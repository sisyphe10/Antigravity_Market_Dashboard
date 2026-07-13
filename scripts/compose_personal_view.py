#!/usr/bin/env python3
"""compose_personal_view.py — 게시 스냅숏의 개인용 뷰 합성 (통합 설계 unified_design_claude.md §3.2, 옵션 a).

publish_snapshot.sh 가 새 릴리스 디렉토리(argv[1])를 rsync 한 직후 호출한다.
두 repo(Antigravity·Sisyphe) 원본과 GitHub(팀원용) 산출물은 불변 — 모든 가공은 이 스냅숏 사본에서만.

수행
  1) WRAP 제거   : wrap.html 삭제 + 전 AoE 페이지의 wrap topnav 아이템/링크 제거
  2) 정방향 nav  : AoE topnav 에 Wiki·Sisyphe 그룹 주입 (→ /sisyphe/...) — 멱등
  3) Sisyphe 합성: ~/srv/sisyphe_plain 평문 3페이지를 <REL>/sisyphe/ 로 복사 (평문·데이터는 런타임 Sheets fetch)
  4) 역방향 nav  : Sisyphe 3페이지 topnav 에 AoE 복귀 pill 주입 (→ /) — 멱등
  5) AoE 통일 CSS: Sisyphe topnav·chrome 색/스타일을 AoE 정본(create_dashboard top_nav_html)과 일치시키는
                   override <style>를 </head> 앞에 주입 — 멱등. 색/pill/브랜드 액센트만(레이아웃 구조 불변).
  6) 검증        : sisyphe 페이지 존재·staticrypt 흔적 0·역방향 nav·통일 CSS 주입 확인. 실패 시 exit1 → 세대 폐기.
"""
import os, re, sys, glob, shutil

REL = sys.argv[1]
SISYPHE_PLAIN = os.environ.get("SISYPHE_PLAIN", "/Users/sisyphe/srv/sisyphe_plain")
SISYPHE_PAGES = ("index.html", "dashboard.html", "journal.html")

# 정방향(AoE→Sisyphe) fragment — 탭 순서 Market > Wiki > Sisyphe > Architecture (기존 1.5단계와 동일)
INJECT = ('<div class="topnav-item"><a href="/wiki/" class="topnav-tab">Wiki</a></div>'
          '<div class="topnav-item"><a href="/sisyphe/index.html" class="topnav-tab">Sisyphe</a>'
          '<div class="topnav-dropdown">'
          '<a href="/sisyphe/dashboard.html" class="topnav-sub">가계부·운동</a>'
          '<a href="/sisyphe/journal.html" class="topnav-sub">투자일지</a>'
          '</div></div>')
NAV_END = '</div></div></nav>'
# 역방향(Sisyphe→AoE) 복귀 pill — 기존 .topnav-tab 컴포넌트 재사용(새 스타일 없음). aoe-back=멱등·검증 마커.
AOE_BACK = '<a href="/" class="topnav-tab aoe-back"><span class="icon">←</span>AoE</a>'
STATICRYPT_MARKERS = ("staticrypt", "encryptedmsg", "cryptoengine")

# AoE 정본 topnav 값(create_dashboard top_nav_html, 2026-07-12 픽셀통일)과 일치시키는 override.
# nav.topnav 특이도(요소+클래스)로 원본 규칙 확실 상회. 색·pill·브랜드 액센트·chrome 배경만 통일하고
# has-sidebar 오프셋(padding/margin/min-width) 등 레이아웃 구조는 건드리지 않는다(깨짐 방지).
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
    '.topnav-brand,.sidebar-brand{color:#111}'
    '.topnav-brand:hover,.sidebar-brand:hover{color:#2d7a3a}'
    '.sidebar{background:#fff;border-right-color:#e5e7eb}'
    '.sidebar-brand{background:#fff;border-bottom-color:#e5e7eb}'
    'body{background:#f8f9fa}'
    '</style>'
)

item_pat = re.compile(r'<div class="topnav-item"><a href="wrap\.html"[^>]*>.*?</div></div>', re.S)
link_pat = re.compile(r'<a[^>]*href="wrap\.html[^"]*"[^>]*>.*?</a>\s*', re.S)
arch_pat = re.compile(r'<div class="topnav-item"><a href="architecture\.html"')
tabs_pat = re.compile(r'<div class="topnav-tabs">')


def fail(msg):
    sys.stderr.write("[compose] FAIL: %s\n" % msg)
    sys.exit(1)


# --- 1)+2) AoE 페이지: WRAP 제거 + 정방향 nav 주입 (멱등) ---
wrap = os.path.join(REL, "wrap.html")
if os.path.exists(wrap):
    os.remove(wrap)
for f in glob.glob(os.path.join(REL, "*.html")):
    s = open(f, encoding="utf-8").read()
    n = item_pat.sub("", s)
    n = link_pat.sub("", n)
    if 'topnav-tab">Sisyphe' not in n:
        m = arch_pat.search(n)
        if m:
            n = n[:m.start()] + INJECT + n[m.start():]
        elif NAV_END in n:
            n = n.replace(NAV_END, INJECT + NAV_END, 1)
    if n != s:
        open(f, "w", encoding="utf-8").write(n)

if os.path.exists(wrap):
    fail("wrap.html 잔존")
idx = os.path.join(REL, "index.html")
if os.path.exists(idx) and 'topnav-tab">Sisyphe' not in open(idx, encoding="utf-8").read():
    fail("index.html: Sisyphe 탭 주입 실패")

# --- 3) Sisyphe 평문 합성 ---
dst = os.path.join(REL, "sisyphe")
os.makedirs(dst, exist_ok=True)
for name in SISYPHE_PAGES:
    src = os.path.join(SISYPHE_PLAIN, name)
    if not os.path.isfile(src) or os.path.getsize(src) == 0:
        fail("sisyphe 평문 소스 없음/빈파일: %s" % src)
    shutil.copyfile(src, os.path.join(dst, name))

# --- 4)+5) 역방향 nav + AoE 통일 CSS 주입 + 검증 (멱등, fail-closed) ---
for name in SISYPHE_PAGES:
    p = os.path.join(dst, name)
    s = open(p, encoding="utf-8").read()
    low = s.lower()
    for mk in STATICRYPT_MARKERS:
        if mk in low:
            fail("sisyphe/%s: staticrypt 흔적(%s) — 암호화본 오배치" % (name, mk))
    changed = False
    if "aoe-back" not in s:
        m = tabs_pat.search(s)
        if not m:
            fail("sisyphe/%s: topnav-tabs 앵커 없음 — 역방향 nav 주입 불가" % name)
        s = s[:m.end()] + AOE_BACK + s[m.end():]
        changed = True
    if "aoe-nav-unify" not in s:
        i = s.lower().find("</head>")
        if i == -1:
            fail("sisyphe/%s: </head> 없음 — 통일 CSS 주입 불가" % name)
        s = s[:i] + NAV_UNIFY + s[i:]
        changed = True
    if changed:
        open(p, "w", encoding="utf-8").write(s)
    final = open(p, encoding="utf-8").read()
    if 'class="topnav-tab aoe-back"' not in final:
        fail("sisyphe/%s: 역방향 nav 검증 실패" % name)
    if 'id="aoe-nav-unify"' not in final:
        fail("sisyphe/%s: AoE 통일 CSS 검증 실패" % name)

sys.stdout.write("[compose] OK: WRAP 제거 + 양방향 nav + AoE 통일 CSS + Sisyphe %d페이지 합성 (%s)\n"
                 % (len(SISYPHE_PAGES), os.path.basename(REL)))
