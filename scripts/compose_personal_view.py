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

REL = sys.argv[1]
SISYPHE_PLAIN = os.environ.get("SISYPHE_PLAIN", "/Users/sisyphe/srv/sisyphe_plain")
SISYPHE_PAGES = ("index.html", "dashboard.html", "journal.html", "memento.html")
NAV_END = '</div></div></nav>'

# ---- AoE 페이지 주입 fragment ----
# 2026-07-16 정렬 확정: 좌 Watchlist·Market·Invest·Memento·Ledger / 우(margin-left:auto) Wiki·Architecture
WATCHLIST_ITEM = '<div class="topnav-item"><a href="/watchlist/" class="topnav-tab">Watchlist</a></div>'
WIKI_ITEM = '<div class="topnav-item right-group"><a href="/wiki/" class="topnav-tab">Wiki</a></div>'
INVEST_ITEM = '<div class="topnav-item"><a href="/sisyphe/journal.html" class="topnav-tab">Invest</a></div>'
MEMENTO_ITEM = '<div class="topnav-item"><a href="/sisyphe/memento.html" class="topnav-tab">Memento</a></div>'
LEDGER_ITEM = '<div class="topnav-item"><a href="/sisyphe/dashboard.html" class="topnav-tab">Ledger</a></div>'
ARCH_ITEM_PLAIN = '<div class="topnav-item"><a href="architecture.html" class="topnav-tab">Architecture</a></div>'
# 구세대 fragment — copy-current 입력 정규화용 제거 대상
OLD_WIKI_ITEM = '<div class="topnav-item"><a href="/wiki/" class="topnav-tab">Wiki</a></div>'
OLD_INVEST_ITEM_P1 = '<div class="topnav-item personal-first"><a href="/sisyphe/journal.html" class="topnav-tab">Invest</a></div>'
OLD_SISYPHE_ITEM = '<div class="topnav-item sisyphe-item"><a href="/sisyphe/index.html" class="topnav-tab sisyphe-tab">Sisyphe</a></div>'
OLD_SISYPHE_DROPDOWN = ('<div class="topnav-item"><a href="/sisyphe/index.html" class="topnav-tab">Sisyphe</a>'
                        '<div class="topnav-dropdown"><a href="/sisyphe/dashboard.html" class="topnav-sub">가계부·운동</a>'
                        '<a href="/sisyphe/journal.html" class="topnav-sub">투자일지</a></div></div>')
AOE_PERSONAL_CSS = ('<style id="aoe-personal-nav">'
                    '.topnav-tabs .topnav-item.right-group{margin-left:auto}'
                    '</style>')

# ---- Sisyphe 페이지: topnav 를 AoE 세트로 교체 ----
def sisyphe_aoe_nav(active):
    def cls(name):
        return 'topnav-tab active' if name == active else 'topnav-tab'
    return (
        '<nav class="topnav">\n    <div class="topnav-inner"><a href="/" class="topnav-brand">AoE</a>\n'
        '        <div class="topnav-tabs">\n'
        '            <a href="/watchlist/" class="topnav-tab">Watchlist</a>\n'
        '            <a href="/market.html" class="topnav-tab">Market</a>\n'
        '            <a href="/sisyphe/journal.html" class="%s">Invest</a>\n'
        '            <a href="/sisyphe/memento.html" class="%s">Memento</a>\n'
        '            <a href="/sisyphe/dashboard.html" class="%s">Ledger</a>\n'
        '            <a href="/wiki/" class="topnav-tab" style="margin-left:auto">Wiki</a>\n'
        '            <a href="/architecture.html" class="topnav-tab">Architecture</a>\n'
        '        </div>\n    </div>\n</nav>'
    ) % (cls('invest'), cls('memento'), cls('ledger'))

