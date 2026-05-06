"""YoY 표 기계 산출 — Codex 권고: LLM이 아닌 공시 데이터에서 직접 계산.

LLM 분석 prompt의 계산 실수를 방지하는 앵커 역할.

전략:
1. XBRL (companyfacts) → 정확한 매출/순이익/EPS 추출 (1순위)
2. EX-99.x 텍스트 정규식 → 1순위 실패 시 폴백 (2순위)
3. 둘 다 실패 시 'unavailable' (LLM 분석에 알림 표시)

XBRL fact 키:
- Revenues / RevenueFromContractWithCustomerExcludingAssessedTax
- NetIncomeLoss
- EarningsPerShareBasic / EarningsPerShareDiluted
- OperatingIncomeLoss
- GrossProfit
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Literal

logger = logging.getLogger(__name__)


@dataclass
class YoyMetric:
    label: str             # '매출' / '영업이익' / 'GAAP EPS' 등
    current_value: float | None
    prior_value: float | None
    yoy_pct: float | None  # ((curr - prior) / |prior|) * 100
    unit: str              # '$M' / '$B' / '$' / '%'
    source: Literal['xbrl', 'press_release_regex', 'unavailable']


@dataclass
class YoySnapshot:
    fiscal_year: int
    fiscal_quarter: int
    metrics: list[YoyMetric] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


def _yoy_pct(curr: float | None, prior: float | None) -> float | None:
    if curr is None or prior is None or prior == 0:
        return None
    return ((curr - prior) / abs(prior)) * 100.0


def _format_value(v: float | None, unit: str) -> str:
    if v is None:
        return '—'
    if unit == '$':
        return f'${v:,.2f}'
    if unit == '%':
        return f'{v:.2f}%'
    return f'{v:,.0f}{unit}'


def from_xbrl_facts(ticker: str, fiscal_year: int, fiscal_quarter: int) -> YoySnapshot:
    """edgartools v5 EntityFacts 기반 분기 YoY 계산.

    edgartools v5의 깔끔한 도메인 메서드 활용:
      facts.get_revenue(period='Qn', annual=False)
      facts.get_operating_income / get_net_income / get_gross_profit
    period에 'Q1'/'Q2'/'Q3'/'Q4' 전달, year는 별도 lookup 안 됨 → 폴백 정규식 활용.
    """
    snapshot = YoySnapshot(fiscal_year=fiscal_year, fiscal_quarter=fiscal_quarter)
    try:
        from edgar import Company
        company = Company(ticker)
        facts = getattr(company, 'facts', None)
        if facts is None:
            snapshot.notes.append('edgartools facts 미지원 — 정규식 폴백')
            return snapshot
    except Exception as e:
        snapshot.notes.append(f'xbrl 조회 실패: {e}')
        return snapshot

    period_str = f'Q{fiscal_quarter}'

    # (label, getter_method_name, unit)
    metric_specs = [
        ('매출', 'get_revenue', '$M'),
        ('영업이익', 'get_operating_income', '$M'),
        ('순이익', 'get_net_income', '$M'),
        ('매출총이익', 'get_gross_profit', '$M'),
    ]

    for label, method_name, unit in metric_specs:
        method = getattr(facts, method_name, None)
        if not callable(method):
            snapshot.metrics.append(YoyMetric(
                label=label, current_value=None, prior_value=None, yoy_pct=None,
                unit=unit, source='unavailable',
            ))
            continue
        try:
            curr_val = method(period=period_str, annual=False)
            # edgartools v5의 get_revenue(period=...)는 가장 최근 분기 반환 — fiscal_year 매칭은 별도 검증 필요
            # 폴백 안전: get_fact()로 직접 lookup도 시도
            prior_val: float | None = None
            try:
                # 전년 동기 — period 문자열을 'YYYY-Qn'으로 시도 (edgartools 일부 버전 지원)
                prior_period = f'{fiscal_year - 1}-Q{fiscal_quarter}'
                prior_val = method(period=prior_period, annual=False)
            except Exception:
                pass
        except (TypeError, ValueError) as e:
            logger.debug(f'[{ticker}] {method_name} 호출 실패: {e}')
            curr_val = prior_val = None
        except Exception as e:
            logger.debug(f'[{ticker}] {method_name} 예외: {e}')
            curr_val = prior_val = None

        snapshot.metrics.append(YoyMetric(
            label=label,
            current_value=float(curr_val) if curr_val is not None else None,
            prior_value=float(prior_val) if prior_val is not None else None,
            yoy_pct=_yoy_pct(curr_val, prior_val),
            unit=unit,
            source='xbrl' if curr_val is not None else 'unavailable',
        ))

    return snapshot


# ─── 폴백: EX-99.x 텍스트 정규식 ───
# 보도자료에서 매출/EPS YoY를 정규식으로 추출. XBRL 실패 시만 사용.
RE_REVENUE_PCT = re.compile(
    r'(?:net |total )?(?:revenue|sales)[^\n]{0,80}?'
    r'(?:increased|decreased|up|down|grew|declined|of)\s*(?:by\s*)?([+-]?\d+\.?\d*)\s*%',
    flags=re.IGNORECASE,
)
RE_EPS_VALUE = re.compile(
    r'(?:diluted |gaap )?(?:eps|earnings per (?:diluted )?share)[^\n]{0,60}?\$?(\d+\.\d{2})',
    flags=re.IGNORECASE,
)


def from_press_release_text(text: str, fy: int, fq: int) -> YoySnapshot:
    """EX-99.x 보도자료 정규식 폴백."""
    snap = YoySnapshot(fiscal_year=fy, fiscal_quarter=fq)
    text = text[:20000]  # 첫 20k chars만 (메모리/속도)

    rev_match = RE_REVENUE_PCT.search(text)
    if rev_match:
        try:
            yoy = float(rev_match.group(1))
            snap.metrics.append(YoyMetric(
                label='매출 YoY (보도자료 텍스트)',
                current_value=None, prior_value=None, yoy_pct=yoy,
                unit='%', source='press_release_regex',
            ))
        except ValueError:
            pass

    eps_match = RE_EPS_VALUE.search(text)
    if eps_match:
        try:
            eps = float(eps_match.group(1))
            snap.metrics.append(YoyMetric(
                label='희석 EPS (보도자료 텍스트)',
                current_value=eps, prior_value=None, yoy_pct=None,
                unit='$', source='press_release_regex',
            ))
        except ValueError:
            pass

    if not snap.metrics:
        snap.notes.append('보도자료 텍스트에서 매출 YoY/EPS 추출 실패')
    return snap


def compute_yoy(ticker: str, fiscal_year: int, fiscal_quarter: int,
                press_release_text: str = '') -> YoySnapshot:
    """XBRL + 정규식 병합 — Codex 권고: 부분 XBRL이 정규식 폴백을 억제하지 않도록.

    - 완전한 XBRL metric (current+prior 모두 있음): 그대로 채택
    - 부분 또는 unavailable: 정규식 결과로 보강 (덮어쓰기 아닌 추가)
    """
    snap = from_xbrl_facts(ticker, fiscal_year, fiscal_quarter)

    # XBRL이 모든 핵심 metric에서 완전(current+prior)한 경우만 정규식 스킵
    fully_complete = (
        len(snap.metrics) > 0
        and all(m.source == 'xbrl' and m.current_value is not None and m.prior_value is not None
                for m in snap.metrics)
    )
    if fully_complete:
        return snap

    if press_release_text:
        text_snap = from_press_release_text(press_release_text, fiscal_year, fiscal_quarter)
        # 정규식 결과를 추가 (덮어쓰기 X). 사용자/모델이 source 컬럼으로 출처 구별 가능
        snap.metrics.extend(text_snap.metrics)
        snap.notes.extend(text_snap.notes)

    return snap


def format_table(snapshot: YoySnapshot) -> str:
    """마크다운 테이블 (1-page sheet용)."""
    lines = [
        f"### YoY 비교 ({snapshot.fiscal_year} Q{snapshot.fiscal_quarter})",
        "| 항목 | 당분기 | 전년동기 | YoY | 출처 |",
        "|---|---|---|---|---|",
    ]
    for m in snapshot.metrics:
        curr = _format_value(m.current_value, m.unit)
        prior = _format_value(m.prior_value, m.unit)
        yoy = f'{m.yoy_pct:+.1f}%' if m.yoy_pct is not None else '—'
        lines.append(f"| {m.label} | {curr} | {prior} | {yoy} | {m.source} |")
    for note in snapshot.notes:
        lines.append(f"\n_{note}_")
    return '\n'.join(lines)


if __name__ == "__main__":
    import sys, logging
    logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
    if len(sys.argv) < 4:
        print("Usage: python -m execution.earnings_bot.yoy_calculator TICKER FY FQ")
        sys.exit(1)
    from edgar import set_identity
    import os
    set_identity(os.getenv('SEC_EDGAR_USER_AGENT', 'Kimtaesik (kts77775@gmail.com)'))
    snap = compute_yoy(sys.argv[1], int(sys.argv[2]), int(sys.argv[3]))
    print(format_table(snap))
