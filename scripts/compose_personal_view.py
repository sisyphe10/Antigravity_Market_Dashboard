#!/usr/bin/env python3
"""compose_personal_view.py — 게시 스냅숏의 개인용 뷰 합성 (통합 설계 unified_design_claude.md §3.2, 옵션 a).

publish_snapshot.sh 가 새 릴리스 디렉토리(argv[1])를 rsync 한 직후 호출. 두 repo·GitHub 산출물 불변,
모든 가공은 스냅숏 사본에서만. Sisyphe 페이지는 매 실행 sisyphe_plain 원본에서 새로 복사되므로 주입은 항상 pristine 기준.

2026-07-16 개편: Sisyphe 구역 해체 — 단일 AoE topnav 로 전 페이지 통일.
  좌측: Watchlist · Market(▾) · Wiki / 우측 그룹(margin-left:auto): Invest · Memento · Ledger · Architecture(맨 끝).
  Sisyphe 탭·아이보리 강조·웜톤 바·←AoE 필·랜딩(index) 폐지 — /sisyphe/index.html 은 Memento 리다이렉트 스텁.
  journal/dashboard/memento 의 topnav 는 AoE 세트로 교체(해당 탭 active). 검증 실패 시 exit1 -> 세대 폐기.
"""
import os, re, sys, glob, shutil

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "execution"))
import nav_style  # AoE 상단 네비 정본 (2026-07-26 통일) — 탭 구성·CSS 의 유일한 출처
P = nav_style.PALETTE  # 다크 팔레트 정본 — 아래 주입 CSS 의 색값은 전부 여기서 파생

REL = sys.argv[1]
SISYPHE_PLAIN = os.environ.get("SISYPHE_PLAIN", "/Users/sisyphe/srv/sisyphe_plain")
SISYPHE_PAGES = ("index.html", "dashboard.html", "journal.html", "memento.html", "checklist_test.html")

# ---- 루트 페이지별 네비 active 매핑 (2026-07-26 whole-nav 교체 방식으로 개편) ----
# 구 방식(fragment 조각 주입·이동)은 사본 드리프트의 원인이라 폐기 —
# 모든 페이지의 <nav> 블록을 nav_style.nav_html() 정본으로 통째 교체한다.
ROOT_ACTIVE = {  # filename -> (active, sub_active)
    'index.html':        (None, None),
    'market.html':       ('market', 'market'),
    'universe.html':     ('market', 'universe'),
    'universe_lab.html': ('market', 'universe_lab'),
    'featured.html':     ('market', 'featured'),
    'market_alert.html': ('market', 'market_alert'),
    'etf.html':          ('market', 'etf'),
    'seibro.html':       ('market', 'seibro'),
    'taiwan.html':       ('market', None),
    'hotels.html':       ('market', None),
    'gh_market.html':    ('market', None),
    'architecture.html': ('architecture', None),
}
NAV_MUST_HAVE = ('index.html', 'market.html', 'architecture.html')  # nav 누락 시 게시 중단

AOE_UPDATED_JS = ('<script id="aoe-updated-move">document.addEventListener("DOMContentLoaded",function(){'
                  'var u=document.querySelector(".last-updated"),s=document.querySelector(".mkt-subtabs")||document.querySelector(".tabs")||document.querySelector(".sidebar");'
                  'if(u&&s){var w=document.createElement("div");w.style.cssText="text-align:right;padding:4px 28px 14px";'
                  'w.appendChild(u);s.insertAdjacentElement("afterend",w);}});</script>')

# 정본 네비 CSS 주입 — 생성기(create_dashboard 등)가 구버전 CSS 로 만든 페이지도
# 스냅숏에서는 즉시 정본 기하·색으로 수렴한다 (</head> 직전 주입 = 동일 명시도 후행 승리).
AOE_NAV_CANON = '<style id="aoe-nav-canon">' + nav_style.NAV_CSS + '</style>'
canon_pat = re.compile(r'<style id="aoe-nav-canon">.*?</style>', re.S)

