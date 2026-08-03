# -*- coding: utf-8 -*-
"""AoE 상단 네비게이션 정본 — 단일 출처 (2026-07-26 통일).

배경: 네비 CSS·마크업이 6곳(create_dashboard / create_architecture / webui server
Earnings·Wiki / quoteboard Watchlist / compose Sisyphe)에 독립 사본으로 존재해
폰트·크기·위치가 페이지마다 미묘하게 어긋났다 (예: 탭 1rem vs 0.92rem,
Earnings box-sizing 누락 28px 어긋남, architecture line-height 차이).

이 파일이 유일한 정본이다. 네비 스타일·탭 구성 수정은 반드시 여기서만 하고,
소비자별 반영 경로는 아래와 같다:
  - execution/create_dashboard.py      : TOP_NAV_CSS 가 NAV_CSS 를 포함 (재생성 시 반영)
  - execution/create_architecture.py   : NAV_CSS + nav_html('architecture') (재생성 시 반영)
  - datalake/webui/server.py           : import 후 기동 시 치환 (Earnings/Wiki, 재시작 시 반영)
  - quoteboard/server.py               : import 후 기동 시 치환 (Watchlist, 재시작 시 반영)
  - scripts/compose_personal_view.py   : 게시 스냅숏 전 페이지 nav 교체 (다음 publish 반영)

스타일 근거: AOE_STYLE_GUIDE.md (터미널 블랙+앰버). WRAP(gh-pages)은
.wrap-topnav / .wrap-strip 스코프가 전면 override 하므로 이 정본의 영향을 받지 않는다.
"""

PRETENDARD_STACK = "'Pretendard Variable', Pretendard, system-ui, -apple-system, sans-serif"
PRETENDARD_LINK = ('<link rel="stylesheet" href="https://cdn.jsdelivr.net/gh/orioncactus/'
                   'pretendard@v1.3.9/dist/web/variable/pretendardvariable.min.css">')

# ---- 로컬 벤더 자산 (2026-07-27 CDN 셀프호스팅, assets/vendor/) ----
# ts.net AoE 페이지 전용 절대경로. ★WRAP(gh-pages 프로젝트 사이트 = /repo/ 하위)은 절대경로가
# 깨지므로 wrap 구간은 CDN 유지 — wrap 코드에서 이 상수들을 쓰지 말 것.
VENDOR_PRETENDARD_CSS = '/assets/vendor/pretendard/pretendardvariable.min.css'
VENDOR_CHART_JS = '/assets/vendor/js/chart.umd.min.js'        # Chart.js v4.5.1 고정 (구 CDN 무버전)
VENDOR_HTML2CANVAS_JS = '/assets/vendor/js/html2canvas.min.js'  # 1.4.1
PRETENDARD_LINK_LOCAL = '<link rel="stylesheet" href="%s">' % VENDOR_PRETENDARD_CSS

# ---- 다크 팔레트 정본 (2026-07-26 확장) ----
# AOE_STYLE_GUIDE.md 팔레트 표의 코드 구현체. 색 변경은 반드시 여기서만 —
# compose(스냅숏 주입 CSS)·별도 앱 3종(Earnings/Wiki/Watchlist의 var(--aoe-*))이 파생.
# ※ 등락색은 다크용 밝은 톤 실사용값(#ff453a/#2e9bff)으로 확정 (가이드 구값 #ff5a5a/#5aa2ff 폐기).
PALETTE = {
    'bg':           '#0a0a0a',   # 페이지 배경
    'card':         '#111214',   # 카드/패널
    'card2':        '#14171b',   # 보조 패널 (하이라이트 컬럼 등)
    'nav-bg':       '#101418',   # 상단바
    'border':       '#27282b',   # 보더
    'input-bg':     '#141517',   # 입력·버튼류 배경
    'input-border': '#3a3b3e',   # 입력류 보더
    'hover':        '#191a1d',   # 행 hover
    'text':         '#d9dde2',   # 본문
    'muted':        '#8a919a',   # 뮤트 텍스트
    'amber':        '#fb8b1e',   # 강조 앰버
    'amber-bright': '#ffb45e',   # 밝은 앰버
    'th-bg':        '#1a1b1e',   # 표 헤더 배경
    'up':           '#ff453a',   # 상승 (다크용)
    'down':         '#2e9bff',   # 하락 (다크용)
    'hl-amber-bg':  '#4a2d0a', 'hl-amber-fg': '#ffb45e',   # 선택 하이라이트 ①앰버
    'hl1-bg': '#241a3d', 'hl1-fg': '#b9a1fc',              # ②바이올렛
    'hl2-bg': '#0a3038', 'hl2-fg': '#67e0f4',              # ③시안
    'hl3-bg': '#10301c', 'hl3-fg': '#4ade80',              # ④에메랄드
}
AMBER = PALETTE['amber']

