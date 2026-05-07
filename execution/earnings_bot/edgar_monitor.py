"""SEC EDGAR 폴링 — 8-K (US) + 6-K (외국 발행인) + NT 10-Q/K 시그널.

매 5분 (Phase 5 systemd timer), Universe 종목별 최근 filings를 fetch.
이미 처리된 accession_number는 db.has_processed로 dedup.

stage 흐름:
  fetched → analyzed → translated → published → notified
이 모듈은 'fetched' 단계까지 책임. 다음 단계는 translator/notion_publisher.
"""
from __future__ import annotations

import json
import logging
import os
from datetime import date, datetime, timedelta, timezone

from edgar import Company, set_identity

from . import db, ticker_registry
from .attachment_parser import parse_filing
from .retry_helper import sec_retry

logger = logging.getLogger(__name__)


# 환경변수 (Phase 5 .env에 등록 필요)
SEC_USER_AGENT = os.getenv('SEC_EDGAR_USER_AGENT', 'Kimtaesik (kts77775@gmail.com)')

# fetch 윈도우: 최근 N일 이내 filings만 본다 (오래된 건 이미 처리됐을 것)
LOOKBACK_DAYS = 7

# NT 10-Q/K 별도 추적
NT_FORMS = ('NT 10-Q', 'NT 10-K')

# 운영 메타: 어떤 form을 ticker별로 추적할지
def _forms_for_ticker(ticker: str) -> list[str]:
    primary = ticker_registry.get_filing_type(ticker)  # '8-K' 또는 '6-K'
    return [primary, 'NT 10-Q', 'NT 10-K']


_initialized = False


def _init() -> None:
    global _initialized
    if _initialized:
        return
    set_identity(SEC_USER_AGENT)
    db.init_db()
    _initialized = True


@sec_retry
def _fetch_recent_filings(ticker: str, form: str, days_back: int | None = None):
    """ticker의 최근 N일 filings 조회. SEC rate limit + 재시도 wrapper."""
    if days_back is None:
        days_back = LOOKBACK_DAYS
    company = Company(ticker)
    cutoff = date.today() - timedelta(days=days_back)
    # edgartools API: get_filings(form=...).filter(filing_date=...)
    filings = company.get_filings(form=form)
    # 너무 많으면 head로 제한 (edgartools가 페이지네이션 처리)
    return [f for f in filings.head(20) if f.filing_date >= cutoff]


def process_ticker(ticker: str) -> list[dict]:
    """1개 ticker의 신규 filings 처리. 반환: 새로 적재된 filing 요약 리스트."""
    _init()
    new_entries = []
    cik = ticker_registry.resolve_cik(ticker)
    if not cik:
        logger.warning(f"[{ticker}] CIK 조회 실패, 건너뜀")
        return []

    for form in _forms_for_ticker(ticker):
        try:
            filings = _fetch_recent_filings(ticker, form)
        except Exception as e:
            logger.error(f"[{ticker}] {form} 조회 실패: {e}")
            continue

        for filing in filings:
            accession = getattr(filing, 'accession_no', None) or getattr(filing, 'accession_number', '')
            if not accession:
                continue

            # dedup: 이미 'fetched' 단계 처리된 건 skip
            if db.has_processed(ticker, document_type=form, stage='fetched',
                                accession_number=accession):
                continue

            # parser: severity + document_subtype + exhibits 추출
            try:
                parsed = parse_filing(filing)
            except Exception as e:
                logger.error(f"[{ticker}] parse 실패 {accession}: {e}")
                continue

            # 외국 발행인의 6-K 중 단순 이사회/거버넌스 발표는 INFO 등급. 알림 폭주 방지.
            if parsed.severity == 'INFO' and parsed.document_subtype in ('6-K_OTHER', '8-K_OTHER', '8-K_REG_FD'):
                # DB 저장은 하지만 다음 stage로 진행 안 됨 (translator가 INFO는 skip)
                pass

            # 발표 시간 (BMO/AMC) lookup — scheduler가 미리 적재했으면 활용
            event_date = filing.filing_date.strftime('%Y-%m-%d') if hasattr(filing, 'filing_date') else None
            amc_or_bmo = db.lookup_calendar_hour(ticker, event_date) if event_date else None

            filed_at_iso = (filing.filing_date.isoformat() + 'T00:00:00+00:00'
                            if hasattr(filing, 'filing_date') else None)

            # 메타 직렬화
            metadata = {
                'document_subtype': parsed.document_subtype,
                'attachment_count': parsed.attachment_count,
                'has_presentation': parsed.has_presentation,
                'exhibit_keys': list(parsed.exhibits.keys()),
                'primary_text_chars': len(parsed.primary_text),
            }
            metadata_json = json.dumps(metadata, ensure_ascii=False)

            row_id = db.upsert_filing(
                ticker=ticker,
                accession_number=accession,
                cik=cik,
                document_type=form,
                stage='fetched',
                form_item=','.join(parsed.items) if parsed.items else None,
                filed_at=filed_at_iso,
                amc_or_bmo=amc_or_bmo,
                severity=parsed.severity,
                source_url=getattr(filing, 'filing_url', None) or getattr(filing, 'document_url', None),
                metadata_json=metadata_json,
            )
            if row_id:
                new_entries.append({
                    'filing_id': row_id,
                    'ticker': ticker,
                    'form': form,
                    'subtype': parsed.document_subtype,
                    'severity': parsed.severity,
                    'accession': accession,
                    'filed_date': event_date,
                    'amc_or_bmo': amc_or_bmo,
                })
                logger.info(
                    f"[{ticker}] NEW {form}/{parsed.document_subtype} "
                    f"sev={parsed.severity} accession={accession}"
                )
                # 분기 실적 (8-K_EARNINGS / 6-K_QUARTERLY)에 한해 transcript 큐 자동 enqueue
                if parsed.document_subtype in ('8-K_EARNINGS', '6-K_QUARTERLY'):
                    try:
                        from . import transcript_watch
                        transcript_watch.initial_enqueue(row_id)
                    except Exception as e:
                        logger.warning(f"[{ticker}] transcript enqueue 실패 filing_id={row_id}: {e}")

    return new_entries


def poll_universe(tickers: list[str] | None = None) -> dict:
    """Universe 전체 1회 폴링. 반환: 통계 dict."""
    _init()
    if tickers is None:
        tickers = ticker_registry.UNIVERSE_USD_DRAFT
    stats = {'tickers': len(tickers), 'new_filings': 0, 'errors': 0, 'entries': []}

    for ticker in tickers:
        try:
            entries = process_ticker(ticker)
            stats['new_filings'] += len(entries)
            stats['entries'].extend(entries)
        except Exception as e:
            logger.error(f"[{ticker}] 폴링 실패: {e}")
            stats['errors'] += 1

    return stats


if __name__ == "__main__":
    import argparse
    logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
    parser = argparse.ArgumentParser()
    parser.add_argument('--ticker', help='단일 ticker 폴링 (테스트용)')
    parser.add_argument('--universe', action='store_true', help='Universe 전체 폴링')
    args = parser.parse_args()

    if args.ticker:
        _init()
        result = process_ticker(args.ticker)
        print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
    elif args.universe:
        result = poll_universe()
        print(f"Tickers: {result['tickers']}, New: {result['new_filings']}, Errors: {result['errors']}")
        for e in result['entries'][:10]:
            print(f"  {e}")
    else:
        parser.print_help()