# 2026-07-18 본문 블룸버그 터미널 다크(시안 A Terminal Black, 사용자 확정): AoE 루트 페이지 전체.
# 배경 거의 검정 + 앰버(#fb8b1e) 강조. ★차트 패널(.chart-card/.cmb-chart-item 등, canvas 포함 컨테이너)은
# 흰색 유지 — Chart.js 텍스트가 다크 전제라 다크 카드에 두면 안 보임. 등락색: 클래스(.pos/.neg 등)는
# 다크용 밝은 톤으로 재단언(td 일괄 규칙이 덮는 문제 v2 보정), 인라인 밝은 배경 셀은 어두운 글자 유지.
# Sisyphe 페이지(sisyphe/)는 미적용(구역 구분 유지). v2: 스크린샷 검증 보정 6건(2026-07-18).
AOE_DARK_CSS = (
    '<style id="aoe-terminal-dark">'
    ':root{--bg-color:' + P['bg'] + ';--card-bg:' + P['card'] + ';--text-color:' + P['text'] + ';--category-bg:' + P['th-bg'] + '}'
    'body{background:' + P['bg'] + '!important;color:' + P['text'] + '!important}'
    # (구) nav.topnav 색·폰트 재단언 4줄 제거 (2026-07-26): 정본 aoe-nav-canon 이 이미 앰버·1rem —
    # !important 재단언은 모바일 미디어쿼리(0.85rem)까지 덮어 폭별 드리프트를 만들었다.
    'header h1{color:#f2f4f6!important}'
    '.last-updated{color:' + P['muted'] + '!important}'
    'header h1{display:none!important}'
    'header .subtitle,header .sub{display:none!important}'
    'header{margin:0!important;padding:0 28px!important;text-align:right!important}'
    '.last-updated{margin:0!important;font-size:0.78rem!important}'
    '.section,.mkt-panel,.table-container,.stat-card,.card,.constituents-row,'
    '.csel-display,.csel-list,.cmb-filter-pop,.tw-filter-pop,.layer,.node,.timeline'
    '{background:' + P['card'] + '!important;color:' + P['text'] + '!important;border-color:' + P['border'] + '!important;'
    'box-shadow:none!important}'
    '.date-bar input,.controls select,.filters select,select,textarea,input[type=date],input[type=text],'
    '.qrow,.plan-in'
    '{background:' + P['input-bg'] + '!important;color:' + P['text'] + '!important;border-color:' + P['input-border'] + '!important}'
    '.category-title,.section>h2,.section>h3,h2.block-title{color:' + P['amber'] + '!important;letter-spacing:1.5px}'
    'th{background:' + P['th-bg'] + '!important;color:' + P['amber'] + '!important;border-color:#2a2b2e!important}'
    'td{border-color:#222326!important}'
    'td:not([style*=color]){color:#fff!important}'
    # 표 셀 가운데 정렬 일괄 (인라인 text-align 지정 셀만 예외 — 긴 본문용)
    'td:not([style*=text-align]),th:not([style*=text-align]){text-align:center!important}'
    'tbody tr:hover td{background:' + P['hover'] + '!important}'
    '.cmb-series-row td{color:#fff!important}'
    # 별표 고정 섹션 구분행 (2026-07-28): 라이트 원본 CSS를 다크로 재단언.
    # ★일괄 td 규칙(font-size 17px·border)이 !important 라 여기도 !important 필수.
    '#cmbSideTable tr.cmb-pin-head td{background:#0f1417!important;color:' + P['hl2-fg'] + '!important;'
    'font-weight:700!important;font-size:12px!important;letter-spacing:1.2px!important;'
    'text-align:left!important;padding:5px 10px!important;border-bottom:1px solid #223038!important}'
    # 등락색 다크용 재단언 — td 일괄 규칙보다 뒤에 두어 우선 적용
    '.pos,td.pos,.positive,td.positive{color:' + P['up'] + '!important}'
    '.neg,td.neg,.negative,td.negative{color:' + P['down'] + '!important}'
    # 인라인 밝은 배경(히트 틴트·경보 핑크) 위 글자는 어둡게 유지
    'td[style*=background],tr[style*=background] td{color:#333!important}'
    # 다크 틴트 인라인 배경(딤 앰버/딤 바이올렛 — universe RSI/YTD)은 밝은 글자 유지
    'td[style*="241a3d"],td[style*="0a3038"]{color:#e8e8e8!important}'
    '.tabs{border-bottom-color:' + P['amber'] + '!important}'
    '.subtab,.mkt-subtab,.tab,.mbtn,.chg-fbtn,.nav-button,.tw-more-btn,.tw-dl-btn,'
    '.cmb-filter-btn,.cmb-ma-btn'
    '{background:' + P['input-bg'] + '!important;color:#9aa4ae!important;border:1.5px solid #565a60!important;'
    'border-radius:2px!important}'
    '.subtab:hover,.mkt-subtab:hover,.tab:hover,.mbtn:hover,.nav-button:hover'
    '{color:' + P['amber'] + '!important;border-color:' + P['amber'] + '!important}'
    '.subtab.active,.mkt-subtab.active,.tab.active,.cmb-filter-btn.active,.cmb-ma-btn.active,'
    '.mbtn.active,.nav-button.active'
    '{background:' + P['amber'] + '!important;color:' + P['nav-bg'] + '!important;border-color:' + P['amber'] + '!important;'
    'font-weight:700}'
    '.stat-card{border-left-color:' + P['amber'] + '!important}'
    '.stat-card .label{color:' + P['muted'] + '!important}'
    '.stat-card .value{color:#f2f4f6!important}'
    '.node .node-name{color:#f2f4f6!important}'
    '.node .node-sched{color:' + P['muted'] + '!important}'
    '.tl-band-count{background:' + P['th-bg'] + '!important;color:' + P['text'] + '!important}'
    '.qrow.starred{background:' + P['hl1-bg'] + '!important}'
    '.sidebar-link.active{border-bottom-color:' + P['amber'] + '!important}'
    '.sidebar{justify-content:center!important}'
    # 타이포 정수 스케일 (2026-07-18 사용자 확정): 대제목28/섹션18/표본문16/메타13/표헤더12
    'table,td{font-size:17px!important}'
    'th{font-size:15px!important}'
    '.category-title{font-size:30px!important}'
    '.section>h2,.section>h3,.section-title,.section-header,.sector-group h3,'
    'h2.block-title,.wg-head .wg-title,.chart-box h3,.category-detail h3,'
    '.table-wrap h3,.pcat-head{font-size:20px!important}'
    '.section-count,.category-date{font-size:14px!important}'
    '.sidebar,.ledger-subtabs,.mm-main .subtabs{height:42px!important;'
    'box-sizing:border-box!important;align-items:stretch!important;overflow:hidden!important}'
    '.sidebar-link,.ledger-subtab,.mm-main .subtabs .subtab{height:41px!important;font-size:18px!important}'
    'button[style*="#dc2626"]{background:' + P['amber'] + '!important;color:' + P['nav-bg'] + '!important;'
    'border:1.5px solid ' + P['amber'] + '!important;border-radius:2px!important}'
    'button[style*="#2563eb"]{background:transparent!important;color:' + P['amber'] + '!important;'
    'border:1.5px solid ' + P['amber'] + '!important;border-radius:2px!important}'
    'button[style*="#f3f4f6"]{background:transparent!important;color:#9aa4ae!important;'
    'border:1.5px solid ' + P['input-border'] + '!important;border-radius:2px!important}'
    '.tw-dl-btn{background:' + P['amber'] + '!important;color:' + P['nav-bg'] + '!important;border-color:' + P['amber'] + '!important}'
    '.node .node-type{background:#101214!important;color:' + P['text'] + '!important}'
    '.mm-main{padding-top:0!important}'
    '.mm-main .subtabs{margin:0 calc(50% - 50vw) 18px!important}'
    '.ledger-subtabs{margin:0 calc(50% - 50vw) 18px!important}'
    '.cmb-series-row:has(.cmb-chart-item.active) td{background:' + P['hl1-bg'] + '!important;color:' + P['hl1-fg'] + '!important;font-weight:700!important}'
    '.cmb-series-row:has(.cmb-chart-item.active) ~ .cmb-series-row:has(.cmb-chart-item.active) td{background:' + P['hl2-bg'] + '!important;color:' + P['hl2-fg'] + '!important;font-weight:700!important}'
    '.cmb-series-row:has(.cmb-chart-item.active) ~ .cmb-series-row:has(.cmb-chart-item.active) ~ .cmb-series-row:has(.cmb-chart-item.active) td{background:' + P['hl3-bg'] + '!important;color:' + P['hl3-fg'] + '!important;font-weight:700!important}'
    '.cmb-series-row:has(.cmb-chart-item.active) ~ .cmb-series-row:has(.cmb-chart-item.active) ~ .cmb-series-row:has(.cmb-chart-item.active) ~ .cmb-series-row:has(.cmb-chart-item.active) td{background:' + P['hl1-bg'] + '!important;color:' + P['hl1-fg'] + '!important;font-weight:700!important}'
    '.cmb-series-row:has(.cmb-chart-item.active) ~ .cmb-series-row:has(.cmb-chart-item.active) ~ .cmb-series-row:has(.cmb-chart-item.active) ~ .cmb-series-row:has(.cmb-chart-item.active) ~ .cmb-series-row:has(.cmb-chart-item.active) td{background:' + P['hl2-bg'] + '!important;color:' + P['hl2-fg'] + '!important;font-weight:700!important}'
    '.cmb-series-row:has(.cmb-chart-item.active) ~ .cmb-series-row:has(.cmb-chart-item.active) ~ .cmb-series-row:has(.cmb-chart-item.active) ~ .cmb-series-row:has(.cmb-chart-item.active) ~ .cmb-series-row:has(.cmb-chart-item.active) ~ .cmb-series-row:has(.cmb-chart-item.active) td{background:' + P['hl3-bg'] + '!important;color:' + P['hl3-fg'] + '!important;font-weight:700!important}'
    '.today-date{color:#c9ced4!important}'
    '.qcard{background:' + P['card2'] + '!important;color:#fff!important;border-color:' + P['border'] + '!important;box-shadow:none!important}'
    '.qcard .qsrc,.qcard .qsrc .qnote{color:#fff!important}'
    '.plan-gcell{background:' + P['card'] + '!important}'
    # 미국 ETF 탭 (etf.html, 2026-07-19 사용자 확정): 본문 흰색 기본, 회색은 설명(메타)만.
    # 실투자 행 = 시안 하이라이트(선택 순환 3번), 한국 O = 녹색, 등락 = 다크 등락색 재단언.
    '#etfTab3 td{color:#fff!important}'
    '#etfTab3 td.pos{color:' + P['up'] + '!important}'
    '#etfTab3 td.neg{color:' + P['down'] + '!important}'
    '#etfTab3 td.us-mut{color:' + P['muted'] + '!important}'
    '#etfTab3 td.kr-o{color:#7ec87e!important}'
    '#etfTab3 tr.us-hl td{background:' + P['hl1-bg'] + '!important}'
    '#etfTab3 td.us-hl-name{color:' + P['hl1-fg'] + '!important}'
    '#etfTab3 .us-dl{background:transparent!important;color:' + P['amber'] + '!important;'
    'border:1.5px solid ' + P['amber'] + '!important}'
    '.chart-card,.sector-card,.idx-chart-item,.lh-card,'
    '.chart-container,.section:has(canvas),div:has(>canvas)'
    '{background:#fff!important;color:#333!important}'
    # 흰 패널 내부 td 구제: 범용 td:not([style*=color])의 밝은 글자가 흰 바탕에 씻김 — Indices 사이드바
    # (2026-07-19 0c55c2d8, 병합 유실 후 재복원)
    'tr.idx-chart-item td{color:#333!important}'
    # Monthly Returns = 생성기 다크 네이티브(416b0842 재복원) — 틴트 셀은 흰 글자 유지
    '#mrTableWrap td[style*=background]{color:#fff!important}'
    # 다크 네이티브 차트 예외 (사용자 지정: SEIBro 막대·Universe Lab 산점도) — id 명시도로 화이트리스트 이김
    '.section:has(#topChart),div:has(>#topChart),.card:has(#scatter),div:has(>#scatter)'
    '{background:' + P['card'] + '!important;color:' + P['text'] + '!important}'
    # 무클래스 표 캡션류(h2~h4, Featured "거래대금 TOP 30" 등) = 흰색. 앰버 섹션타이틀 규칙(.section>h2 등)이 명시도로 우선
    'h2,h3,h4{color:#fff!important}'
    '</style>')
