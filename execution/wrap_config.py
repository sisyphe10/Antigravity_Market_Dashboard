"""WRAP 증권사·상품 단일 출처 레지스트리 (Single Source of Truth).

증권사/상품 추가 = 이 파일의 BROKERS / PRODUCTS 에 엔트리 1건 추가 (+ 자문지 템플릿 파일 1개).
기존 8개 스크립트에 흩어져 있던 dict/list (portfolio_config, ytd_base_dates, chart_series,
broker_colors, PORTFOLIO_GROUPS, FIXED_PRODUCTS, ORDER_PORTFOLIOS, GENERAL ...)는 모두 여기서
파생 생성한다. 자세한 배경은 broker_onboarding/AUDIT.md, DESIGN_*.md 참조.

설계 핵심
---------
- 페어/단독 구분 폐지: 결합 표시는 `group` id 하나로 통일.
  · 일반형 3사(→4사): 모두 group='GENERAL_OPEN' → 결합명 자동 생성.
  · NH/DB 목표전환형 페어: 같은 group id 부여 → 결합명 자동.
  · 한투 단독 목표전환형: group=None → 개별 표시.
- 데이터 키 분리: NH는 AUM 시트('다이내믹밸류')와 NAV/NEW 시트('Value ESG')가 다름.
  · nav_key  : 기준가/수익률/NEW 시트 컬럼·상품명 (NAV·수익률·차트 조인 키)
  · aum_name : AUM 시트 '상품명' (AUM 표·add_aum 입력 키)
- 표시 라벨 변형: 소비자마다 라벨이 historically 다름 → display + monthly_label + report_label.

추가 절차 (출시일)
------------------
1. 신규 증권사면 BROKERS 에 Broker(...) 1건.
2. PRODUCTS 에 Product(...) 1건 (active=True, keep_in_nav=True).
3. 자문지/ 폴더에 advisory_template 파일 1개.
4. Wrap_NAV.xlsx NEW 시트 종목 + AUM 시트 개시 AUM.
5. 표준 체인 실행 (calculate_wrap_nav → calculate_returns → create_portfolio_tables → create_dashboard).
청산: 해당 Product.active=False + end_date 기입 (keep_in_nav 는 청산 직후 한동안 True 유지 → 컬럼 완결).
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Broker:
    code: str          # AUM/NEW 시트 '증권사' 값 ('삼성'|'NH'|'DB'|'한투'...)
    color: str         # 브랜드 색 (#RRGGBB)
    order: int         # 표시·정렬 순서 (작을수록 먼저)


@dataclass(frozen=True)
class Product:
    broker: str                       # Broker.code
    nav_key: str                      # 기준가/수익률/NEW 시트 컬럼·상품명
    aum_name: str                     # AUM 시트 '상품명' (보통 nav_key 와 동일)
    ptype: str                        # 'general' | 'target'
    kind_label: str                   # add_aum 입력 유형 ('일반형'|'지속형'|'목표전환형'...)
    display: str                      # 표준 표시명 (차트·PORTFOLIO·GENERAL 결합)
    base_price: float
    start_date: str                   # 'YYYY-MM-DD'
    ytd_base: str                     # YTD 기준일 (보통 start_date)
    color: str                        # 차트 계열색 (기본=broker color)
    advisory_template: str | None     # 자문지/ 경로 (Order 카드 Download)
    group: str | None = None          # 결합 그룹 id (None=단독)
    active: bool = True               # 대시보드 활성 표시 여부
    keep_in_nav: bool = True          # calculate_wrap_nav portfolio_config 포함 (청산분도 컬럼 완결용 True 유지)
    end_date: str | None = None       # 청산일 ('YYYY-MM-DD'), 활성은 None
    monthly_label: str | None = None  # 월별수익률 표 라벨 (None=display)
    report_label: str | None = None   # 텔레그램 일간리포트 nav_map 라벨 (None=display)
    keywords: tuple = ()              # _categorize Wrap 인식 substring (비면 [nav_key, display])

    @property
    def monthly(self) -> str:
        return self.monthly_label or self.display

    @property
    def report(self) -> str:
        return self.report_label or self.display

    @property
    def wrap_keywords(self) -> list:
        return list(self.keywords) if self.keywords else [self.nav_key, self.display]


# ── 증권사 ─────────────────────────────────────────────────────────────
# 한투(한국투자증권)는 상품 출시일(2026-07-02)에 추가:
#   Broker('한투', '#F58220', 40)  ← 색은 출시 전 확정
BROKERS = [
    Broker('삼성', '#1428A0', 10),
    Broker('NH',   '#0072CE', 20),
    Broker('DB',   '#00854A', 30),
]

# ── 결합 그룹 (동일 종목/비중 → 한 줄로 결합 표시) ──────────────────────
# use: 결합 그룹의 대표 nav_key (데이터·수익률을 대표로 끌어옴)
GROUPS = {
    'GENERAL_OPEN': {'use': '트루밸류'},   # 일반형(영구) 결합 — 한투 지속형 합류 예정
}

# ── 벤치마크 (차트·수익률 표 공통) ─────────────────────────────────────
BENCHMARKS = [
    {'display': 'KOSPI',  'nav_key': 'KOSPI',  'color': '#000000', 'ytd_base': '2025-12-30'},
    {'display': 'KOSDAQ', 'nav_key': 'KOSDAQ', 'color': '#666666', 'ytd_base': '2025-12-30'},
]

# ── 상품 ───────────────────────────────────────────────────────────────
PRODUCTS = [
    # 활성 일반형 3종 (2025-12-30 개시, 사실상 동일 포트)
    Product(broker='삼성', nav_key='트루밸류', aum_name='트루밸류', ptype='general', kind_label='일반형',
            display='삼성 트루밸류', base_price=2021.31, start_date='2025-12-30', ytd_base='2025-12-30',
            color='#1428A0', advisory_template='자문지/라이프자산운용_트루밸류_260427.xlsx',
            group='GENERAL_OPEN', keywords=('트루밸류', '삼성 트루밸류')),
    Product(broker='NH', nav_key='Value ESG', aum_name='다이내믹밸류', ptype='general', kind_label='일반형',
            display='NH Value ESG', base_price=1980.49, start_date='2025-12-30', ytd_base='2025-12-30',
            color='#0072CE', advisory_template='자문지/라이프자산운용_라이프 다이내믹밸류_일반형 _2026.4.27.xlsx',
            group='GENERAL_OPEN', monthly_label='NH 다이내믹밸류 일반형',
            keywords=('Value ESG', 'NH Value ESG')),
    Product(broker='DB', nav_key='개방형 랩', aum_name='개방형 랩', ptype='general', kind_label='일반형',
            display='DB 개방형', base_price=1518.52, start_date='2025-12-30', ytd_base='2025-12-30',
            color='#00854A', advisory_template='자문지/라이프자산운용_DB 개방형 랩 _2026.4.27.xlsx',
            group='GENERAL_OPEN', report_label='DB 개방형 랩',
            keywords=('개방형', 'DB 개방형')),

    # 활성 목표전환형 (단기 랩) — NH 5호 2026-06-29 개시. 단독(group=None), DB 6차(7/1)는 별도.
    # advisory_template은 자문지 .xlsx 확보 시 경로 주입 (현재 Order 탭 직접 입력 운용).
    Product(broker='NH', nav_key='목표전환형 5호', aum_name='목표전환형 5호', ptype='target', kind_label='목표전환형',
            display='NH 목표전환형 5호', base_price=1000.00, start_date='2026-06-29', ytd_base='2026-06-29',
            color='#0072CE', advisory_template='자문지/라이프자산운용_라이프 다이내믹밸류_목표전환형 5호_2026.6.29.xlsx', group=None,
            active=True, keep_in_nav=True),
    # DB 목표전환형 6차 — 2026-07-01 개시. 단독(group=None).
    Product(broker='DB', nav_key='목표전환형 6차', aum_name='목표전환형 6차', ptype='target', kind_label='목표전환형',
            display='DB 목표전환형 6차', base_price=1000.00, start_date='2026-07-01', ytd_base='2026-07-01',
            color='#00854A',
            advisory_template='자문지/라이프자산운용_DB 목표전환형 랩 _6차_2026.7.1.xlsx',
            group=None, active=True, keep_in_nav=True),

    # 청산 목표전환형 (이력 보존 — EXCLUDED_PORTFOLIOS 자동 파생). active=False.
    # 5차/4호는 2026-06-23 end_date 동결 SOP 적용분 → keep_in_nav=True (컬럼 완결).
    Product(broker='NH', nav_key='목표전환형 4호', aum_name='목표전환형 4호', ptype='target', kind_label='목표전환형',
            display='NH 목표전환형 4호', base_price=1000.00, start_date='2026-06-15', ytd_base='2026-06-15',
            color='#0072CE', advisory_template=None, active=False, keep_in_nav=True, end_date='2026-06-19'),
    Product(broker='DB', nav_key='목표전환형 5차', aum_name='목표전환형 5차', ptype='target', kind_label='목표전환형',
            display='DB 목표전환형 5차', base_price=1000.00, start_date='2026-06-12', ytd_base='2026-06-12',
            color='#00854A', advisory_template=None, active=False, keep_in_nav=True, end_date='2026-06-19'),
    # 이하 구(舊) 청산분 — keep_in_nav=False (이미 컬럼 완결, calc_wrap_nav 미포함)
    Product(broker='NH', nav_key='목표전환형 3호', aum_name='목표전환형 3호', ptype='target', kind_label='목표전환형',
            display='NH 목표전환형 3호', base_price=1000.00, start_date='2026-05-14', ytd_base='2026-05-14',
            color='#0072CE', advisory_template=None, active=False, keep_in_nav=False, end_date='2026-05-27'),
    Product(broker='DB', nav_key='목표전환형 4차', aum_name='목표전환형 4차', ptype='target', kind_label='목표전환형',
            display='DB 목표전환형 4차', base_price=1000.00, start_date='2026-05-18', ytd_base='2026-05-18',
            color='#00854A', advisory_template=None, active=False, keep_in_nav=False, end_date='2026-05-27'),
    Product(broker='NH', nav_key='목표전환형 2호', aum_name='목표전환형 2호', ptype='target', kind_label='목표전환형',
            display='NH 목표전환형 2호', base_price=1000.00, start_date='2026-04-29', ytd_base='2026-04-29',
            color='#0072CE', advisory_template=None, active=False, keep_in_nav=False, end_date='2026-05-06'),
    Product(broker='DB', nav_key='목표전환형 3차', aum_name='목표전환형 3차', ptype='target', kind_label='목표전환형',
            display='DB 목표전환형 3차', base_price=1000.00, start_date='2026-04-30', ytd_base='2026-04-30',
            color='#00854A', advisory_template=None, active=False, keep_in_nav=False, end_date='2026-05-06'),
    Product(broker='NH', nav_key='목표전환형 1호', aum_name='목표전환형 1호', ptype='target', kind_label='목표전환형',
            display='NH 목표전환형 1호', base_price=1000.00, start_date='2026-03-25', ytd_base='2026-03-25',
            color='#0072CE', advisory_template=None, active=False, keep_in_nav=False, end_date='2026-04-15'),
    Product(broker='DB', nav_key='목표전환형 2차', aum_name='목표전환형 2차', ptype='target', kind_label='목표전환형',
            display='DB 목표전환형 2차', base_price=1000.00, start_date='2026-03-16', ytd_base='2026-03-16',
            color='#00854A', advisory_template=None, active=False, keep_in_nav=False, end_date='2026-04-15'),
    Product(broker='DB', nav_key='목표전환형', aum_name='목표전환형 1차', ptype='target', kind_label='목표전환형',
            display='DB 목표전환형', base_price=1000.00, start_date='2026-02-11', ytd_base='2026-02-11',
            color='#00854A', advisory_template=None, active=False, keep_in_nav=False, end_date='2026-02-25'),
]


# ── 기본 조회 ──────────────────────────────────────────────────────────
def _brokers_sorted():
    return sorted(BROKERS, key=lambda b: b.order)


def broker_by_code(code):
    for b in BROKERS:
        if b.code == code:
            return b
    return None


def active_products():
    return [p for p in PRODUCTS if p.active]


def _broker_order(code):
    b = broker_by_code(code)
    return b.order if b else 9999


def _sorted_active(products):
    return sorted(products, key=lambda p: _broker_order(p.broker))


# ── 결합 그룹 ──────────────────────────────────────────────────────────
def group_active_members(group_id):
    return _sorted_active([p for p in active_products() if p.group == group_id])


def combined_display(group_id):
    members = group_active_members(group_id)
    return ' / '.join(p.display for p in members)


def group_use(group_id):
    return GROUPS.get(group_id, {}).get('use')


def active_group_ids():
    seen = []
    for p in _sorted_active(active_products()):
        if p.group and p.group not in seen:
            seen.append(p.group)
    return seen


# ── 파생물 (기존 하드코딩 치환) ─────────────────────────────────────────
def nav_portfolio_config():
    """calculate_wrap_nav.py / portfolio_config (keep_in_nav 상품)."""
    cfg = {}
    for p in PRODUCTS:
        if not p.keep_in_nav:
            continue
        entry = {'base_price': p.base_price, 'start_date': p.start_date}
        if p.end_date:
            entry['end_date'] = p.end_date
        cfg[p.nav_key] = entry
    return cfg


def contribution_portfolio_config():
    """create_contribution_data.py / portfolio_config (활성 상품만, end_date 없음)."""
    return {p.nav_key: {'base_price': p.base_price, 'start_date': p.start_date}
            for p in active_products()}


def ytd_base_dates():
    """calculate_returns.py / ytd_base_dates (활성 + 벤치마크)."""
    d = {p.nav_key: p.ytd_base for p in active_products()}
    for b in BENCHMARKS:
        d[b['nav_key']] = b['ytd_base']
    return d


def portfolio_display_names():
    """create_portfolio_tables.py / PORTFOLIO_DISPLAY_NAMES (활성 상품 nav_key→display)."""
    return {p.nav_key: p.display for p in active_products()}


def excluded_portfolios():
    """create_portfolio_tables.py / EXCLUDED_PORTFOLIOS (비활성 nav_key)."""
    return {p.nav_key for p in PRODUCTS if not p.active}


def portfolio_groups():
    """create_portfolio_tables.py / PORTFOLIO_GROUPS (활성 멤버 있는 그룹)."""
    groups = []
    for gid in active_group_ids():
        members = group_active_members(gid)
        groups.append({
            'sources': [p.nav_key for p in members],
            'combined': ' / '.join(p.display for p in members),
            'use': group_use(gid) or members[0].nav_key,
        })
    return groups


def wrap_keywords():
    """create_dashboard.py / wrap_keywords (_categorize Wrap 인식)."""
    kws = []
    for p in _sorted_active(active_products()):
        for k in p.wrap_keywords:
            if k not in kws:
                kws.append(k)
    return kws


def _display_for_chart(p):
    """그룹 멤버라도 차트/수익률 계열은 개별 display 사용 (결합은 표/Order 전용)."""
    return p.display


def chart_series():
    """create_dashboard.py / chart_series (활성 개별 + 벤치마크)."""
    series = [(p.display, p.nav_key) for p in _sorted_active(active_products())]
    series += [(b['display'], b['nav_key']) for b in BENCHMARKS]
    return series


def chart_colors():
    """create_dashboard.py / chart_colors."""
    colors = {p.display: p.color for p in _sorted_active(active_products())}
    for b in BENCHMARKS:
        colors[b['display']] = b['color']
    return colors


def broker_colors():
    """create_dashboard.py / broker_colors (AUM 표·누적차트)."""
    return {b.code: b.color for b in _brokers_sorted()}


def monthly_returns_products():
    """create_dashboard.py / create_wrap_monthly_returns_table products (벤치마크 + 일반형 개별)."""
    items = [(b['display'], b['nav_key']) for b in BENCHMARKS]
    items += [(p.monthly, p.nav_key) for p in _sorted_active(active_products()) if p.ptype == 'general']
    return items


def wrap_returns_items():
    """create_dashboard.py / create_wrap_returns_table items (벤치마크 + 일반형 그룹대표 + 활성 target)."""
    items = [(b['display'], b['nav_key']) for b in BENCHMARKS]
    # 일반형: 그룹별 대표 1개 (동일 수익률) — 그룹 없는 일반형은 개별
    done_groups = set()
    for p in _sorted_active(active_products()):
        if p.ptype != 'general':
            continue
        if p.group:
            if p.group in done_groups:
                continue
            done_groups.add(p.group)
            use_key = group_use(p.group) or p.nav_key
            up = next((x for x in active_products() if x.nav_key == use_key), p)
            items.append((up.display, up.nav_key))
        else:
            items.append((p.display, p.nav_key))
    # 활성 목표전환형: 개별
    for p in _sorted_active(active_products()):
        if p.ptype == 'target':
            items.append((p.display, p.nav_key))
    return items


def portfolio_names():
    """draw_wrap_charts.py / PORTFOLIO_NAMES (활성 nav_key→display)."""
    return {p.nav_key: p.display for p in _sorted_active(active_products())}


def report_nav_map():
    """daily_portfolio_report.py / nav_map (활성 display(report_label)→nav_key)."""
    return {p.report: p.nav_key for p in _sorted_active(active_products())}


def report_return_products():
    """daily_portfolio_report.py 수익률 product 리스트 (그룹대표 + 벤치마크 + 활성 target)."""
    out = []
    done_groups = set()
    for p in _sorted_active(active_products()):
        if p.ptype != 'general':
            continue
        if p.group:
            if p.group in done_groups:
                continue
            done_groups.add(p.group)
            out.append(group_use(p.group) or p.nav_key)
        else:
            out.append(p.nav_key)
    for b in BENCHMARKS:
        out.append(b['nav_key'])
    for p in _sorted_active(active_products()):
        if p.ptype == 'target':
            out.append(p.nav_key)
    return out


def report_display_names():
    """daily_portfolio_report.py 수익률 display_names (그룹대표 nav_key→display + 벤치마크)."""
    d = {}
    done_groups = set()
    for p in _sorted_active(active_products()):
        if p.ptype != 'general':
            continue
        if p.group:
            if p.group in done_groups:
                continue
            done_groups.add(p.group)
            use_key = group_use(p.group) or p.nav_key
            up = next((x for x in active_products() if x.nav_key == use_key), p)
            d[up.nav_key] = up.display
        else:
            d[p.nav_key] = p.display
    for b in BENCHMARKS:
        d[b['nav_key']] = b['display']
    for p in _sorted_active(active_products()):
        if p.ptype == 'target':
            d[p.nav_key] = p.display
    return d


def fixed_products():
    """add_aum.py / FIXED_PRODUCTS — {(broker, kind_label): aum_name} (활성 일반형/지속형)."""
    return {(p.broker, p.kind_label): p.aum_name
            for p in active_products() if p.ptype == 'general'}


def active_target_transform():
    """add_aum.py / ACTIVE_TARGET_TRANSFORM — {broker: aum_name} (활성 목표전환형)."""
    return {p.broker: p.aum_name for p in active_products() if p.ptype == 'target'}


# ── Order/이메일 JS 페이로드 ───────────────────────────────────────────
def general_combined_name():
    """create_dashboard.py JS / GENERAL (일반형 결합 표시명·jsonKey)."""
    return combined_display('GENERAL_OPEN')


def order_portfolios():
    """create_dashboard.py JS / ORDER_PORTFOLIOS (결합 그룹 카드 + 단독 target 카드)."""
    cards = []
    # 결합 그룹 카드 (일반형 등)
    for gid in active_group_ids():
        members = group_active_members(gid)
        combined = ' / '.join(p.display for p in members)
        cards.append({
            'display': combined,
            'jsonKey': combined,
            'templates': [{'label': p.display, 'file': p.advisory_template}
                          for p in members if p.advisory_template],
            'newSheetTargets': [{'broker': p.broker, 'product': p.nav_key} for p in members],
        })
    # 단독(그룹 없는) 활성 상품 카드 — 보통 한투 단독 목표전환형
    for p in _sorted_active(active_products()):
        if p.group:
            continue
        templates = [{'label': p.display, 'file': p.advisory_template}] if p.advisory_template else []
        cards.append({
            'display': p.display,
            'jsonKey': p.display,
            'templates': templates,
            'newSheetTargets': [{'broker': p.broker, 'product': p.nav_key}],
        })
    return cards


def target_tabs():
    """create_dashboard.py JS / TARGET_TABS (활성 목표전환형 display — 결합 이메일/네이트온 노출 대상)."""
    return [p.display for p in _sorted_active(active_products()) if p.ptype == 'target']


def broker_order_map():
    """create_dashboard.py JS / BROKER_ORDER — {code: 0..N} (정렬용)."""
    return {b.code: i for i, b in enumerate(_brokers_sorted())}


def broker_color_map():
    """create_dashboard.py JS / BROKER_COLOR — {code: color}."""
    return {b.code: b.color for b in _brokers_sorted()}


# ── 출시 전 안전 검증 ──────────────────────────────────────────────────
def validate(today=None, nav_file='Wrap_NAV.xlsx'):
    """레지스트리 정합성 + (start_date<=today 인 활성 상품의) 데이터/자문지 존재 강제 점검.

    today: 'YYYY-MM-DD' (None이면 데이터 존재 검사 생략, 구조 검사만).
    반환: 경고 메시지 리스트 (빈 리스트면 정상).
    """
    warns = []
    nav_keys = [p.nav_key for p in PRODUCTS]
    if len(nav_keys) != len(set(nav_keys)):
        warns.append('중복 nav_key 존재')
    for p in PRODUCTS:
        if p.broker not in {b.code for b in BROKERS}:
            warns.append(f'미등록 증권사: {p.broker} ({p.nav_key})')
        if p.group and p.group not in GROUPS:
            warns.append(f'미등록 group: {p.group} ({p.nav_key})')
        if p.active and not p.keep_in_nav:
            warns.append(f'활성인데 keep_in_nav=False: {p.nav_key}')
    if today is not None:
        import os
        import pandas as pd
        new_pairs = set()
        aum_pairs = set()
        if os.path.exists(nav_file):
            try:
                new_df = pd.read_excel(nav_file, sheet_name='NEW')
                new_pairs = set(zip(new_df['증권사'], new_df['상품명']))
            except Exception:
                pass
            try:
                aum_df = pd.read_excel(nav_file, sheet_name='AUM')
                aum_pairs = set(zip(aum_df['증권사'], aum_df['상품명']))
            except Exception:
                pass
        for p in active_products():
            if p.start_date <= today:
                if (p.broker, p.nav_key) not in new_pairs:
                    warns.append(f'개시일 도래했으나 NEW 시트 없음: {p.broker}/{p.nav_key}')
                if (p.broker, p.aum_name) not in aum_pairs:
                    warns.append(f'개시일 도래했으나 AUM 시트 없음: {p.broker}/{p.aum_name}')
                if p.advisory_template and not os.path.exists(p.advisory_template):
                    warns.append(f'자문지 템플릿 없음: {p.advisory_template}')
    return warns


if __name__ == '__main__':
    import sys
    sys.stdout.reconfigure(encoding='utf-8')
    print('=== BROKERS ===', [b.code for b in _brokers_sorted()])
    print('=== active ===', [p.nav_key for p in active_products()])
    print('nav_portfolio_config:', nav_portfolio_config())
    print('ytd_base_dates:', ytd_base_dates())
    print('portfolio_groups:', portfolio_groups())
    print('chart_series:', chart_series())
    print('chart_colors:', chart_colors())
    print('broker_colors:', broker_colors())
    print('monthly_returns_products:', monthly_returns_products())
    print('wrap_returns_items:', wrap_returns_items())
    print('wrap_keywords:', wrap_keywords())
    print('fixed_products:', fixed_products())
    print('active_target_transform:', active_target_transform())
    print('report_nav_map:', report_nav_map())
    print('report_return_products:', report_return_products())
    print('report_display_names:', report_display_names())
    print('portfolio_names:', portfolio_names())
    print('general_combined_name:', general_combined_name())
    print('order_portfolios:', order_portfolios())
    print('target_tabs:', target_tabs())
    print('excluded_portfolios:', sorted(excluded_portfolios()))
    print('validate:', validate())
