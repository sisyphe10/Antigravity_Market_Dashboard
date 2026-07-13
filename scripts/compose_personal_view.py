#!/usr/bin/env python3
"""compose_personal_view.py — 게시 스냅숏의 개인용 뷰 합성 (통합 설계 unified_design_claude.md §3.2, 옵션 a).

publish_snapshot.sh 가 새 릴리스 디렉토리(argv[1])를 rsync 한 직후 호출. 두 repo·GitHub 산출물 불변,
모든 가공은 스냅숏 사본에서만. Sisyphe 페이지는 매 실행 sisyphe_plain 원본에서 새로 복사되므로 주입은 항상 pristine 기준.

AoE 페이지(11) topnav: WRAP 제거 + Wiki(Architecture 앞) + Invest(->journal) + Sisyphe(맨 오른쪽·아이보리 배경, 단일 탭).
Sisyphe index/dashboard: Invest pill 제거, ←AoE pill 맨 오른쪽. journal: topnav 를 AoE 세트로 교체(Invest 활성).
전 Sisyphe 페이지: AoE 통일 CSS + 사이드바 액센트 녹색 + 랜딩 브랜드(index). 검증 실패 시 exit1 -> 세대 폐기.
"""
import os, re, sys, glob, shutil

REL = sys.argv[1]
SISYPHE_PLAIN = os.environ.get("SISYPHE_PLAIN", "/Users/sisyphe/srv/sisyphe_plain")
SISYPHE_PAGES = ("index.html", "dashboard.html", "journal.html")
NAV_END = '</div></div></nav>'

# ---- AoE 페이지 주입 fragment ----
WIKI_ITEM = '<div class="topnav-item"><a href="/wiki/" class="topnav-tab">Wiki</a></div>'
INVEST_ITEM = '<div class="topnav-item"><a href="/sisyphe/journal.html" class="topnav-tab">Invest</a></div>'
SISYPHE_ITEM = '<div class="topnav-item sisyphe-item"><a href="/sisyphe/index.html" class="topnav-tab sisyphe-tab">Sisyphe</a></div>'
# 구버전(드롭다운형) Sisyphe 아이템 — copy-current 입력 정규화용 제거 대상
OLD_SISYPHE_DROPDOWN = ('<div class="topnav-item"><a href="/sisyphe/index.html" class="topnav-tab">Sisyphe</a>'
                        '<div class="topnav-dropdown"><a href="/sisyphe/dashboard.html" class="topnav-sub">가계부·운동</a>'
                        '<a href="/sisyphe/journal.html" class="topnav-sub">투자일지</a></div></div>')
# AoE 페이지: Sisyphe 탭 우측 정렬 + 아이보리 배경(Sisyphe 아이덴티티, 은은)
AOE_PERSONAL_CSS = (
    '<style id="aoe-personal-nav">'
    '.topnav-tabs .topnav-item.sisyphe-item{margin-left:auto}'
    '.topnav-tab.sisyphe-tab{background:#faf3e3;border-color:#e6d9b8;color:#6b5a2a}'
    '.topnav-tab.sisyphe-tab:hover{background:#f3e8cf;border-color:#d9c48f;color:#5e4a1a}'
    '</style>'
)

# ---- Sisyphe 페이지 주입/치환 ----
AOE_BACK = '<a href="/" class="topnav-tab aoe-back"><span class="icon">←</span>AoE</a>'
INDEX_BRAND = '<a href="index.html" class="topnav-brand">Sisyphe</a>'
INVEST_PILL = '<a href="journal.html" class="topnav-tab t-journal"><span class="icon">\U0001F4DD</span>Invest</a>'
# journal: topnav 전체를 AoE 세트로 교체(원 wrapper 유지 -> 레이아웃 CSS 그대로). 고정 사이드바(200px)가 좌상단을
# 덮으므로 journal 한정 offset(padding-left)로 콘텐츠를 사이드바 우측으로 밀어 브랜드/탭 가림 방지.
NEW_JOURNAL_NAV = (
    '<nav class="topnav">\n    <div class="topnav-inner"><a href="/" class="topnav-brand">AoE</a>\n'
    '        <div class="topnav-tabs">\n'
    '            <a href="/market.html" class="topnav-tab">Market</a>\n'
    '            <a href="/wiki/" class="topnav-tab">Wiki</a>\n'
    '            <a href="/architecture.html" class="topnav-tab">Architecture</a>\n'
    '            <a href="/sisyphe/journal.html" class="topnav-tab active">Invest</a>\n'
    '            <a href="/sisyphe/index.html" class="topnav-tab sisyphe-tab">Sisyphe</a>\n'
    '        </div>\n    </div>\n</nav>'
)
JOURNAL_OFFSET = (
    '<style id="aoe-journal-offset">'
    'nav.topnav .topnav-inner{max-width:none;padding-left:228px;padding-right:24px}'
    '@media(max-width:900px){nav.topnav .topnav-inner{padding-left:12px;padding-right:12px}}'
    '</style>'
)
# index/dashboard 한정: Sisyphe 구역 표시용 은은한 웜톤 nav 바 (통일 CSS 뒤 주입 -> 흰색 상회).
# journal 은 AoE 세트(=AoE 구역)라 흰색 유지. "약간"만 다르게 — Sisyphe 탭 배경(#faf3e3)과 같은 계열.
SISYPHE_WARM_BAR = '<style id="sisyphe-warm-bar">nav.topnav{background:#fbf8ef;border-bottom-color:#ece4d3}</style>'

