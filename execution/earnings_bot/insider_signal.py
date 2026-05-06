"""Form-4 ±30일 insider 거래 부록.

Codex 지적사항 반영:
- transaction_code 화이트리스트 enum 처리
- 파생상품 거래 / 10b5-1 / 증여 / 세금원천징수 / 옵션행사+매도 쌍 → 단순 매수·매도 분류 금지
- 알 수 없는 코드는 raw 보존

SEC Form 4 transaction codes:
  P  = Open market or private purchase of non-derivative or derivative security (BUY)
  S  = Open market or private sale of non-derivative or derivative security (SELL)
  V  = Voluntary report (보통 transfer)
  A  = Grant, award (옵션 부여)
  D  = Sale back to issuer (회사로 매도)
  F  = Payment of exercise price or tax liability (세금/행사가)
  I  = Discretionary transaction (관리자 위임)
  M  = Exercise or conversion of derivative (옵션 행사)
  C  = Conversion of derivative
  E  = Expiration of short derivative position
  H  = Expiration of long derivative position
  O  = Exercise of out-of-the-money derivative
  X  = Exercise of in-the-money/at-the-money derivative
  G  = Bona fide gift (증여)
  L  = Small acquisition under Rule 16a-6
  J  = Other (10b5-1 등 acquired/disposed)
  K  = Equity swap
  U  = Disposition pursuant to a tender of shares
  W  = Acquisition or disposition by will
  Z  = Voting trust deposit/withdrawal
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Literal

from edgar import Company

from .retry_helper import sec_retry

logger = logging.getLogger(__name__)

# 분류용 화이트리스트
OPEN_MARKET_BUY = {'P'}
OPEN_MARKET_SELL = {'S'}
DERIVATIVE_EXERCISE = {'M', 'C', 'X', 'O'}
GRANT_AWARD = {'A'}
TAX_WITHHOLDING = {'F'}
SALE_TO_ISSUER = {'D'}
GIFT = {'G'}
OTHER_10B5_1_LIKE = {'J', 'V', 'I', 'K'}
EXPIRATION = {'E', 'H'}
OTHER_RAW = {'L', 'U', 'W', 'Z'}

ClusterSignal = Literal['strong_buy_cluster', 'moderate_buy_cluster',
                        'strong_sell_cluster', 'moderate_sell_cluster',
                        'mixed', 'inactive']


@dataclass
class InsiderTransaction:
    filed_at: str         # YYYY-MM-DD
    insider_name: str
    insider_role: str     # 'CEO' / 'CFO' / 'Director' / '10% Owner' 등
    transaction_code: str
    bucket: str           # 분류 결과: 'buy' / 'sell' / 'grant' / 'tax' / 'gift' / 'derivative_exercise' / 'sale_to_issuer' / 'other'
    shares: float | None
    price: float | None
    value_usd: float | None
    is_10b5_1: bool       # SEC 신고 footnote에 10b5-1 명시 여부
    raw_form_url: str | None


@dataclass
class InsiderSummary:
    ticker: str
    window_start: str
    window_end: str
    transactions: list[InsiderTransaction]
    cluster_signal: ClusterSignal
    notes: list[str]      # 사람이 읽을 부가 설명 (강조 사항)


def _bucket_for_code(code: str) -> str:
    code = code.upper()
    if code in OPEN_MARKET_BUY:
        return 'buy'
    if code in OPEN_MARKET_SELL:
        return 'sell'
    if code in DERIVATIVE_EXERCISE:
        return 'derivative_exercise'
    if code in GRANT_AWARD:
        return 'grant'
    if code in TAX_WITHHOLDING:
        return 'tax'
    if code in SALE_TO_ISSUER:
        return 'sale_to_issuer'
    if code in GIFT:
        return 'gift'
    if code in OTHER_10B5_1_LIKE:
        return 'other_discretionary'
    if code in EXPIRATION:
        return 'expiration'
    return 'other_raw'


def _safe_float(v) -> float | None:
    """edgartools TransactionActivity의 shares/price/value는 float일 수도, footnote ref('[F1]') 또는
    '$1,234.56' / '1.2M' 같은 문자열일 수도 있음. 깔끔히 변환 안 되면 None."""
    if v is None:
        return None
    if isinstance(v, (int, float)):
        return float(v)
    s = str(v).strip()
    if not s or s.startswith('['):  # '[F1]' 같은 footnote 참조
        return None
    # 숫자/소수점/음수 외 문자 제거 (예: '$1,234' → '1234')
    import re as _re
    cleaned = _re.sub(r'[^\d.\-]', '', s)
    if not cleaned or cleaned in ('.', '-', '-.'):
        return None
    try:
        return float(cleaned)
    except ValueError:
        return None


def _detect_10b5_1(footnotes_text: str) -> bool:
    if not footnotes_text:
        return False
    t = footnotes_text.lower()
    return ('10b5-1' in t or 'rule 10b5' in t)


def _classify_cluster(buys: int, sells: int, distinct_insiders: int) -> ClusterSignal:
    """단순 휴리스틱:
    - 강한 매수 클러스터: buys >= 3 AND distinct >= 2 AND sells == 0
    - 강한 매도 클러스터: sells >= 3 AND distinct >= 2 AND buys == 0
    - 적당한 매수: buys >= 2 AND sells == 0
    - 적당한 매도: sells >= 2 AND buys == 0
    - 그 외 거래 있으면 mixed, 없으면 inactive
    """
    if buys == 0 and sells == 0:
        return 'inactive'
    if buys >= 3 and distinct_insiders >= 2 and sells == 0:
        return 'strong_buy_cluster'
    if sells >= 3 and distinct_insiders >= 2 and buys == 0:
        return 'strong_sell_cluster'
    if buys >= 2 and sells == 0:
        return 'moderate_buy_cluster'
    if sells >= 2 and buys == 0:
        return 'moderate_sell_cluster'
    return 'mixed'


@sec_retry
def _fetch_form4(ticker: str, start: date, end: date) -> list:
    """edgartools로 Form 4 filings fetch."""
    company = Company(ticker)
    filings = company.get_filings(form='4')
    return [f for f in filings.head(100) if start <= f.filing_date <= end]


def fetch_insider_window(ticker: str, event_date: date, days: int = 30) -> InsiderSummary:
    """발표일 ±days 윈도우의 form-4 거래 요약."""
    start = event_date - timedelta(days=days)
    end = event_date + timedelta(days=days)
    filings = _fetch_form4(ticker, start, end)

    transactions: list[InsiderTransaction] = []
    distinct_insiders: set[str] = set()
    buys = sells = 0

    for filing in filings:
        try:
            obj = filing.obj()  # edgartools v5 Form4 object
        except Exception as e:
            logger.warning(f"[{ticker}] form-4 obj 추출 실패 {filing.accession_no}: {e}")
            continue

        # 발표자 + 직책 (v5: insider_name, position 속성)
        owner_name = str(getattr(obj, 'insider_name', None) or 'unknown')
        owner_role = str(getattr(obj, 'position', None) or '')

        # 거래 활동 — v5는 get_transaction_activities() → list[TransactionActivity]
        try:
            activities = obj.get_transaction_activities() or []
        except Exception as e:
            logger.warning(f"[{ticker}] {filing.accession_no} get_transaction_activities 실패: {e}")
            activities = []

        # 정규화된 filing_date (date 객체)
        filing_date_obj = filing.filing_date
        filed_at_str = filing_date_obj.isoformat() if hasattr(filing_date_obj, 'isoformat') else str(filing_date_obj)

        for t in activities:
            code = str(getattr(t, 'code', '') or '').upper()
            if not code:
                continue
            bucket = _bucket_for_code(code)
            shares = _safe_float(getattr(t, 'shares', None))
            price = _safe_float(getattr(t, 'price_per_share', None) or getattr(t, 'price', None))
            value = _safe_float(getattr(t, 'value', None))
            footnotes_text = getattr(t, 'footnotes_text', '') or ''

            txn = InsiderTransaction(
                filed_at=filed_at_str,
                insider_name=owner_name,
                insider_role=owner_role,
                transaction_code=code,
                bucket=bucket,
                shares=shares,
                price=price,
                value_usd=value,
                is_10b5_1=_detect_10b5_1(footnotes_text),
                raw_form_url=getattr(filing, 'filing_url', None) or getattr(filing, 'document_url', None),
            )
            transactions.append(txn)
            distinct_insiders.add(owner_name)
            if bucket == 'buy':
                buys += 1
            elif bucket == 'sell':
                sells += 1

    cluster = _classify_cluster(buys, sells, len(distinct_insiders))

    notes = []
    n_10b5_1 = sum(1 for t in transactions if t.is_10b5_1)
    if n_10b5_1 > 0:
        notes.append(f'10b5-1 사전약정 거래 {n_10b5_1}건 포함 — 의지 시그널로 해석 주의')
    n_tax = sum(1 for t in transactions if t.bucket == 'tax')
    if n_tax > 0:
        notes.append(f'세금원천징수(F) {n_tax}건 — 매수/매도 시그널과 무관')
    n_grant = sum(1 for t in transactions if t.bucket == 'grant')
    if n_grant > 0:
        notes.append(f'옵션 부여(A) {n_grant}건 — 시그널 아님')

    return InsiderSummary(
        ticker=ticker,
        window_start=str(start),
        window_end=str(end),
        transactions=transactions,
        cluster_signal=cluster,
        notes=notes,
    )


def format_appendix(summary: InsiderSummary) -> str:
    """1-page sheet 부록용 짧은 마크다운 (한국어)."""
    if not summary.transactions:
        return f"### 내부자 거래 ({summary.window_start} ~ {summary.window_end})\n없음"

    label = {
        'inactive': '거래 없음',
        'strong_buy_cluster': '강한 매수 클러스터 🟢🟢',
        'moderate_buy_cluster': '매수 우위 🟢',
        'strong_sell_cluster': '강한 매도 클러스터 🔴🔴',
        'moderate_sell_cluster': '매도 우위 🔴',
        'mixed': '혼조',
    }[summary.cluster_signal]

    n_buy = sum(1 for t in summary.transactions if t.bucket == 'buy')
    n_sell = sum(1 for t in summary.transactions if t.bucket == 'sell')
    n_other = len(summary.transactions) - n_buy - n_sell

    lines = [
        f"### 내부자 거래 ({summary.window_start} ~ {summary.window_end})",
        f"**시그널**: {label}",
        f"매수 {n_buy} / 매도 {n_sell} / 기타 {n_other}",
    ]
    for note in summary.notes:
        lines.append(f"- _주의_: {note}")
    return '\n'.join(lines)


if __name__ == "__main__":
    import sys, logging
    logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
    if len(sys.argv) < 3:
        print("Usage: python -m execution.earnings_bot.insider_signal TICKER YYYY-MM-DD")
        sys.exit(1)
    ticker = sys.argv[1]
    event_date = date.fromisoformat(sys.argv[2])
    from edgar import set_identity
    import os
    set_identity(os.getenv('SEC_EDGAR_USER_AGENT', 'Kimtaesik (kts77775@gmail.com)'))
    summary = fetch_insider_window(ticker, event_date)
    print(format_appendix(summary))
    print()
    print(f"[transactions={len(summary.transactions)}, signal={summary.cluster_signal}]")
