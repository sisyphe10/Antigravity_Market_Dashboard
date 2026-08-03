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
    'universe.html':     ('watchlist', 'universe'),        # 2026-07-31 Watchlist 하위로 이동
    'universe_lab.html': ('watchlist', 'universe_lab'),
    'featured.html':     ('market', 'featured'),
    'market_alert.html': ('market', 'market_alert'),
    'etf.html':          ('market', 'etf'),
    'seibro.html':       ('market', 'seibro'),
    'taiwan.html':       ('market', None),
    'hotels.html':       ('market', None),
    'gh_market.html':    ('market', None),
    'architecture.html': ('architecture', 'architecture'),
    'system_map.html':   ('architecture', 'system_map'),
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
    ':root{--bg-color:' + P['bg'] + ';--card-bg:' + P['card'] + ';--text-color:#fff;--category-bg:' + P['th-bg'] + '}'
    'body{background:' + P['bg'] + '!important;color:#fff!important}'
    # (구) nav.topnav 색·폰트 재단언 4줄 제거 (2026-07-26): 정본 aoe-nav-canon 이 이미 앰버·1rem —
    # !important 재단언은 모바일 미디어쿼리(0.85rem)까지 덮어 폭별 드리프트를 만들었다.
    'header h1{color:#fff!important}'
    '.last-updated{color:#fff!important}'
    'header h1{display:none!important}'
    'header .subtitle,header .sub{display:none!important}'
    'header{margin:0!important;padding:0 28px!important;text-align:right!important}'
    '.last-updated{margin:0!important;font-size:0.78rem!important}'
    '.section,.mkt-panel,.table-container,.stat-card,.card,.constituents-row,'
    '.csel-display,.csel-list,.cmb-filter-pop,.tw-filter-pop,.layer,.node,.timeline'
    '{background:' + P['card'] + '!important;color:#fff!important;border-color:' + P['border'] + '!important;'
    'box-shadow:none!important}'
    # 필터 팝업 항목 라벨 (2026-08-03): 원본 .cmb-filter-item/.tw-filter-item 의 color:#111 이
    # 다크 카드 배경 위에 그대로 남아 글자가 안 보였다 — 밝은 글자로 재단언 + 호버 배경 다크화.
    '.cmb-filter-item,.tw-filter-item{color:#fff!important}'
    '.tw-filter-item:hover{background:' + P['hover'] + '!important}'
    '.date-bar input,.controls select,.filters select,select,textarea,input[type=date],input[type=text],'
    '.qrow,.plan-in'
    '{background:' + P['input-bg'] + '!important;color:#fff!important;border-color:' + P['input-border'] + '!important}'
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
    '#cmbSideTable tr.cmb-pin-head td{background:' + P['hl2-fg'] + '!important;padding:0!important;'
    'height:2px!important;line-height:0!important;font-size:0!important;border:0!important}'
    # 등락색 다크용 재단언 — td 일괄 규칙보다 뒤에 두어 우선 적용
    '.pos,td.pos,.positive,td.positive{color:' + P['up'] + '!important}'
    '.neg,td.neg,.negative,td.negative{color:' + P['down'] + '!important}'
    # 인라인 밝은 배경(히트 틴트·경보 핑크) 위 글자는 어둡게 유지
    'td[style*=background],tr[style*=background] td{color:#333!important}'
    # 다크 틴트 인라인 배경(딤 앰버/딤 바이올렛 — universe RSI/YTD)은 밝은 글자 유지
    'td[style*="241a3d"],td[style*="0a3038"]{color:#fff!important}'
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
    '.stat-card .label{color:#fff!important}'
    '.stat-card .value{color:#fff!important}'
    '.node .node-name{color:#fff!important}'
    '.node .node-sched{color:#fff!important}'
    '.tl-band-count{background:' + P['th-bg'] + '!important;color:#fff!important}'
    '.qrow.starred{background:' + P['hl1-bg'] + '!important}'
    '.sidebar-link.active{border-bottom-color:' + P['amber'] + '!important}'
    '.sidebar{justify-content:center!important}'
    # 타이포 정수 스케일 (2026-07-18 사용자 확정): 대제목28/섹션18/표본문16/메타13/표헤더12
    # (2026-08-03 재단언 제거) 표 크기는 코어 토큰 변수만 주입 — 그리는 규칙은 코어·페이지 소유.
    # !important = 페이지 컨테이너의 라이트 값(16px 등)보다 우선하기 위함 (변수 선언에만 사용).
    'table{--aoe-t-font:17px!important;--aoe-t-head-font:15px!important}'
    '.category-title{font-size:30px!important}'
    '.section>h2,.section>h3,.section-title,.section-header,.sector-group h3,'
    'h2.block-title,.wg-head .wg-title,.chart-box h3,.category-detail h3,'
    '.table-wrap h3,.pcat-head{font-size:20px!important}'
    '.section-count,.category-date{font-size:14px!important}'
    '.sidebar,.ledger-subtabs,.journal-subtabs,.mm-main .subtabs{height:42px!important;'
    'box-sizing:border-box!important;align-items:stretch!important;overflow:hidden!important}'
    '.sidebar-link,.ledger-subtab,.journal-subtab,.mm-main .subtabs .subtab{height:41px!important;font-size:18px!important}'
    'button[style*="#dc2626"]{background:' + P['amber'] + '!important;color:' + P['nav-bg'] + '!important;'
    'border:1.5px solid ' + P['amber'] + '!important;border-radius:2px!important}'
    # Copy 버튼(#0891b2) = 앰버 다음 강조색인 시안 채움 (2026-08-02 사용자 확정)
    'button[style*="#0891b2"]{background:' + P['hl2-fg'] + '!important;color:' + P['hl2-bg'] + '!important;'
    'border:1.5px solid ' + P['hl2-fg'] + '!important;border-radius:2px!important}'
    'button[style*="#2563eb"]{background:transparent!important;color:' + P['amber'] + '!important;'
    'border:1.5px solid ' + P['amber'] + '!important;border-radius:2px!important}'
    'button[style*="#f3f4f6"]{background:transparent!important;color:#fff!important;'
    'border:1.5px solid ' + P['input-border'] + '!important;border-radius:2px!important}'
    '.tw-dl-btn{background:' + P['amber'] + '!important;color:' + P['nav-bg'] + '!important;border-color:' + P['amber'] + '!important}'
    '.node .node-type{background:#101214!important;color:#fff!important}'
    '.mm-main{padding-top:0!important}'
    '.mm-main .subtabs{margin:0 calc(50% - 50vw) 18px!important}'
    '.ledger-subtabs,.journal-subtabs{margin:0 calc(50% - 50vw) 18px!important}'
    # 선택행 하이라이트 (2026-08-03 개편): JS(applyMarkerColors)가 클릭 순번을
    # data-hl(1~3 순환)로 마킹 — 별표 복제 행과 원본이 항상 같은 색을 받고,
    # 순번이 차트 클릭 순서 기반이라 차트 선 색 순서와도 일치.
    # (구) :has 형제 체인은 복제 행이 순번을 오염시켜 폐기.
    '.cmb-series-row[data-hl="1"] td{background:' + P['hl1-bg'] + '!important;color:' + P['hl1-fg'] + '!important;font-weight:700!important}'
    '.cmb-series-row[data-hl="2"] td{background:' + P['hl2-bg'] + '!important;color:' + P['hl2-fg'] + '!important;font-weight:700!important}'
    '.cmb-series-row[data-hl="3"] td{background:' + P['hl3-bg'] + '!important;color:' + P['hl3-fg'] + '!important;font-weight:700!important}'
    '.today-date{color:#fff!important}'
    '.qcard{background:' + P['card2'] + '!important;color:#fff!important;border-color:' + P['border'] + '!important;box-shadow:none!important}'
    '.qcard .qsrc,.qcard .qsrc .qnote{color:#fff!important}'
    '.plan-gcell{background:' + P['card'] + '!important}'
    # 미국 ETF 탭 (etf.html, 2026-07-19 사용자 확정): 본문 흰색 기본, 회색은 설명(메타)만.
    # 실투자 행 = 시안 하이라이트(선택 순환 3번), 한국 O = 녹색, 등락 = 다크 등락색 재단언.
    '#etfTab3 td{color:#fff!important}'
    '#etfTab3 td.pos{color:' + P['up'] + '!important}'
    '#etfTab3 td.neg{color:' + P['down'] + '!important}'
    '#etfTab3 td.us-mut{color:#fff!important}'
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
    '.section:has(#topChart),div:has(>#topChart),.card:has(#scatter),div:has(>#scatter),'
    '.chart-box:has(#trendChart),div:has(>#trendChart),'
    '.chart-box:has(#categoryChart),div:has(>#categoryChart)'
    '{background:' + P['card'] + '!important;color:#fff!important}'
    # 무클래스 표 캡션류(h2~h4, Featured "거래대금 TOP 30" 등) = 흰색. 앰버 섹션타이틀 규칙(.section>h2 등)이 명시도로 우선
    'h2,h3,h4{color:#fff!important}'
    # ---- architecture.html 다크 보정 (2026-07-28) ----
    # 생성기(create_architecture.py)는 라이트 전제라 도식도 밖(설명문·타임라인 라벨·위키 목록/카드)이
    # 전부 #000~#555 → 다크 배경에서 사실상 안 보였다. 페이지 고유 클래스라 여기서만 보정한다.
    '.block-sub,.layer-desc,.wiki-count,.wi-sched,.wi-caret,.card-meta,.tl-tick,.tl-band-sub'
    '{color:#fff!important}'
    '.layer-head,.tl-band-name,.wi-name{color:#fff!important}'
    '.tl-label,.tl-name{color:#fff!important}'
    '.tl-freq{background:' + P['input-border'] + '!important;color:#fff!important}'
    '.tl-axis{border-bottom-color:' + P['input-border'] + '!important}'
    '.tl-track{background:repeating-linear-gradient(90deg,#1a1b1e 0,#1a1b1e 1px,'
    'transparent 1px,transparent 12.5%)!important}'
    '.tl-trigger{color:#fff!important;background:#1a1b1e!important;'
    'border-color:' + P['input-border'] + '!important}'
    '.tl-mark{border-color:' + P['bg'] + '!important}'
    '.tl-band{background:' + P['card2'] + '!important;border-left-color:' + P['amber'] + '!important}'
    '.tl-band-count{background:' + P['th-bg'] + '!important;color:#fff!important}'
    '.wg-head{border-bottom-color:' + P['amber'] + '!important}'
    '.wg-head .wg-title{color:' + P['amber'] + '!important}'
    '.wg-head .g-count{background:' + P['th-bg'] + '!important;color:#fff!important}'
    '.wi-summary,.card-desc,.card-desc p,.card-desc li,.card-desc strong,'
    '.card-desc h4,.card-desc h5,.card-desc h6,.chip-row .chip-k'
    '{color:#fff!important}'
    '.witem{border-bottom-color:#1f2023!important}'
    '.witem-row:hover{background:' + P['hover'] + '!important}'
    '.wiki-search{background:' + P['input-bg'] + '!important;color:#fff!important;'
    'border-color:' + P['input-border'] + '!important}'
    '.legend .sep{background:' + P['input-border'] + '!important}'
    'header.page-head{border-bottom-color:' + P['border'] + '!important}'
    # 타이포 2단 통일 (2026-07-28 사용자 지시): 본문 15px / 보조 13px.
    # 페이지가 12.5·13.1·14·14.4·15.2·17px 6종으로 난립해 구역마다 크기가 달라 보였다.
    # ★일괄 'table,td{17px!important}' 를 이겨야 하므로 여기서 !important 로 재단언한다.
    # 표 부분은 재단언 대신 변수 재선언 (2026-08-03 — 전역 table 변수 주입 17/15를 아키 확정값 15/13으로 상회)
    '.skill-table{--aoe-t-font:15px!important;--aoe-t-head-font:13px!important}'
    '.skill-table .sk-name,.node .node-name,.wi-name,.layer-head,'
    '.card-desc,.card-desc p,.card-desc li{font-size:15px!important}'
    '.node .node-sched,.layer-desc,.block-sub,.wi-sched,.wi-summary,.card-meta,'
    '.tl-label,.tl-name,.tl-band-sub,.wiki-count{font-size:13px!important}'
    '.skill-table .sk-name{font-weight:400!important}'
    '.skill-table .sk-code code{font-family:inherit!important;color:#fff!important}'
    'footer,footer a,.date-bar span,.section-count,.no-match,.note,.data-table th .sort-arrow{color:#fff!important}'
    '[style*="color:#888"],[style*="color: #888"],[style*="color:#999"],[style*="color: #999"],[style*="color:#aaa"],[style*="color:#9ca3af"],[style*="color: #9ca3af"]{color:#fff!important}'
    '.chart-card [style*="color:#888"],.chart-container [style*="color:#888"],.lh-card [style*="color:#888"],.chart-card [style*="color:#999"],.chart-container [style*="color:#999"]{color:#333!important}'
    '</style>')