# ---- Life WRAP 라이트 팔레트 정본 (2026-07-26) ----
# WRAP(팀 전용, gh-pages)은 라이트 테마 유지가 의도된 예외 — 다크 PALETTE 와 별도 정본.
# create_dashboard 의 WRAP 전용 구간이 var(--wrap-*) 로 참조, :root 선언은 wrap_page 에 주입.
WRAP_PALETTE = {
    'green':     '#2d7a3a',   # 브랜드 그린 (라인·활성)
    'green-bg':  '#f0f7f2',   # 그린 틴트 배경
    'bg':        '#f8f9fa',   # 페이지 배경
    'border':    '#e5e7eb',   # 옅은 보더
    'border2':   '#d1d5db',   # 진한 보더 (버튼류)
    'neutral':   '#f3f4f6',   # 중립 배경
    'red':       '#dc2626',   # 주요 액션 (최종저장 등)
    'blue':      '#2563eb',   # 보조 액션
}
WRAP_CSS_VARS = ':root{' + ';'.join(
    '--wrap-%s:%s' % (k, v) for k, v in WRAP_PALETTE.items()) + '}'

# 별도 앱용 CSS 변수 선언 — 앱 CSS 는 var(--aoe-*) 로 참조, 기동 시 이 블록이 치환된다
PALETTE_CSS_VARS = ':root{' + ';'.join(
    '--aoe-%s:%s' % (k, v) for k, v in PALETTE.items()) + '}'

# ★★NAV 변경 시 필수 후속 (2026-08-03 사용자 반복 지적으로 명문화) ─────────────
#   이 파일은 정본이지만, 런타임 데몬은 기동 시 1회만 이 정본을 굽는다.
#   NAV_ITEMS·CSS 를 바꿨으면 반드시:
#     1) sudo launchctl kickstart -k system/com.antigravity.watchlist      (/watchlist 시세판)
#     2) sudo launchctl kickstart -k system/com.antigravity.datalake-webui (/wiki·/wiki/library)
#     3) bash scripts/publish_snapshot.sh                                  (스냅숏 페이지)
#   그리고 /watchlist·/wiki·/wiki/library·본체·/sisyphe 전 표면에서 탭 구성을 실측 검증한다.
# ──────────────────────────────────────────────────────────────────────

BRAND = 'AGE OF EMERGENCE'
BRAND_HREF = '/index.html'   # Caddy가 /watchlist/ 로 redirect (랜딩 폐지 후 동작 동일)