# AoE 정본(create_dashboard top_nav_html / sidebar, 픽셀통일)과 일치시키는 override — Sisyphe 페이지에만 주입.
NAV_UNIFY = (
    '<style id="aoe-nav-unify">'
    'nav.topnav{background:#fff;border-bottom-color:#e5e7eb}'
    'nav.topnav .topnav-inner{max-width:1400px;box-sizing:border-box}'
    'nav.topnav .topnav-tab,nav.topnav .topnav-tab.t-journal,nav.topnav .topnav-tab.t-ledger,'
    'nav.topnav .topnav-tab.t-fitness,nav.topnav .topnav-tab.t-workout,nav.topnav .topnav-tab.t-sheet'
    '{box-sizing:border-box;gap:6px;justify-content:center;color:#444;border-color:#d1d5db;background:#fff}'
    'nav.topnav .topnav-tab:hover,nav.topnav .topnav-tab.t-journal:hover,nav.topnav .topnav-tab.t-ledger:hover,'
    'nav.topnav .topnav-tab.t-fitness:hover,nav.topnav .topnav-tab.t-workout:hover,nav.topnav .topnav-tab.t-sheet:hover'
    '{color:#111;border-color:#2d7a3a;background:#f0f7f2}'
    'nav.topnav .topnav-tab.active{color:#fff;border-color:#2d7a3a;background:#2d7a3a}'
    'nav.topnav .topnav-tab.aoe-back{margin-left:auto}'
    'nav.topnav .topnav-tab.sisyphe-tab{margin-left:auto;background:#faf3e3;border-color:#e6d9b8;color:#6b5a2a}'
    'nav.topnav .topnav-tab.sisyphe-tab:hover{background:#f3e8cf;border-color:#d9c48f;color:#5e4a1a}'
    '.topnav-brand,.sidebar-brand{color:#111}'
    '.topnav-brand:hover,.sidebar-brand:hover{color:#2d7a3a}'
    '.sidebar{background:#fff;border-right-color:#e5e7eb}'
    '.sidebar-brand{background:#fff;border-bottom-color:#e5e7eb}'
    '.sidebar .sidebar-link{color:#444}'
    '.sidebar .sidebar-link:hover{background:#f0f7f2;color:#2d7a3a;border-color:#2d7a3a}'
    '.sidebar .sidebar-link.active{background:transparent;color:#2d7a3a;border-color:#2d7a3a}'
    'body{background:#f8f9fa}'
    '</style>'
)

item_pat = re.compile(r'<div class="topnav-item"><a href="wrap\.html"[^>]*>.*?</div></div>', re.S)
link_pat = re.compile(r'<a[^>]*href="wrap\.html[^"]*"[^>]*>.*?</a>\s*', re.S)
arch_pat = re.compile(r'<div class="topnav-item"><a href="architecture\.html"')
tabs_pat = re.compile(r'<div class="topnav-tabs">')
inner_pat = re.compile(r'<div class="topnav-inner">')
jnav_pat = re.compile(r'<nav class="topnav">.*?</nav>', re.S)


def fail(msg):
    sys.stderr.write("[compose] FAIL: %s\n" % msg)
    sys.exit(1)


def inject_before_head(s, frag):
    i = s.lower().find("</head>")
    if i == -1:
        return None
    return s[:i] + frag + s[i:]


# ===== 1) AoE 페이지: WRAP 제거 + topnav 재구성 (Wiki / Invest / Sisyphe 우측) =====
wrap = os.path.join(REL, "wrap.html")
if os.path.exists(wrap):
    os.remove(wrap)