dark_pat = re.compile(r'<style id="aoe-terminal-dark">.*?</style>', re.S)

# ---- Sisyphe 페이지: topnav 를 정본(nav_style.nav_html)으로 교체 ----
# 구 자체 마크업(평면형 <a> 나열)은 폐기 — 루트 페이지와 동일한 DOM 계약(.topnav-item 래퍼).

# checklist_test.html = 테스트 페이지(직접 URL 전용, nav 탭 없음 → active 없음)
ACTIVE_OF = {'journal.html': 'journal', 'dashboard.html': 'ledger', 'memento.html': 'memento',
             'checklist_test.html': None}
# journal 페이지: 해시(#weekly)에 따라 nav 액티브를 Journal↔Weekly 로 전환 + 페이지 서브탭 동기화
# 2026-08-03: Weekly 상단 탭 병합 — 상단 Journal 은 상시 active, 해시는 드롭다운·하위 스트립만 전환
HASH_ACTIVE_JS = (
    '<script id="aoe-nav-hash-active">document.addEventListener("DOMContentLoaded",function(){'
    'function u(sync){var wk=location.hash==="#weekly";'
    'var all=document.querySelectorAll(".topnav-dropdown a[href*=journal], #aoeJournalStrip a");'
    'Array.prototype.forEach.call(all,function(a){'
    'var isW=(a.getAttribute("href")||"").indexOf("#weekly")>-1;'
    'a.classList.toggle("active",isW===wk);});'
    'if(sync&&typeof switchTab==="function")switchTab(wk?"weekly":"journal");}'
    'window.addEventListener("hashchange",function(){u(true)});u(location.hash==="#weekly");});</script>')