dark_pat = re.compile(r'<style id="aoe-terminal-dark">.*?</style>', re.S)

# ---- Sisyphe 페이지: topnav 를 정본(nav_style.nav_html)으로 교체 ----
# 구 자체 마크업(평면형 <a> 나열)은 폐기 — 루트 페이지와 동일한 DOM 계약(.topnav-item 래퍼).

# checklist_test.html = 테스트 페이지(직접 URL 전용, nav 탭 없음 → active 없음)
ACTIVE_OF = {'journal.html': 'journal', 'dashboard.html': 'ledger', 'memento.html': 'memento',
             'checklist_test.html': None}
# journal 페이지: 해시(#weekly)에 따라 nav 액티브를 Journal↔Weekly 로 전환 + 페이지 서브탭 동기화
HASH_ACTIVE_JS = (
    '<script id="aoe-nav-hash-active">document.addEventListener("DOMContentLoaded",function(){'
    'var nav=document.querySelector("nav.topnav");if(!nav)return;'
    'var j=nav.querySelector(\'a[href="/sisyphe/journal.html"]\');'
    'var w=nav.querySelector(\'a[href="/sisyphe/journal.html#weekly"]\');'
    'function u(sync){var wk=location.hash==="#weekly";'
    'if(j)j.classList.toggle("active",!wk);if(w)w.classList.toggle("active",wk);'
    'if(sync&&typeof switchTab==="function")switchTab(wk?"weekly":"journal");}'
    'window.addEventListener("hashchange",function(){u(true)});u(false);});</script>')