ACTIVE_OF = {'journal.html': 'invest', 'dashboard.html': 'ledger', 'memento.html': 'memento'}
# 1안(2026-07-16 사용자 확정): 사이드바 전면 제거 — journal(서브내비=본문 tab-bar)·dashboard 공통.
# 본문 좌측 오프셋도 해제. (구 JOURNAL_OFFSET·CORNER_BRAND 는 사이드바와 함께 폐기)
NO_SIDEBAR = '<style id="aoe-nosidebar">.sidebar{display:none}.has-sidebar{padding-left:24px !important}</style>'
JOURNAL_OFFSET = (
    '<style id="aoe-journal-offset">'
    'nav.topnav .topnav-inner{max-width:none;padding-left:228px;padding-right:24px}'
    '@media(max-width:900px){nav.topnav .topnav-inner{padding-left:12px;padding-right:12px}}'
    '</style>'
)

# AoE 정본(create_dashboard top_nav_html / sidebar, 픽셀통일)과 일치시키는 override — Sisyphe 페이지에만 주입.
# 2026-07-16 블룸버그 다크 통일: 바 #101418·하단 2px 그린 라인·액티브=와인 레드 채움(#991B1B)·높이 54px.
NAV_UNIFY = (
    '<style id="aoe-nav-unify">'
    'nav.topnav{background:#101418;border-bottom:2px solid #2d7a3a}'
    'nav.topnav .topnav-inner{max-width:1400px;box-sizing:border-box;align-items:stretch;height:54px;gap:36px}'
    'nav.topnav .topnav-tabs{display:flex;flex:1;gap:2px;align-items:stretch}'
    'nav.topnav .topnav-tab,nav.topnav .topnav-tab.t-journal,nav.topnav .topnav-tab.t-ledger,'
    'nav.topnav .topnav-tab.t-fitness,nav.topnav .topnav-tab.t-workout,nav.topnav .topnav-tab.t-sheet'
    '{box-sizing:border-box;display:inline-flex;align-items:center;gap:6px;justify-content:center;'
    'min-width:0;padding:0 18px;color:#9aa4ae;border:none;border-radius:0;background:transparent;'
    'font-size:0.92rem;font-weight:600;letter-spacing:0.3px;transition:color 0.12s,background 0.12s}'
    'nav.topnav .topnav-tab:hover,nav.topnav .topnav-tab.t-journal:hover,nav.topnav .topnav-tab.t-ledger:hover,'
    'nav.topnav .topnav-tab.t-fitness:hover,nav.topnav .topnav-tab.t-workout:hover,nav.topnav .topnav-tab.t-sheet:hover'
    '{color:#fff;border:none;background:#1a2027}'
    'nav.topnav .topnav-tab.active{color:#fff;border:none;background:#991B1B;font-weight:700}'
    'nav.topnav .topnav-brand{color:#fff;font-size:1.1rem;letter-spacing:3.5px;align-self:center}'
    'nav.topnav .topnav-brand:hover{color:#7fc78f}'
    # 좌상단 사이드바 배지 = 다크 nav 와 한 몸(같은 높이·색·그린 라인) — AoE 브랜드 색 통일(2026-07-16)
    # right:-1px = 사이드바 밝은 border-right 가 배지 구간에서 흰 세로선으로 비치는 것 차폐(배지가 1px 덮음)
    '.sidebar-brand{height:54px;background:#101418;color:#fff;font-size:1.1rem;font-weight:800;'
    'letter-spacing:3.5px;border-bottom:2px solid #2d7a3a;right:-1px}'
    '.sidebar-brand:hover{color:#7fc78f}'
    # 사이드바 다크 A안(2026-07-16): 다크 bg + 좌측 3px 레드 인디케이터 (nav 와 한 세트)
    '.sidebar{background:#101418;border-right-color:#2a323b}'
    '.sidebar .sidebar-link{color:#9aa4ae;font-size:0.9rem;padding:11px 14px;margin-bottom:2px;'
    'border:none;border-left:3px solid transparent;border-radius:0;text-align:left}'
    '.sidebar .sidebar-link:hover{background:#1a2027;color:#fff;border-color:transparent;border-left-color:transparent}'
    '.sidebar .sidebar-link.active{background:#1c1416;color:#fff;font-weight:700;border-left-color:#991B1B}'
    'body{background:#f8f9fa}'
    '</style>'
)