# Journal 하위 스트립 (Ledger 서브탭 양식 이식 — sticky 42px 가로 스트립, active=앰버 밑줄)
JOURNAL_STRIP_CSS = (
    '<style id="aoe-journal-strip-css">'
    '.journal-subtabs{position:sticky;top:54px;display:flex;justify-content:center;align-items:stretch;'
    'gap:2px;margin:0 0 18px;padding:0 28px;background:#161b21;border-bottom:1px solid #2a323b;z-index:90}'
    '.journal-subtab{display:inline-flex;align-items:center;height:38px;padding:0 14px;border:none;'
    'border-radius:0;border-bottom:2px solid transparent;background:transparent;color:#9aa4ae;'
    'font-family:inherit;font-size:0.85rem;font-weight:600;cursor:pointer;text-decoration:none;'
    'transition:color 0.12s}'
    '.journal-subtab:hover{color:#fff}'
    '.journal-subtab.active{color:#fff;font-weight:700;border-bottom-color:' + P['amber'] + '}'
    '</style>')
JOURNAL_STRIP = (
    '<div class="journal-subtabs" id="aoeJournalStrip">'
    '<a href="#daily" class="journal-subtab active">Daily</a>'
    '<a href="#weekly" class="journal-subtab">Weekly</a></div>')
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
# 하위 스트립(sub-strip)도 정본 교체 대상 (2026-07-31): 상단 드롭다운만 교체하던 탓에
# 구 빌더가 구워둔 <aside class="sidebar"> 가 살아남아 Market 스트립에 Universe 가 잔존했다.
sidebar_pat = re.compile(r'<aside class="sidebar">.*?</aside>', re.S)
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
    # 하위 스트립을 정본 그룹 children 으로 교체 (자식 없는 그룹이면 스트립 제거).
    # ★ROOT_ACTIVE 미등록 페이지는 손대지 않는다 — (None,None) 로 떨어져 멀쩡한
    #   스트립이 삭제되는 사고 방지 (2026-07-31 적대적 검증 지적).
    if name in ROOT_ACTIVE:
        n = sidebar_pat.sub(lambda m, a=(sub or act): nav_style.sidebar_html(a), n, 1)
    elif sidebar_pat.search(n):
        sys.stderr.write('[compose] 경고: %s 는 ROOT_ACTIVE 미등록인데 스트립 보유 '
                         '— 정본 교체 대상에서 제외됨\n' % name)
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