# ---- 정본 탭 구성 (2026-07-22 순서 개편 반영: 좌 Watchlist~Wiki / 우 Memento·Ledger·Arch) ----
# (key, href, label, right_group, children[(key, href, label)])
NAV_ITEMS = [
    ('watchlist',    '/watchlist/',                  'Watchlist',    False, [
        # 2026-07-31 사용자: Universe·Universe Lab 을 Market → Watchlist 하위로 이동
        ('watchlist',    '/watchlist/',        'Quotes'),
        ('universe',     '/universe.html',     'Universe'),
        ('universe_lab', '/universe_lab.html', 'Universe Lab'),
    ]),
    ('market',       '/market.html',                 'Market',       False, [
        ('market',       '/market.html',       'Data'),
        ('featured',     '/featured.html',     'Featured'),
        ('market_alert', '/market_alert.html', '투자유의종목'),
        ('etf',          '/etf.html',          'ETF'),
        ('seibro',       '/seibro.html',       'SEIBro'),
    ]),
    # 2026-08-03 사용자: Weekly 상단 탭을 Journal 하위로 병합 — 드롭다운·하위 스트립 = Daily/Weekly
    ('journal',      '/sisyphe/journal.html',        'Journal',      False, [
        ('journal_daily',  '/sisyphe/journal.html',        'Daily'),
        ('journal_weekly', '/sisyphe/journal.html#weekly', 'Weekly'),
    ]),
    ('earnings',     '/wiki/library',                'Earnings',     False, None),
    ('wiki',         '/wiki/',                       'Wiki',         False, None),
    ('memento',      '/sisyphe/memento.html',        'Memento',      True,  None),
    ('ledger',       '/sisyphe/dashboard.html',      'Ledger',       False, None),
    ('architecture', '/architecture.html',           'Architecture', False, [
        ('architecture', '/architecture.html', 'Architecture'),
        ('system_map',   '/system_map.html',   'System Map'),
    ]),
]
NAV_LABELS = [it[2] for it in NAV_ITEMS]


def nav_html(active=None, sub_active=None):
    """정본 네비 마크업. active=메인 탭 key, sub_active=드롭다운 child key."""
    parts = []
    for key, href, label, right, children in NAV_ITEMS:
        cls = 'topnav-tab active' if key == active else 'topnav-tab'
        icls = 'topnav-item right-group' if right else 'topnav-item'
        tab = '<a href="%s" class="%s">%s</a>' % (href, cls, label)
        if children:
            subs = ''.join(
                '<a href="%s" class="topnav-sub%s">%s</a>'
                % (h, ' active' if k == sub_active else '', l)
                for k, h, l in children)
            tab += '<div class="topnav-dropdown">%s</div>' % subs
        parts.append('<div class="%s">%s</div>' % (icls, tab))
    return ('<nav class="topnav"><div class="topnav-inner">'
            '<a href="%s" class="topnav-brand">%s</a>'
            '<div class="topnav-tabs">%s</div>'
            '</div></nav>' % (BRAND_HREF, BRAND, ''.join(parts)))