# 1안(2026-07-16 사용자 확정): 사이드바 전면 제거 — journal(서브내비=본문 tab-bar)·dashboard 공통.
# 본문 좌측 오프셋도 해제. (구 JOURNAL_OFFSET·CORNER_BRAND 는 사이드바와 함께 폐기)
NO_SIDEBAR = '<style id="aoe-nosidebar">.sidebar{display:none}.has-sidebar{padding-left:24px !important}</style>'
JOURNAL_OFFSET = (
    '<style id="aoe-journal-offset">'
    'nav.topnav .topnav-inner{max-width:none;padding-left:228px;padding-right:24px}'
    '@media(max-width:900px){nav.topnav .topnav-inner{padding-left:12px;padding-right:12px}}'
    '</style>'
)

# Sisyphe 페이지의 자체 .topnav CSS 를 이기는 정본 override (2026-07-26: nav_style 스코프 렌더).
# 기하·색 정본은 nav_style 단일 출처 — 여기는 사이드바 배지 등 Sisyphe 잔여 규칙만 추가.
NAV_UNIFY = (
    '<style id="aoe-nav-unify">'
    + nav_style.NAV_CSS_SCOPED +
    # 좌상단 사이드바 배지 = 다크 nav 와 한 몸 (NO_SIDEBAR 로 통상 숨김 — 폴백 정합용)
    '.sidebar-brand{height:54px;background:' + P['nav-bg'] + ';color:#fff;font-size:1.1rem;font-weight:800;'
    'letter-spacing:3.5px;border-bottom:2px solid ' + P['amber'] + ';right:-1px}'
    '.sidebar-brand:hover{color:' + P['amber'] + '}'
    '.sidebar{background:' + P['nav-bg'] + ';border-right-color:#2a323b}'
    '.sidebar .sidebar-link{color:#9aa4ae;font-size:0.9rem;padding:11px 14px;margin-bottom:2px;'
    'border:none;border-left:3px solid transparent;border-radius:0;text-align:left}'
    '.sidebar .sidebar-link:hover{background:#1a2027;color:#fff;border-color:transparent;border-left-color:transparent}'
    '.sidebar .sidebar-link.active{background:#1c1416;color:#fff;font-weight:700;border-left-color:' + P['amber'] + '}'
    'body{background:#f8f9fa}'
    '</style>'
)