item_pat = re.compile(r'<div class="topnav-item"><a href="wrap\.html"[^>]*>.*?</div></div>', re.S)
link_pat = re.compile(r'<a[^>]*href="wrap\.html[^"]*"[^>]*>.*?</a>\s*', re.S)
arch_pat = re.compile(r'<div class="topnav-item"><a href="architecture\.html" class="topnav-tab(?: active)?">Architecture</a></div>')
market_pat = re.compile(r'<div class="topnav-item"><a href="market\.html"')
tabs_pat = re.compile(r'<div class="topnav-tabs">')
jnav_pat = re.compile(r'<nav class="topnav">.*?</nav>', re.S)
personal_css_pat = re.compile(r'<style id="aoe-personal-nav">.*?</style>', re.S)
warm_bar_pat = re.compile(r'<style id="sisyphe-warm-bar">.*?</style>', re.S)


def fail(msg):
    sys.stderr.write("[compose] FAIL: %s\n" % msg)
    sys.exit(1)


def inject_before_head(s, frag):
    i = s.lower().find("</head>")
    if i == -1:
        return None
    return s[:i] + frag + s[i:]


# ===== 1) AoE 페이지: WRAP 제거 + topnav 재구성 (좌: Watchlist·Market·Wiki / 우: Invest·Memento·Ledger·Architecture) =====
wrap = os.path.join(REL, "wrap.html")
if os.path.exists(wrap):
    os.remove(wrap)
for f in glob.glob(os.path.join(REL, "*.html")):
    s = open(f, encoding="utf-8").read()
    n = item_pat.sub("", s)
    n = link_pat.sub("", n)
    # 정규화: 기존 주입 fragment·구 Sisyphe 잔재 제거(clean 입력이면 무동작)
    for frag in (WATCHLIST_ITEM, WIKI_ITEM, OLD_WIKI_ITEM, INVEST_ITEM, OLD_INVEST_ITEM_P1,
                 MEMENTO_ITEM, LEDGER_ITEM, OLD_SISYPHE_ITEM, OLD_SISYPHE_DROPDOWN):
        n = n.replace(frag, "")
    n = personal_css_pat.sub("", n)
    # Architecture 원본 아이템 추출(있으면) — 우측 그룹 맨 끝으로 이동. active 상태 보존.
    m = arch_pat.search(n)
    if m:
        arch_html = m.group(0)
        n = n[:m.start()] + n[m.end():]
    else:
        arch_html = ARCH_ITEM_PLAIN
    # Watchlist 를 Market 앞에(없으면 tabs 여는 태그 직후 폴백) — ts.net 첫화면(관심종목 시세판)
    m = market_pat.search(n)
    if m:
        n = n[:m.start()] + WATCHLIST_ITEM + n[m.start():]
    else:
        mt = tabs_pat.search(n)
        if mt:
            n = n[:mt.end()] + WATCHLIST_ITEM + n[mt.end():]
    # 좌측 잔여 그룹(Invest·Memento·Ledger) + 우측 그룹(Wiki·Architecture) 을 nav 끝에.
    # (정규화 후 남은 기존 아이템 = Watchlist·Market 뿐이므로 append 순서가 곧 좌측 순서)
    # 가드: 이미 Memento 마크업이 있으면 재주입 금지(정규화가 지웠으므로 통상 미존재).
    if NAV_END in n and 'topnav-tab">Memento' not in n:
        n = n.replace(NAV_END, INVEST_ITEM + MEMENTO_ITEM + LEDGER_ITEM + WIKI_ITEM + arch_html + NAV_END, 1)
    if 'id="aoe-personal-nav"' not in n:
        r = inject_before_head(n, AOE_PERSONAL_CSS)
        if r is not None:
            n = r
    if n != s:
        open(f, "w", encoding="utf-8").write(n)

if os.path.exists(wrap):
    fail("wrap.html 잔존")
