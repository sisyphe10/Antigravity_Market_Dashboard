# -*- coding: utf-8 -*-
"""리가켐바이오 ADC 파이프라인 표 — chart_viewer_pipeline.html

표 3개.
  · 임상 단계   (clinical)    : 8개 에셋, 진척도 내림차순
  · 전임상      (preclinical) : 4개 에셋
  · 플랫폼 계약 (platform)    : ConjuALL 플랫폼 사용권 자체를 판 5건

정본 = pipeline_data.json (정적). 수집기 없음 → run_daily.py 제외, 수동 갱신.
양식은 chart_viewer_bop.html(환율 수급 표)과 동일 — 흰 카드·검정 글씨·회색 섹션행, 색상 없음.
"""
import html as _html
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from chart_common import aoe_tokens_css, nav_html  # noqa: E402

BASE = os.path.dirname(os.path.abspath(__file__))
D = json.load(open(os.path.join(BASE, 'pipeline_data.json'), encoding='utf-8'))

E = _html.escape
# ADC 3부품(타겟·항체 / 페이로드 / 링커)이 나란히 오도록 배치.
COLS = ['에셋명', '타겟', '항체', '페이로드', '링커', '암종', '적응증', '파트너', '지역',
        '구분', '개발 단계', '시장 규모', '기전 · 현황']


def sub(v):
    """부제(<small>) — 값이 비었거나 하이픈뿐이면 아예 렌더하지 않는다."""
    v = (v or '').strip()
    return f'<small>{E(v)}</small>' if v not in ('', '-', '—') else ''


def mute(v):
    """미공개 값은 회색으로 눌러 공개된 항목(LCB84·BCMA 2종)이 드러나게 한다."""
    v = (v or '').strip()
    if v in ('', '-', '—'):
        return '<span class="dash">—</span>'
    return f'<span class="mut">{E(v)}</span>' if v == '비공개' else E(v)


def reg(v):
    """값이 없으면 대시 — 지역·에셋 공통."""
    v = (v or '').strip()
    return E(v) if v not in ('', '-', '—') else '<span class="dash">—</span>'


def asset_cell(a):
    return f'<b>{E(a["name"])}</b>'


def tam_cell(a):
    v = f'<b>{E(a["tam"])}</b>' if a['tam'] else '<span class="dash">—</span>'
    return f'{v}{sub(a["tam_note"])}'


def asset_rows(items):
    out = []
    for a in sorted(items, key=lambda x: -x['rank']):
        out.append(
            '<tr>'
            f'<th scope="row">{asset_cell(a)}</th>'
            f'<td>{E(a["target"])}</td>'
            f'<td class="ab">{mute(a["antibody"])}</td>'
            f'<td>{mute(a["payload"])}{sub(a["payload_src"])}</td>'
            f'<td>{mute(a["linker"])}</td>'
            f'<td>{E(a["tumor_type"])}</td>'
            f'<td class="l">{E(a["indication"])}</td>'
            f'<td>{E(a["partner"])}</td>'
            f'<td>{reg(a["region"])}</td>'
            f'<td>{E(a["type"])}</td>'
            f'<td class="ph">{E(a["phase"])}</td>'
            f'<td class="tam">{tam_cell(a)}</td>'
            f'<td class="mech">{E(a["mech"])}</td>'
            '</tr>')
    return '\n'.join(out)


def plat_rows(items):
    return '\n'.join(
        f'<tr><th scope="row">{E(p["date"])}</th><td>{E(p["partner"])}</td>'
        f'<td>{E(p["region"])}</td><td>{E(p["targets"])}</td><td><b>{E(p["amount"])}</b></td></tr>'
        for p in items)


def cnt_text(items):
    """'8개 · 고형암 6 · 혈액암 2 · 자체 보유 1개 (LCB02A)' — 건수는 전부 정본에서 센다."""
    parts = [f'{len(items)}개']
    for tt in ('고형암', '혈액암'):
        n = sum(1 for a in items if a['tumor_type'] == tt)
        if n:
            parts.append(f'{tt} {n}')
    own = [a['name'] for a in items if a['type'] == '자체']
    if own:
        parts.append(f'자체 보유 {len(own)}개 ({" · ".join(own)})')
    return ' · '.join(parts)