jnav_pat = re.compile(r'<nav class="topnav">.*?</nav>', re.S)
personal_css_pat = re.compile(r'<style id="aoe-personal-nav">.*?</style>', re.S)  # 구세대 잔재 제거용
warm_bar_pat = re.compile(r'<style id="sisyphe-warm-bar">.*?</style>', re.S)


def fail(msg):
    sys.stderr.write("[compose] FAIL: %s\n" % msg)
    sys.exit(1)


def inject_before_head(s, frag):
    i = s.lower().find("</head>")
    if i == -1:
        return None
    return s[:i] + frag + s[i:]


# ===== 1) AoE 페이지: WRAP 제거 + topnav 를 정본으로 통째 교체 (2026-07-26 개편) =====
wrap = os.path.join(REL, "wrap.html")
if os.path.exists(wrap):
    os.remove(wrap)
for f in glob.glob(os.path.join(REL, "*.html")):
    name = os.path.basename(f)
    s = open(f, encoding="utf-8").read()
    act, sub = ROOT_ACTIVE.get(name, (None, None))
    # <nav class="topnav"> 블록 전체를 정본으로 교체 (repl=함수 — 백슬래시 이스케이프 회피)
    n, cnt = jnav_pat.subn(lambda m, a=act, su=sub: nav_style.nav_html(a, su), s, 1)
    if cnt == 0 and name in NAV_MUST_HAVE:
        fail("%s: topnav 블록 없음 — 교체 불가" % name)
    # 구세대 주입 잔재 제거 (clean 입력이면 무동작)
    n = personal_css_pat.sub("", n)
    n = canon_pat.sub("", n)
    n = dark_pat.sub("", n)
    if cnt:  # nav 있는 페이지에만 정본 CSS·다크 주입 (canon 먼저 → dark 가 후행 !important)
        if 'id="aoe-nav-canon"' not in n:
            r = inject_before_head(n, AOE_NAV_CANON)
            if r is not None:
                n = r
        if 'id="aoe-updated-move"' not in n:
            r = inject_before_head(n, AOE_UPDATED_JS)
            if r is not None:
                n = r
        if 'id="aoe-terminal-dark"' not in n:
            r = inject_before_head(n, AOE_DARK_CSS)
            if r is not None:
                n = r
    if n != s:
        open(f, "w", encoding="utf-8").write(n)