# 하위 스트립 정합 검증 (2026-07-31 적대적 검증 반영: fail-closed 화)
#   - 스트립 2개 이상        -> 중단 (count=1 치환이라 뒤엣것이 구본으로 남는다)
#   - 스트립 1개 & 정본 불일치 -> 중단
#   - 그룹 children 이 없는데 스트립 존재 -> 중단
#   - 스트립 0개             -> 통과. hotels/taiwan 처럼 애초에 스트립을 굽지 않는
#                              페이지가 정상 존재하므로 '존재'를 강제하면 게시가 통째로
#                              막힌다. 대신 어떤 페이지가 0개였는지 로그로 남긴다.
_sb_none = []
for _pg, (_a, _s) in ROOT_ACTIVE.items():
    _pp = os.path.join(REL, _pg)
    if not os.path.exists(_pp):
        continue
    _want = nav_style.sidebar_html(_s or _a)
    _all = sidebar_pat.findall(open(_pp, encoding="utf-8").read())
    if len(_all) > 1:
        fail("%s: 하위 스트립 %d개 — 구본 잔존 가능" % (_pg, len(_all)))
    if not _all:
        _sb_none.append(_pg)
        continue
    if not _want:
        fail("%s: 그룹 children 이 없는데 하위 스트립 잔존" % _pg)
    if _all[0] != _want:
        fail("%s: 하위 스트립이 정본과 불일치" % _pg)
if _sb_none:
    sys.stdout.write("[compose] 스트립 없음(정상 가능): %s\n" % ", ".join(_sb_none))

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
        s = inject_before_head(s, JOURNAL_STRIP_CSS)
        s = inject_before_head(s, HASH_ACTIVE_JS)
        s = s.replace('</nav>', '</nav>' + JOURNAL_STRIP, 1)   # 스트립 = nav 바로 아래

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