# ---- 정본 CSS ----
# 값 확정 근거 (2026-07-26 6개 사본 대조):
#   탭 폰트 1rem            = 2026-07-22 타이포 개정(스냅숏 주입·watchlist 반영분)을 정본화
#   box-sizing:border-box   = inner 1400px 계산 통일 (누락 시 28px 어긋남 — market·wrap 이력)
#   line-height:normal      = 페이지 body line-height 상속 차단 (architecture 1.6 상속 이력)
#   비활성 탭 #9aa4ae       = 다수 사본 값 (watchlist 만 #fff 였음 → 통일)
#   활성 = 앰버/#101418     = AOE_STYLE_GUIDE 확정값
#   드롭다운 active 앰버    = 구 레드(#2a1515/#e08585) 폐기, 가이드 선택 하이라이트 ①앰버 계열
_PAGE_RULES = [  # 페이지 레벨 가드 — scoped 렌더 포함 전 소비자 공통 (2026-07-27)
    ('html', 'overflow-y:scroll'),   # 스크롤바 공간 상시 확보 — 로드 중 nav 좌우 점프 방지
    ('body', 'margin:0'),
]
_NAV_RULES = [
    ('.topnav',
     'background:' + PALETTE['nav-bg'] + ';border-bottom:2px solid ' + PALETTE['amber'] + ';position:sticky;top:0;z-index:100'),
    ('.topnav-inner',
     'max-width:1400px;margin:0 auto;padding:0 28px;box-sizing:border-box;'
     'display:flex;align-items:stretch;height:54px;gap:36px'),
    ('.topnav-brand',
     'font-size:1.1rem;font-weight:800;letter-spacing:3.5px;color:#fff;white-space:nowrap;'
     'text-decoration:none;align-self:center;line-height:normal;font-family:' + PRETENDARD_STACK),
    ('.topnav-brand:hover', 'color:' + PALETTE['amber']),
    ('.topnav-tabs', 'display:flex;gap:2px;flex:1;align-items:stretch'),
    ('.topnav-item', 'position:relative;display:flex;align-items:stretch'),
    ('.topnav-tabs .topnav-item.right-group', 'margin-left:auto'),
    ('.topnav-tab',
     'box-sizing:border-box;display:inline-flex;align-items:center;gap:6px;padding:0 18px;'
     'color:#9aa4ae;text-decoration:none;font-size:1rem;font-weight:600;letter-spacing:0.3px;'
     'line-height:normal;border:none;border-radius:0;white-space:nowrap;background:transparent;'
     'transition:color 0.12s,background 0.12s;cursor:pointer;font-family:' + PRETENDARD_STACK),
    ('.topnav-tab:hover', 'color:#fff;background:#1a2027'),
    ('.topnav-tab.active', 'color:' + PALETTE['nav-bg'] + ';background:' + PALETTE['amber'] + ';font-weight:600;'
     'text-shadow:0.4px 0 currentColor,-0.4px 0 currentColor'),  # 유사볼드 — 700은 글자폭이 늘어 뒤 탭이 페이지마다 1~3px 밀림 (2026-07-27)
    ('.topnav-dropdown',
     'box-sizing:border-box;position:absolute;top:100%;left:0;min-width:180px;width:max-content;'
     'background:#14181d;border:1px solid #2a323b;border-radius:0;'
     'box-shadow:0 8px 24px rgba(0,0,0,0.35);padding:4px 0;opacity:0;visibility:hidden;'
     'transform:translateY(-4px);transition:opacity 0.15s,transform 0.15s,visibility 0.15s;'
     'z-index:200'),
    ('.topnav-item:hover .topnav-dropdown,.topnav-item:focus-within .topnav-dropdown',
     'opacity:1;visibility:visible;transform:translateY(0)'),
    ('.topnav-sub',
     'display:block;padding:9px 16px;color:#b7c0c9;text-decoration:none;font-size:0.9rem;'
     'font-weight:500;border-radius:0;white-space:nowrap;text-align:center;line-height:normal;'
     'font-family:' + PRETENDARD_STACK),
    ('.topnav-sub:hover', 'background:#1a2027;color:#fff'),
    ('.topnav-sub.active', 'background:' + PALETTE['hl-amber-bg'] + ';color:' + PALETTE['hl-amber-fg'] + ';font-weight:700'),
]
_NAV_MEDIA_RULES = [
    ('.topnav-inner', 'padding:0 12px;gap:12px;height:46px'),
    ('.topnav-brand', 'font-size:0.95rem'),
    ('.topnav-tab', 'padding:0 12px;font-size:0.85rem;min-width:0'),
]


def _scope_sel(sel):
    """'.topnav...' 셀렉터를 nav.topnav 스코프로 승격 — 기존 페이지 CSS(동일 셀렉터)를
    명시도에서 이기기 위한 override 렌더용 (compose Sisyphe 페이지)."""
    out = []
    for part in sel.split(','):
        part = part.strip()
        if part == '.topnav':
            out.append('nav.topnav')
        elif part.startswith('.topnav'):
            out.append('nav.topnav ' + part)
        else:
            out.append(part)
    return ','.join(out)


def render_nav_css(scoped=False):
    rules = list(_PAGE_RULES) + _NAV_RULES  # scoped 포함 (2026-07-27): memento 등 짧은 페이지 스크롤바 부재로 nav +8px 점프
    lines = []
    for sel, decl in rules:
        s = _scope_sel(sel) if scoped else sel
        lines.append('%s{%s}' % (s, decl))
    media = []
    for sel, decl in _NAV_MEDIA_RULES:
        s = _scope_sel(sel) if scoped else sel
        media.append('%s{%s}' % (s, decl))
    lines.append('@media (max-width:800px){%s}' % ''.join(media))
    return '\n'.join(lines)