if os.path.exists(wrap):
    fail("wrap.html 잔존")
idx = os.path.join(REL, "index.html")
if os.path.exists(idx):
    t = open(idx, encoding="utf-8").read()
    if 'class="topnav-brand">AGE OF EMERGENCE</a>' not in t:
        fail("index.html: 정본 브랜드 없음")
    # 탭 순서 = nav_style.NAV_LABELS 정본 그대로인지 (라벨 위치 오름차순 + right-group 위치)
    pos = [t.find('>%s<' % lb) for lb in nav_style.NAV_LABELS]
    pos.insert(nav_style.NAV_LABELS.index('Memento'), t.find('topnav-item right-group'))
    if -1 in pos or pos != sorted(pos):
        fail("index.html: 탭 순서 오류 %s" % pos)
    if 'sisyphe-tab' in t or 'topnav-sub">가계부' in t:
        fail("index.html: 구 Sisyphe 탭 잔존")

for pg in ("market.html", "index.html"):
    pp = os.path.join(REL, pg)
    if os.path.exists(pp):
        tt = open(pp, encoding="utf-8").read()
        if 'id="aoe-terminal-dark"' not in tt:
            fail("%s: terminal-dark CSS 누락" % pg)
        if 'id="aoe-nav-canon"' not in tt:
            fail("%s: 정본 네비 CSS 누락" % pg)

# ===== 2) Sisyphe 평문 합성 (매 실행 pristine 복사) =====
dst = os.path.join(REL, "sisyphe")
os.makedirs(dst, exist_ok=True)
for name in SISYPHE_PAGES:
    src = os.path.join(SISYPHE_PLAIN, name)
    if not os.path.isfile(src) or os.path.getsize(src) == 0:
        fail("sisyphe 평문 소스 없음/빈파일: %s" % src)
    shutil.copyfile(src, os.path.join(dst, name))