def tl_rows(items):
    """2H26 주요 일정 — 정본의 order 값으로만 정렬한다."""
    return '\n'.join(
        '<tr>'
        f'<th scope="row">{E(t["when"])}</th>'
        f'<td>{reg(t["asset"])}</td>'
        f'<td class="l">{E(t["event"])}</td>'
        f'<td>{E(t["kind"])}</td>'
        f'<td>{E(t["source"])}</td>'
        '</tr>'
        for t in sorted(items, key=lambda x: x['order']))


def tl_cnt(items):
    """'15건 · 회사 IR 12건 · 증권사 3건' — 출처 구성을 정본에서 센다."""
    ir = sum(1 for t in items if t['source'] == '회사 IR')
    return f'{len(items)}건 · 회사 IR {ir}건 · 증권사 {len(items) - ir}건'


head = ''.join(f'<th>{E(c)}</th>' for c in COLS[1:])
n_own = sum(1 for a in D['clinical'] + D['preclinical'] if a['type'] == '자체')

PAGE = """<!doctype html>
<html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>__TITLE__</title>
<link rel="stylesheet" href="https://cdn.jsdelivr.net/gh/orioncactus/pretendard@v1.3.9/dist/web/static/pretendard.css">
<style>
__AOE_TOKENS__
  :root { --aoe-t-pad-y: 8px; }   /* 파이프라인 표는 행 높이 여유 (기존값 유지) */
  * { box-sizing: border-box; }
  body { font-family: Pretendard, -apple-system, sans-serif; color: #111;
         background: #f7f8f9; margin: 0; padding: 22px 26px 40px; }
  h1 { font-size: 20px; font-weight: 700; margin: 0 0 12px; }
  h2 { font-size: 17px; font-weight: 700; margin: 26px 0 10px; }
  .card { background: #fff; border-radius: 12px; box-shadow: 0 1px 3px rgba(0,0,0,.08);
          padding: 16px 18px; display: inline-block; max-width: 100%; }
  .bar { display: flex; align-items: baseline; gap: 8px; margin-bottom: 12px; }
  .cnt { font-size: 12.5px; color: #111; }
  .unit { margin-left: auto; font-size: 12.5px; color: #111; padding-left: 20px; }
  .dl { font-family: inherit; font-size: 12.5px; font-weight: 600; padding: 6px 14px;
        border-radius: 8px; border: none; background: #dc2626; color: #fff; cursor: pointer; }
  /* .unit 이 없는 카드(플랫폼)에서만 버튼을 오른쪽 끝으로.
     .dl 정의 자체는 fcf 정본 그대로 두기 위해 마진은 별도 셀렉터로 뺀다. */
  .cnt + .dl { margin-left: auto; }
  .dl:focus-visible { outline: 2px solid #111; outline-offset: 2px; }
  .dl[disabled] { opacity: .45; cursor: default; }
  /* 캡처 모드 — 가로 스크롤 펼치고 sticky 를 풀고 버튼 줄을 숨긴다. finally 에서 원복. */
  .card.cap { max-width: none !important; width: max-content !important; }
  .card.cap .bar { display: none !important; }
  .card.cap .wrap { overflow: visible !important; width: max-content !important; }
  .card.cap thead th, .card.cap tbody th[scope=row] { position: static !important; }
  .wrap { overflow-x: auto; }
  table { border-collapse: separate; border-spacing: 0; font-size: var(--aoe-t-font);
          font-variant-numeric: var(--aoe-t-num); }
  th, td { text-align: var(--aoe-t-align); padding: var(--aoe-t-pad-y) var(--aoe-t-pad-x); white-space: nowrap;
           border-bottom: var(--aoe-t-row-line) solid #ececec; vertical-align: var(--aoe-t-valign); }
  thead th { position: sticky; top: 0; background: #fff; font-weight: var(--aoe-t-head-weight);
             border-bottom: var(--aoe-t-head-underline) solid #111; z-index: 2; }
  tbody th[scope=row] { text-align: left; padding-left: 12px; font-weight: 400;
                        position: sticky; left: 0; background: #fff; z-index: 1; }
  tbody th[scope=row] b { font-weight: 700; }
  small { display: block; font-size: 11px; color: #666; font-weight: 400;
          line-height: 1.4; margin-top: 1px; }
  td.l { text-align: left; }
  td.ph { font-weight: 700; }
  td.tam { min-width: 130px; }
  td.tam b { font-weight: 700; }
  td.tam small { white-space: normal; max-width: 150px; margin: 1px auto 0; }
  td.mech { text-align: left; white-space: normal; min-width: 420px; max-width: 460px;
            color: #333; line-height: 1.55; padding: 10px 12px; }
  td.ab { white-space: normal; max-width: 200px; }
  .mut { color: #999; }
  .dash { color: #999; }
  tr.sec th { text-align: left; background: #f1f2f4; font-weight: 700; font-size: 12.5px;
              padding-top: 9px; padding-bottom: 9px; }
  tbody tr:hover td, tbody tr:hover th[scope=row] { background: #f4f4f4; }
  .note { font-size: 12px; color: #666; line-height: 1.6; margin: 8px 0 0; max-width: 900px; }
  .note b { color: #111; }
</style></head>
<body>
  <h1>__TITLE__</h1>
  __NAV__

  <h2>임상 단계</h2>
  <div class="card">
    <div class="bar">
      <span class="cnt">__CCNT__</span>
      <button type="button" class="dl" data-target="t-clinical" data-name="ligachem_pipeline_clinical">Download</button>
    </div>
    <div class="wrap"><table id="t-clinical">
      <thead><tr><th>에셋명</th>__HEAD__</tr></thead>
      <tbody>__CBODY__</tbody>
    </table></div>
  </div>

  <h2>전임상 · IND 준비</h2>
  <div class="card">
    <div class="bar">
      <span class="cnt">__PCNT__</span>
      <button type="button" class="dl" data-target="t-preclinical" data-name="ligachem_pipeline_preclinical">Download</button>
    </div>
    <div class="wrap"><table id="t-preclinical">
      <thead><tr><th>에셋명</th>__HEAD__</tr></thead>
      <tbody>__PBODY__</tbody>
    </table></div>
  </div>

  <h2>2H26 주요 일정</h2>
  <div class="card">
    <div class="bar">
      <span class="cnt">__TCNT__</span>
      <span class="unit">시점 순</span>
      <button type="button" class="dl" data-target="t-timeline" data-name="ligachem_pipeline_2h26_timeline">Download</button>
    </div>
    <div class="wrap"><table id="t-timeline">
      <thead><tr><th>시점</th><th>에셋</th><th>이벤트</th><th>구분</th><th>출처</th></tr></thead>
      <tbody>__TBODY__</tbody>
    </table></div>
  </div>

  <h2>플랫폼 기술이전 계약</h2>
  <div class="card">
    <div class="bar">
      <span class="cnt">개별 물질이 아니라 ConjuALL 플랫폼 사용권 자체를 판매</span>
      <button type="button" class="dl" data-target="t-platform" data-name="ligachem_pipeline_platform_deals">Download</button>
    </div>
    <div class="wrap"><table id="t-platform">
      <thead><tr><th>계약 시기</th><th>파트너</th><th>소재</th><th>타겟 수</th><th>총 계약규모</th></tr></thead>
      <tbody>__LBODY__</tbody>
    </table></div>
  </div>

  <p class="note">
    <b>ADC 3부품</b> 타겟은 항체가 결정하고, 페이로드는 무엇으로 죽일지, 링커는 언제 놓을지를 담당한다.
    리가켐은 항체를 외부에서 도입하며 <b>항체 출처가 공개된 것은 LCB84뿐</b>이다.
    자체 기술은 접합 방식(ConjuALL)·LBG 링커·pPBD 페이로드 셋이다.<br>
    <b>암종</b> 고형암은 덩어리로 자라는 암(유방·폐·위·난소 등)이라 약이 종양 내부까지 침투해야 해 개발 난도가 높고,
    혈액암은 암세포가 혈액을 순환해 반응률이 상대적으로 높게 나온다. 두 군의 반응률 수치를 직접 비교하면 안 된다.<br>
    <b>구분</b> 기술이전 = 이미 파트너에게 권리를 넘긴 에셋으로, 시장이 커도 리가켐 몫은 마일스톤·로열티 일부.
    임상 8개 중 자체 보유는 LCB02A 하나.<br>
    <b>시장 규모</b> 리포트에 적응증 TAM이 명시된 항목은 LCB02A(위암)뿐. 나머지는 경쟁·선발 약물의 2032년 예상 매출을 대리 지표로 표기 —
    해당 에셋이 가져갈 매출이 아니라 타겟 시장의 크기로만 읽을 것.<br>
    <b>2H26 일정</b> 출처가 '회사 IR'인 항목은 2026-07-10 회사 IR 공지 원문 기준, '증권사'는 리포트 추정.
    회사 공지에는 LNCB74(B7-H4)와 ESMO 언급이 없다.<br>
    <b>출처</b> 증권사 리포트 9건(하나·iM 2건·메리츠·다올·NH·DS·미래에셋·신한, 2026-05-21 ~ 07-08) 및 회사 1Q26 실적발표 IR(2026-05-18). 기준일 __ASOF__.
  </p>
<script src="https://cdn.jsdelivr.net/npm/html2canvas@1.4.1/dist/html2canvas.min.js"></script>
<script>
(function () {
  // 표 카드를 그대로 고해상 PNG 로. 폴더 규약: 네이티브 2배 · 흰 배경 · 실행일 파일명.
  var DPR = (window.devicePixelRatio || 1) * 2;

  function stamp() {
    return new Date().toLocaleDateString('sv').replace(/-/g, '');
  }

  function capture(btn) {
    var table = document.getElementById(btn.getAttribute('data-target'));
    if (!table) return;
    var card = table.closest('.card');        // 카드 패딩까지 포함해서 담는다
    if (typeof html2canvas !== 'function') {
      window.alert('html2canvas 를 불러오지 못했습니다. 네트워크를 확인해 주세요.');
      return;
    }
    btn.disabled = true;
    card.classList.add('cap');                // 스크롤 펼침 + sticky 해제 + .bar 숨김
    // 레이아웃이 실제로 반영된 뒤 크기를 읽는다.
    var w = card.scrollWidth, h = card.scrollHeight;
    html2canvas(card, {
      scale: DPR,
      backgroundColor: '#ffffff',
      width: w,
      height: h,
      windowWidth: Math.max(document.documentElement.clientWidth, w + 80),
      scrollX: 0,
      scrollY: 0,
      useCORS: true
    }).then(function (canvas) {
      var a = document.createElement('a');
      a.download = btn.getAttribute('data-name') + '_' + stamp() + '.png';
      a.href = canvas.toDataURL('image/png');
      a.click();
    }).catch(function (e) {
      window.alert('이미지 생성에 실패했습니다: ' + e);
    }).then(function () {
      card.classList.remove('cap');           // 성공/실패 무관 원복
      btn.disabled = false;
    });
  }

  Array.prototype.forEach.call(document.querySelectorAll('button.dl'), function (btn) {
    btn.addEventListener('click', function () { capture(btn); });
  });
})();
</script>
</body></html>
"""