NAV_CSS = render_nav_css()
NAV_CSS_SCOPED = render_nav_css(scoped=True)

# ---- 정적 HTML 물리 반영/기동 시 치환 (wiki index.html, quoteboard index.html) ----
CSS_MARK_BEGIN = '/* AOE-NAV-CSS-BEGIN (정본: execution/nav_style.py — 직접 수정 금지) */'
CSS_MARK_END = '/* AOE-NAV-CSS-END */'
PALETTE_MARK_BEGIN = '/* AOE-PALETTE-BEGIN (정본: execution/nav_style.py — 직접 수정 금지) */'
PALETTE_MARK_END = '/* AOE-PALETTE-END */'

# ---- 공용 캡처 색고정 JS (2026-07-26) ----
# html2canvas 가 동일 명시도 !important 간 후행 우선을 무시해 다크 틴트 셀 글자를 #333 으로
# 굳히는 버그 차단: 캡처 전 계산된 색을 인라인 !important 로 고정, 캡처 후 style '속성
# 문자열'을 그대로 원복 (cssText 재직렬화 금지 — [style*=...] 셀렉터 보호).
# 소비자: create_dashboard(_element_download_helper_js·universe 페이지) — <script> 안에 splice.
H2C_FREEZE_JS = '''
if (typeof window._h2cFreeze !== 'function') {
    window._h2cFreeze = function(root) {
        var nodes = [root].concat(Array.prototype.slice.call(root.querySelectorAll('*')));
        var saved = [];
        nodes.forEach(function(n) {
            if (n.nodeType !== 1) return;
            var cs = getComputedStyle(n);
            saved.push([n, n.getAttribute('style')]);
            n.style.setProperty('color', cs.color, 'important');
            var b = cs.backgroundColor;
            if (b && b !== 'rgba(0, 0, 0, 0)' && b !== 'transparent') n.style.setProperty('background-color', b, 'important');
        });
        return function() {
            saved.forEach(function(p) {
                if (p[1] === null) p[0].removeAttribute('style');
                else p[0].setAttribute('style', p[1]);
            });
        };
    };
}
'''


# ---- 하위 스트립(사이드바) 정본 (2026-07-31) ----
# Market 그룹 전용 하드코딩이었던 렌더러를 NAV_ITEMS 기반 그룹 일반화로 이전.
# 소비자: create_dashboard(생성 페이지) / quoteboard(materialize 마커 주입).
SIDEBAR_EXCLUDE_GROUPS = ('wrap',)   # WRAP 은 전용 렌더러(wrap_top_nav_html) 사용


def resolve_main_key(active):
    """active 페이지 키가 속한 메인 탭 key 를 반환."""
    for key, _href, _label, _right, children in NAV_ITEMS:
        if key == active:
            return key
        for ck, _ch, _cl in (children or []):
            if ck == active:
                return key
    return ''


def group_children(active):
    """active 가 속한 그룹의 children (없으면 None). 제외 그룹은 None."""
    mk = resolve_main_key(active)
    if not mk or mk in SIDEBAR_EXCLUDE_GROUPS:
        return None
    for key, _href, _label, _right, children in NAV_ITEMS:
        if key == mk:
            return children
    return None


def sidebar_html(active='', href_prefix=''):
    """그룹 하위 스트립. children 없는 그룹이면 ''."""
    children = group_children(active)
    if not children:
        return ''
    links = ''.join(
        '<a href="%s%s" class="sidebar-link%s">%s</a>'
        % (href_prefix, href, ' active' if k == active else '', label)
        for k, href, label in children)
    return '<aside class="sidebar">%s</aside>' % links