# corp_codes_lite.json 복사 — journal DART 자동채움 lookup (2026-07-27: GitHub Pages 404 → 로컬 서빙).
# 원본=sisyphe_repo(시간당 pull). 없으면 경고만 — journal 은 GAS 폴백으로 동작.
_cc_src = os.path.expanduser("~/srv/sisyphe_repo/corp_codes_lite.json")
if os.path.isfile(_cc_src) and os.path.getsize(_cc_src) > 0:
    shutil.copyfile(_cc_src, os.path.join(dst, "corp_codes_lite.json"))
else:
    sys.stderr.write("[compose] 경고: corp_codes_lite.json 원본 없음 — journal GAS 폴백\n")

# ===== 3) Sisyphe 페이지 가공 =====
STATIC = ("staticrypt", "encryptedmsg", "cryptoengine")
for name in SISYPHE_PAGES:
    p = os.path.join(dst, name)
    s = open(p, encoding="utf-8").read()
    low = s.lower()
    for mk in STATIC:
        if mk in low:
            fail("sisyphe/%s: staticrypt 흔적(%s)" % (name, mk))

    if name == "index.html":
        # 랜딩 폐지 — Memento 리다이렉트 스텁만 검증
        if 'http-equiv="refresh"' not in s or 'memento.html' not in s:
            fail("sisyphe/index.html: Memento 리다이렉트 스텁 아님")
        continue

    # topnav 를 정본으로 교체 (journal/dashboard/memento 공통) — 루트 페이지와 동일 DOM
    m = jnav_pat.search(s)
    if not m:
        fail("sisyphe/%s: topnav 블록 없음 — 교체 불가" % name)
    s = s[:m.start()] + nav_style.nav_html(ACTIVE_OF[name]) + s[m.end():]
    s = warm_bar_pat.sub("", s)

    r = inject_before_head(s, NAV_UNIFY)
    if r is None:
        fail("sisyphe/%s: </head> 없음" % name)
    s = r
    # 2026-07-18 사용자 지시: Sisyphe 구역 구분 폐지 — AoE terminal-dark 를 동일 주입
    r = inject_before_head(s, AOE_DARK_CSS)
    if r is None:
        fail("sisyphe/%s: 다크 CSS 주입 실패" % name)
    s = r
    if name in ("journal.html", "dashboard.html"):
        s = inject_before_head(s, NO_SIDEBAR)
    if name == "journal.html":
        s = inject_before_head(s, HASH_ACTIVE_JS)

    open(p, "w", encoding="utf-8").write(s)

    # ---- 검증 ----
    fin = open(p, encoding="utf-8").read()
    if 'id="aoe-nav-unify"' not in fin:
        fail("sisyphe/%s: 통일 CSS 검증 실패" % name)
    if 'id="aoe-terminal-dark"' not in fin:
        fail("sisyphe/%s: 다크 CSS 검증 실패" % name)
    if 'topnav-brand">AGE OF EMERGENCE' not in fin:
        fail("sisyphe/%s: AoE nav 교체 검증 실패" % name)
    if ACTIVE_OF[name]:
        active_label = {'journal': 'Journal', 'memento': 'Memento', 'ledger': 'Ledger'}[ACTIVE_OF[name]]
        chk = fin.replace(' style="margin-left:auto"', '')
        if ('class="topnav-tab active">%s</a>' % active_label) not in chk:
            fail("sisyphe/%s: 활성 탭(%s) 검증 실패" % (name, active_label))
    if 'sisyphe-warm-bar' in fin:
        fail("sisyphe/%s: 웜톤 바 잔존" % name)
    if name in ("journal.html", "dashboard.html") and 'id="aoe-nosidebar"' not in fin:
        fail("sisyphe/%s: 사이드바 제거 검증 실패" % name)

sys.stdout.write("[compose] OK: 정본 AoE nav(nav_style) 전 페이지 교체 + Sisyphe %d페이지 합성 (%s)\n"
                 % (len(SISYPHE_PAGES), os.path.basename(REL)))
