# -*- coding: utf-8 -*-
"""매크로 · 실적 이벤트 캘린더 — chart_viewer_calendar.html

표 2개.
  · 8월 예정 (upcoming) : 날짜 · 요일 · 이벤트
  · 7월 결과 (past)     : 날짜 · 요일 · 이벤트 · 결과 · 시장 반응

정본 = calendar_data.json (정적). 수집기 없음 → run_daily.py 제외, 수동 갱신.
양식(사용자 확정 2026-07-31) = 채팅 마크다운 표 그대로 — 흰 배경 · 검정 글씨의 민무늬 표.
bop 계열의 회색 카드 · 회색 섹션행은 쓰지 않는다. 날짜 · 요일 · 이벤트는 가운데,
결과 · 시장 반응만 왼쪽 정렬 + 한 칸 들여쓰기.
"""
import html as _html
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from chart_common import aoe_tokens_css, nav_html  # noqa: E402

BASE = os.path.dirname(os.path.abspath(__file__))
D = json.load(open(os.path.join(BASE, 'calendar_data.json'), encoding='utf-8'))

E = _html.escape


def sec_row(label, span):
    return f'<tr class="sec"><th scope="row" colspan="{span}">{E(label)}</th></tr>'


def tr(r):
    """주요 이벤트 = 행 배경색으로만 구분 (볼드 금지, 사용자 확정 2026-07-31)."""
    return '<tr class="key">' if r.get('key') else '<tr>'


def up_rows(items):
    out = []
    for r in items:
        if 'sec' in r:
            out.append(sec_row(r['sec'], 3))
            continue
        out.append(
            f'{tr(r)}'
            f'<th scope="row">{E(r["date"])}</th>'
            f'<td class="dow">{E(r["dow"])}</td>'
            f'<td class="ev">{E(r["event"])}</td>'
            '</tr>')
    return '\n'.join(out)


def past_rows(items):
    out = []
    for r in items:
        if 'sec' in r:
            out.append(sec_row(r['sec'], 4))
            continue
        out.append(
            f'{tr(r)}'
            f'<th scope="row">{E(r["date"])}</th>'
            f'<td class="dow">{E(r["dow"])}</td>'
            f'<td class="ev">{E(r["event"])}</td>'
            f'<td class="res">{E(r["result"])}</td>'
            '</tr>')
    return '\n'.join(out)


def nav_black(current):
    """내비 링크 기본색 #111 → 순검정. 표 페이지는 글씨를 전부 #000 으로 통일한다."""
    return nav_html(current).replace('color:#111', 'color:#000')