# quoteboard 등 마커 소비자용 (create_dashboard 는 자체 레이아웃 CSS 를 별도 보유)
SIDEBAR_CSS = (
    # 2026-07-31 사용자: 하위 스트립 외형을 게시 페이지(market 등)와 통일.
    # 게시본 실제 형상 = create_dashboard 기본 CSS + compose 타이포 v2 오버라이드
    #   -> 스트립 42px / 링크 41px / 18px / 중앙정렬 / sticky(top=nav 54px) / 앰버 밑줄.
    # 이 상수를 소비하는 앱: quoteboard(Watchlist), datalake webui(자식 없음=무동작).
    '.sidebar{position:sticky;top:54px;z-index:90;display:flex;align-items:stretch;'
    # margin-bottom 18px = 게시 페이지(create_dashboard .sidebar margin:0 -24px 18px)와 통일
    'margin:0 0 18px;'
    'justify-content:center;gap:2px;padding:0 28px;height:42px;background:#161b21;'
    'border-bottom:1px solid #2a323b;overflow:hidden;box-sizing:border-box}'
    '.sidebar-link{display:inline-flex;align-items:center;padding:0 14px;height:41px;color:#9aa4ae;'
    'text-decoration:none;font-size:18px;font-weight:600;border-bottom:2px solid transparent;'
    'white-space:nowrap;transition:all 0.12s;font-family:' + PRETENDARD_STACK + '}'
    '.sidebar-link:hover{color:#fff}'
    '.sidebar-link.active{color:#fff;font-weight:700;border-bottom-color:' + PALETTE['amber'] + '}'
    '@media (max-width:800px){.sidebar{display:none}}'
)

SIDEBAR_MARK_BEGIN = '<!-- AOE-SIDEBAR-BEGIN (정본: execution/nav_style.py — 직접 수정 금지) -->'
SIDEBAR_MARK_END = '<!-- AOE-SIDEBAR-END -->'

import re as _re  # noqa: E402

_CSS_BLOCK_PAT = _re.compile(
    _re.escape(CSS_MARK_BEGIN) + '.*?' + _re.escape(CSS_MARK_END), _re.S)
_PAL_BLOCK_PAT = _re.compile(
    _re.escape(PALETTE_MARK_BEGIN) + '.*?' + _re.escape(PALETTE_MARK_END), _re.S)
_NAV_BLOCK_PAT = _re.compile(r'<nav class="topnav">.*?</nav>', _re.S)
_SIDEBAR_BLOCK_PAT = _re.compile(
    _re.escape(SIDEBAR_MARK_BEGIN) + '.*?' + _re.escape(SIDEBAR_MARK_END), _re.S)


def materialize(html_text, active=None, sub_active=None):
    """정적 HTML 의 마커 CSS 블록과 <nav class="topnav"> 블록을 정본으로 치환.

    반환 (new_text, ok). ok=False 면 마커/nav 미발견 — 호출측은 원본을 그대로 쓰되
    경고 로그를 남긴다 (기동 실패로 페이지를 죽이지 않는다).
    """
    new_css = CSS_MARK_BEGIN + '\n' + NAV_CSS + '\n' + SIDEBAR_CSS + '\n' + CSS_MARK_END
    out, n_css = _CSS_BLOCK_PAT.subn(lambda m: new_css, html_text, 1)
    out, n_nav = _NAV_BLOCK_PAT.subn(lambda m: nav_html(active, sub_active), out, 1)
    # 팔레트 마커는 선택적 — 있으면 최신 PALETTE 로 치환 (2026-07-26 색톤 정본화)
    new_pal = PALETTE_MARK_BEGIN + '\n' + PALETTE_CSS_VARS + '\n' + PALETTE_MARK_END
    out = _PAL_BLOCK_PAT.sub(lambda m: new_pal, out, 1)
    # 하위 스트립 마커는 선택적 — 있으면 그룹 children 으로 채운다 (2026-07-31)
    new_sb = (SIDEBAR_MARK_BEGIN + sidebar_html(active) + SIDEBAR_MARK_END)
    out = _SIDEBAR_BLOCK_PAT.sub(lambda m: new_sb, out, 1)
    return out, (n_css == 1 and n_nav == 1)