idx = os.path.join(REL, "index.html")
if os.path.exists(idx):
    t = open(idx, encoding="utf-8").read()
    for marker, what in ((WATCHLIST_ITEM, 'Watchlist'), (WIKI_ITEM, 'Wiki(우측)'), (INVEST_ITEM, 'Invest'),
                         (MEMENTO_ITEM, 'Memento'), (LEDGER_ITEM, 'Ledger')):
        if marker not in t:
            fail("index.html: %s 탭 주입 실패" % what)
    # 순서: Watchlist < Market < Invest < Memento < Ledger < Wiki(right-group) < Architecture
    # ★'right-group' 단독 검색 금지 — head 의 aoe-personal-nav CSS(.topnav-item.right-group)가
    #   nav 마크업보다 먼저 매칭돼 순서 검증이 항상 실패(2026-07-16 게시 동결 사고). 마크업 전용
    #   마커 'topnav-item right-group'(class 속성, 공백 구분)만 사용.
    pos = [t.find('>Watchlist<'), t.find('>Market<'), t.find('>Invest<'), t.find('>Memento<'),
           t.find('>Ledger<'), t.find('topnav-item right-group'), t.rfind('>Architecture<')]
    if -1 in pos or pos != sorted(pos):
        fail("index.html: 탭 순서 오류 %s" % pos)
    if 'sisyphe-tab' in t or 'topnav-sub">가계부' in t:
        fail("index.html: 구 Sisyphe 탭 잔존")

# ===== 2) Sisyphe 평문 합성 (매 실행 pristine 복사) =====
dst = os.path.join(REL, "sisyphe")
os.makedirs(dst, exist_ok=True)
for name in SISYPHE_PAGES:
    src = os.path.join(SISYPHE_PLAIN, name)
    if not os.path.isfile(src) or os.path.getsize(src) == 0:
        fail("sisyphe 평문 소스 없음/빈파일: %s" % src)
    shutil.copyfile(src, os.path.join(dst, name))

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

    # topnav 를 AoE 세트로 교체 (journal/dashboard/memento 공통)
    m = jnav_pat.search(s)
    if not m:
        fail("sisyphe/%s: topnav 블록 없음 — 교체 불가" % name)
    s = s[:m.start()] + sisyphe_aoe_nav(ACTIVE_OF[name]) + s[m.end():]
    s = warm_bar_pat.sub("", s)

    r = inject_before_head(s, NAV_UNIFY)
    if r is None:
        fail("sisyphe/%s: </head> 없음" % name)
    s = r
    if name in ("journal.html", "dashboard.html"):
        s = inject_before_head(s, NO_SIDEBAR)

    open(p, "w", encoding="utf-8").write(s)

    # ---- 검증 ----
    fin = open(p, encoding="utf-8").read()
    if 'id="aoe-nav-unify"' not in fin:
        fail("sisyphe/%s: 통일 CSS 검증 실패" % name)
    if 'topnav-brand">AoE' not in fin:
        fail("sisyphe/%s: AoE nav 교체 검증 실패" % name)
    active_label = {'invest': 'Invest', 'memento': 'Memento', 'ledger': 'Ledger'}[ACTIVE_OF[name]]
    chk = fin.replace(' style="margin-left:auto"', '')
    if ('class="topnav-tab active">%s</a>' % active_label) not in chk:
        fail("sisyphe/%s: 활성 탭(%s) 검증 실패" % (name, active_label))
    if 'sisyphe-warm-bar' in fin:
        fail("sisyphe/%s: 웜톤 바 잔존" % name)
    if name in ("journal.html", "dashboard.html") and 'id="aoe-nosidebar"' not in fin:
        fail("sisyphe/%s: 사이드바 제거 검증 실패" % name)

sys.stdout.write("[compose] OK: 단일 AoE nav(좌 Watchlist·Market·Invest·Memento·Ledger / 우 Wiki·Arch) + Sisyphe 4페이지 합성 (%s)\n"
                 % os.path.basename(REL))