for f in glob.glob(os.path.join(REL, "*.html")):
    s = open(f, encoding="utf-8").read()
    n = item_pat.sub("", s)
    n = link_pat.sub("", n)
    # 정규화: 기존 주입 fragment 제거(clean 입력이면 무동작)
    for frag in (WIKI_ITEM, INVEST_ITEM, SISYPHE_ITEM, OLD_SISYPHE_DROPDOWN):
        n = n.replace(frag, "")
    # Wiki 를 Architecture 앞에(없으면 nav 끝 폴백)
    m = arch_pat.search(n)
    if m:
        n = n[:m.start()] + WIKI_ITEM + n[m.start():]
    elif NAV_END in n:
        n = n.replace(NAV_END, WIKI_ITEM + NAV_END, 1)
    # Invest + Sisyphe 를 nav 끝에(Sisyphe 는 margin-left:auto 로 맨 오른쪽).
    # 가드는 nav 마크업 전용 마커('sisyphe-tab">Sisyphe')로 — 'sisyphe-tab' 만 보면 주입된 CSS(aoe-personal-nav)에
    # 걸려 copy-current 재실행 시 재주입이 막힘. 정규화가 SISYPHE_ITEM 을 지웠으므로 마크업 마커는 사라진 상태.
    if NAV_END in n and 'sisyphe-tab">Sisyphe' not in n:
        n = n.replace(NAV_END, INVEST_ITEM + SISYPHE_ITEM + NAV_END, 1)
    # AoE 개인 nav CSS
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
    if 'sisyphe-tab">Sisyphe' not in t:
        fail("index.html: Sisyphe 탭(우측) 주입 실패")
    if '/sisyphe/journal.html" class="topnav-tab">Invest' not in t:
        fail("index.html: Invest 탭 주입 실패")
    if 'topnav-sub">가계부' in t:
        fail("index.html: 구 Sisyphe 드롭다운 잔존")

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

    if name == "journal.html":
        # topnav 전체를 AoE 세트로 교체
        m = jnav_pat.search(s)
        if not m:
            fail("sisyphe/journal.html: topnav 블록 없음 — 교체 불가")
        s = s[:m.start()] + NEW_JOURNAL_NAV + s[m.end():]
    else:
        # index/dashboard: Invest pill 제거 + ←AoE 를 topnav-tabs 의 '마지막 자식'으로 주입.
        # (첫 자식에 margin-left:auto 를 주면 뒤 pill 들까지 통째로 우측으로 밀리므로 반드시 마지막에 배치.)
        # topnav-tabs 는 중첩 div 없이 <a> pill 만 담으므로 여는 태그 뒤 첫 </div> 가 닫는 태그다.
        s = s.replace(INVEST_PILL, "")
        if "aoe-back" not in s:
            m = tabs_pat.search(s)
            if not m:
                fail("sisyphe/%s: topnav-tabs 앵커 없음" % name)
            close = s.index("</div>", m.end())
            s = s[:close] + AOE_BACK + s[close:]
        if name == "index.html" and 'topnav-brand">Sisyphe' not in s:
            m = inner_pat.search(s)
            if not m:
                fail("sisyphe/index.html: topnav-inner 앵커 없음")
            s = s[:m.end()] + INDEX_BRAND + s[m.end():]

    # 통일 CSS(전 Sisyphe 페이지)
    r = inject_before_head(s, NAV_UNIFY)
    if r is None:
        fail("sisyphe/%s: </head> 없음" % name)
    s = r
    # journal 한정 nav offset(사이드바 우측으로) — 통일 CSS 뒤에 와야 max-width 상회
    if name == "journal.html":
        s = inject_before_head(s, JOURNAL_OFFSET)
    else:
        # index/dashboard: Sisyphe 구역 웜톤 nav 바
        s = inject_before_head(s, SISYPHE_WARM_BAR)

    open(p, "w", encoding="utf-8").write(s)

    # ---- 검증 ----
    fin = open(p, encoding="utf-8").read()
    if 'id="aoe-nav-unify"' not in fin:
        fail("sisyphe/%s: 통일 CSS 검증 실패" % name)
    if name == "journal.html":
        if 'class="topnav-tab active">Invest' not in fin:
            fail("sisyphe/journal.html: AoE nav(Invest 활성) 검증 실패")
        if 'sisyphe-tab">Sisyphe' not in fin or 'topnav-brand">AoE' not in fin:
            fail("sisyphe/journal.html: AoE nav(브랜드/Sisyphe 탭) 검증 실패")
        if 'dashboard.html#ledger' in fin:
            fail("sisyphe/journal.html: 구 Sisyphe nav 잔존")
        if 'id="aoe-journal-offset"' not in fin:
            fail("sisyphe/journal.html: nav offset 검증 실패")
        if 'sisyphe-warm-bar' in fin:
            fail("sisyphe/journal.html: 웜톤 바 오주입(AoE 구역=흰색이어야)")
    else:
        if INVEST_PILL in fin:
            fail("sisyphe/%s: Invest pill 제거 실패" % name)
        # ←AoE 가 topnav-tabs 의 '마지막 자식'인지 마크업 순서로 검증(CSS 존재만으론 시각 결과 보장 못 함)
        mt = tabs_pat.search(fin)
        tc = fin.index("</div>", mt.end())
        tabs_inner = fin[mt.end():tc]
        last_a = tabs_inner.rfind("<a ")
        if last_a < 0 or "aoe-back" not in tabs_inner[last_a:]:
            fail("sisyphe/%s: ←AoE 가 topnav-tabs 마지막 자식 아님(순서 오류)" % name)
        if 'id="sisyphe-warm-bar"' not in fin:
            fail("sisyphe/%s: 웜톤 nav 바 주입 실패" % name)
        if name == "index.html" and 'topnav-brand">Sisyphe' not in fin:
            fail("sisyphe/index.html: 랜딩 브랜드 검증 실패")

sys.stdout.write("[compose] OK: AoE nav 재구성(Invest·Sisyphe 우측) + Sisyphe 3페이지(journal=AoE세트) 합성 (%s)\n"
                 % os.path.basename(REL))