PAGE = """<!doctype html>
<html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>__TITLE__</title>
<link rel="stylesheet" href="https://cdn.jsdelivr.net/gh/orioncactus/pretendard@v1.3.9/dist/web/variable/pretendardvariable.min.css">
<style>
__AOE_TOKENS__
  :root { --aoe-t-font: 13px; }   /* 캘린더 확정 양식(7/31) 유지 — 값만 토큰으로 외재화 */
  /* 채팅에 렌더된 마크다운 표를 그대로 옮긴 양식 — 흰 배경 · 검정 글씨, 카드 · 음영 없음. */
  * { box-sizing: border-box; }
  body { font-family: 'Pretendard Variable', Pretendard, system-ui, -apple-system, sans-serif;
         color: #000; background: #fff; margin: 0; padding: 22px 26px 40px; }
  h1 { font-size: 20px; font-weight: 700; margin: 0 0 12px; }
  h2 { font-size: 17px; font-weight: 700; margin: 26px 0 10px; }
  /* inline-block 이라야 카드가 표 폭으로 줄어든다 — block 이면 상단 요약줄과
     Download 버튼만 화면 끝까지 벌어져 표와 따로 논다. */
  .card { display: inline-block; max-width: 100%; }
  /* 건수 · 기준일 같은 메타 문구는 넣지 않는다 (사용자 확정 2026-07-31). 버튼만. */
  .bar { display: flex; justify-content: flex-end; margin-bottom: 10px; }
  .dl { font-family: inherit; font-size: 12.5px; font-weight: 600; padding: 6px 14px;
        border-radius: 8px; border: none; background: #dc2626; color: #fff; cursor: pointer; }
  .dl:focus-visible { outline: 2px solid #000; outline-offset: 2px; }
  .dl[disabled] { opacity: .45; cursor: default; }
  /* 캡처 모드 — 가로 스크롤 펼치고 sticky 를 풀고 버튼 줄을 숨긴다. finally 에서 원복. */
  .card.cap { max-width: none !important; width: max-content !important; }
  .card.cap .bar { display: none !important; }
  .card.cap .wrap { overflow: visible !important; width: max-content !important; }
  .card.cap thead th, .card.cap tbody th[scope=row] { position: static !important; }
  .wrap { overflow-x: auto; }
  /* 화면 폭을 다 쓰면 한 행이 너무 길어져 눈이 못 따라간다 → 표는 내용 폭으로만,
     각 열은 max-width 로 묶고 가로 · 세로 구분선을 모두 넣는다. */
  table { border-collapse: collapse; font-size: var(--aoe-t-font); width: auto;
          font-variant-numeric: var(--aoe-t-num); }
  /* 표 기본 = 좌우 · 상하 모두 가운데 정렬, 글씨 순검정 · 볼드 없음, 테두리 전부 검정선.
     강조는 굵기가 아니라 행 배경색으로만 한다 (사용자 확정 2026-07-31). */
  th, td { text-align: center; vertical-align: middle; padding: 6px 10px;
           border: 1px solid #000; color: #000; font-weight: 400; }
  /* 볼드는 헤더 첫 행에만 (사용자 확정 2026-07-31). 본문은 전부 일반 굵기. */
  thead th { position: sticky; top: 0; background: #fff; z-index: 2; white-space: nowrap;
             font-weight: 700; }
  tbody th[scope=row] { text-align: center; white-space: nowrap; background: #fff; }
  tbody tr.key th[scope=row], tbody tr.key td { background: #ededed; }
  tr.sec th { background: #d8d8d8; }
  td.dow { white-space: nowrap; }
  td.ev { max-width: 400px; line-height: 1.45; }
  /* 결과 열만 왼쪽 정렬 — 셀 기본 여백에 한 칸(1ch) 더 들여쓴다. */
  td.res { text-align: left; max-width: 560px; line-height: 1.5;
           padding-left: calc(10px + 1ch); }
</style></head>
<body>
  <h1>__TITLE__</h1>
  __NAV__

  <h2>2026년 8월 예정</h2>
  <div class="card">
    <div class="bar">
      <button type="button" class="dl" data-target="t-upcoming" data-name="event_calendar_202608">Download</button>
    </div>
    <div class="wrap"><table id="t-upcoming">
      <thead><tr><th>날짜</th><th>요일</th><th>이벤트</th></tr></thead>
      <tbody>__UBODY__</tbody>
    </table></div>
  </div>

  <h2>2026년 7월 결과</h2>
  <div class="card">
    <div class="bar">
      <button type="button" class="dl" data-target="t-past" data-name="event_calendar_202607_result">Download</button>
    </div>
    <div class="wrap"><table id="t-past">
      <thead><tr><th>날짜</th><th>요일</th><th>이벤트</th><th>결과 · 시장 반응</th></tr></thead>
      <tbody>__PBODY__</tbody>
    </table></div>
  </div>
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

out = (PAGE.replace('__TITLE__', '이벤트 캘린더')
           .replace('__AOE_TOKENS__', aoe_tokens_css()).replace('__NAV__', nav_black('chart_viewer_calendar.html'))
           .replace('__UBODY__', up_rows(D['upcoming']))
           .replace('__PBODY__', past_rows(D['past'])))
for tok in ('__TITLE__', '__NAV__', '__UBODY__', '__PBODY__'):
    assert tok not in out, f'미치환 토큰 {tok}'

open(os.path.join(BASE, 'chart_viewer_calendar.html'), 'w', encoding='utf-8').write(out)
n_u = sum(1 for r in D['upcoming'] if 'sec' not in r)
n_p = sum(1 for r in D['past'] if 'sec' not in r)
print(f'WROTE chart_viewer_calendar.html — 8월 예정 {n_u}건 / 7월 결과 {n_p}건')