out = (PAGE.replace('__TITLE__', '리가켐바이오 ADC 파이프라인')
           .replace('__AOE_TOKENS__', aoe_tokens_css()).replace('__NAV__', nav_html('chart_viewer_pipeline.html'))
           .replace('__HEAD__', head)
           .replace('__CBODY__', asset_rows(D['clinical']))
           .replace('__PBODY__', asset_rows(D['preclinical']))
           .replace('__TBODY__', tl_rows(D['timeline']))
           .replace('__TCNT__', tl_cnt(D['timeline']))
           .replace('__LBODY__', plat_rows(D['platform']))
           .replace('__CCNT__', cnt_text(D['clinical']))
           .replace('__PCNT__', cnt_text(D['preclinical']))
           .replace('__NC__', str(len(D['clinical'])))
           .replace('__NP__', str(len(D['preclinical'])))
           .replace('__ASOF__', D['asof']))
for tok in ('__TITLE__', '__NAV__', '__HEAD__', '__CBODY__', '__PBODY__',
            '__LBODY__', '__TBODY__', '__TCNT__', '__CCNT__', '__PCNT__',
            '__NC__', '__NP__', '__ASOF__'):
    assert tok not in out, f'미치환 토큰 {tok}'

open(os.path.join(BASE, 'chart_viewer_pipeline.html'), 'w', encoding='utf-8').write(out)
print(f'WROTE chart_viewer_pipeline.html — 임상 {len(D["clinical"])} / 전임상 {len(D["preclinical"])}'
      f' / 일정 {len(D["timeline"])} / 플랫폼 {len(D["platform"])} · 자체 보유 {n_own}')
