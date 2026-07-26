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

BRAND = 'AGE OF EMERGENCE'
BRAND_HREF = '/index.html'   # Caddy가 /watchlist/ 로 redirect (랜딩 폐지 후 동작 동일)

# ---- 정본 탭 구성 (2026-07-22 순서 개편 반영: 좌 Watchlist~Wiki / 우 Memento·Ledger·Arch) ----
# (key, href, label, right_group, children[(key, href, label)])
NAV_ITEMS = [
    ('watchlist',    '/watchlist/',                  'Watchlist',    False, None),
    ('market',       '/market.html',                 'Market',       False, [
        ('market',       '/market.html',       'Data'),
        ('universe',     '/universe.html',     'Universe'),
        ('universe_lab', '/universe_lab.html', 'Universe Lab'),
        ('featured',     '/featured.html',     'Featured'),
        ('market_alert', '/market_alert.html', '투자유의종목'),
        ('etf',          '/etf.html',          'ETF'),
        ('seibro',       '/seibro.html',       'SEIBro'),
    ]),
    ('journal',      '/sisyphe/journal.html',        'Journal',      False, None),
    ('weekly',       '/sisyphe/journal.html#weekly', 'Weekly',       False, None),
    ('earnings',     '/wiki/library',                'Earnings',     False, None),
    ('wiki',         '/wiki/',                       'Wiki',         False, None),
    ('memento',      '/sisyphe/memento.html',        'Memento',      True,  None),
    ('ledger',       '/sisyphe/dashboard.html',      'Ledger',       False, None),
    ('architecture', '/architecture.html',           'Architecture', False, None),
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
_PAGE_RULES = [  # 페이지 레벨 가드 — scoped 렌더(기존 페이지 CSS override 용)에서는 제외
    ('html', 'overflow-y:scroll'),   # 스크롤바 공간 상시 확보 — 로드 중 nav 좌우 점프 방지
    ('body', 'margin:0'),
]
_NAV_RULES = [
    ('.topnav',
     'background:#101418;border-bottom:2px solid #fb8b1e;position:sticky;top:0;z-index:100'),
    ('.topnav-inner',
     'max-width:1400px;margin:0 auto;padding:0 28px;box-sizing:border-box;'
     'display:flex;align-items:stretch;height:54px;gap:36px'),
    ('.topnav-brand',
     'font-size:1.1rem;font-weight:800;letter-spacing:3.5px;color:#fff;white-space:nowrap;'
     'text-decoration:none;align-self:center;line-height:normal;font-family:' + PRETENDARD_STACK),
    ('.topnav-brand:hover', 'color:#fb8b1e'),
    ('.topnav-tabs', 'display:flex;gap:2px;flex:1;align-items:stretch'),
    ('.topnav-item', 'position:relative;display:flex;align-items:stretch'),
    ('.topnav-tabs .topnav-item.right-group', 'margin-left:auto'),
    ('.topnav-tab',
     'box-sizing:border-box;display:inline-flex;align-items:center;gap:6px;padding:0 18px;'
     'color:#9aa4ae;text-decoration:none;font-size:1rem;font-weight:600;letter-spacing:0.3px;'
     'line-height:normal;border:none;border-radius:0;white-space:nowrap;background:transparent;'
     'transition:color 0.12s,background 0.12s;cursor:pointer;font-family:' + PRETENDARD_STACK),
    ('.topnav-tab:hover', 'color:#fff;background:#1a2027'),
    ('.topnav-tab.active', 'color:#101418;background:#fb8b1e;font-weight:700'),
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
    ('.topnav-sub.active', 'background:#4a2d0a;color:#ffb45e;font-weight:700'),
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
    rules = ([] if scoped else list(_PAGE_RULES)) + _NAV_RULES
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

import re as _re  # noqa: E402

_CSS_BLOCK_PAT = _re.compile(
    _re.escape(CSS_MARK_BEGIN) + '.*?' + _re.escape(CSS_MARK_END), _re.S)
_NAV_BLOCK_PAT = _re.compile(r'<nav class="topnav">.*?</nav>', _re.S)


def materialize(html_text, active=None, sub_active=None):
    """정적 HTML 의 마커 CSS 블록과 <nav class="topnav"> 블록을 정본으로 치환.

    반환 (new_text, ok). ok=False 면 마커/nav 미발견 — 호출측은 원본을 그대로 쓰되
    경고 로그를 남긴다 (기동 실패로 페이지를 죽이지 않는다).
    """
    new_css = CSS_MARK_BEGIN + '\n' + NAV_CSS + '\n' + CSS_MARK_END
    out, n_css = _CSS_BLOCK_PAT.subn(lambda m: new_css, html_text, 1)
    out, n_nav = _NAV_BLOCK_PAT.subn(lambda m: nav_html(active, sub_active), out, 1)
    return out, (n_css == 1 and n_nav == 1)
