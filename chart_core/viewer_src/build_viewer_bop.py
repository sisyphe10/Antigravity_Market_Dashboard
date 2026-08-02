# -*- coding: utf-8 -*-
"""원화↔외화 환전 수급 표 (국제수지 기반) — chart_viewer_bop.html

표 2개.
  · 연도별 (bop_flows.json)   : 유입/유출 항목별 · 순유입 · 참고(환율·거주자외화예금 연말잔액)
  · 월별   (monthly_flows.json): 거주자외화예금 잔액(총/기업/개인) · 월별 플로우 · 환율 월평균
연간 합계로는 안 보이는 월 단위 타이밍(외국인 주식 이탈 ↔ 환율 급등)을 월별 표가 담당한다.

자릿수 = $B 소수 1자리 통일(환율만 정수) — 항목 진폭이 0.3~719로 넓어 행별 밴드를 쓰면
표가 지저분해진다(사용자 확정 2026-07-27).
"""
import html as _html
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from chart_common import nav_html  # noqa: E402

BASE = os.path.dirname(os.path.abspath(__file__))
D = json.load(open(os.path.join(BASE, 'bop_flows.json'), encoding='utf-8'))
S, XL = D['series'], D['xlabels']
N = len(XL)

MP = os.path.join(BASE, 'monthly_flows.json')
M = json.load(open(MP, encoding='utf-8')) if os.path.exists(MP) else None

INFLOW = [('goods_ex', '상품수출'), ('prim_in', '본원소득 수입'), ('frn_bond', '외국인 국내채권'),
          ('travel_in', '여행수입'), ('fdi', '외국인직접투자'), ('oth_liab', '기타투자 부채'),
          ('frn_eq', '외국인 국내주식')]
OUTFLOW = [('goods_im', '상품수입'), ('odi', '해외직접투자'), ('prim_out', '본원소득 지급'),
           ('res_eq', '거주자 해외주식'), ('travel_out', '여행지급'), ('res_bond', '거주자 해외채권'),
           ('oth_asset', '기타투자 자산'), ('svc_etc', '기타 서비스'), ('transfer_out', '이전소득 지급')]


def fmt(v, key):
    if v is None:
        return ''
    return f'{v:,.0f}' if key == 'usdkrw' else f'{v:,.1f}'


def rows(spec, src, cols, cls=''):
    out = []
    for k, label in spec:
        vals = src.get(k) or [None] * len(cols)
        tds = ''.join(f'<td>{fmt(v, k)}</td>' for v in vals)
        out.append(f'<tr class="{cls}"><th scope="row">{_html.escape(label)}</th>{tds}</tr>')
    return '\n'.join(out)


# ── 연도별 표 ────────────────────────────────────────────────────────
# 거주자외화예금 연말잔액을 연도 축에 정렬 (보도자료 표에서 회수 — ECOS 미제공)
if M and M.get('dep_yearend'):
    ye = M['dep_yearend']
    S['dep_ye'] = [ye.get(str(x)) for x in XL]

ncol = N + 1
head = ''.join(f'<th>{_html.escape(str(x))}</th>' for x in XL)
ref = [('usdkrw', '원/달러 연평균 (원)')]
if 'dep_ye' in S:
    ref.append(('dep_ye', '거주자외화예금 연말잔액'))
body = f"""
<tr class="sec"><th scope="row" colspan="{ncol}">유입 &nbsp;·&nbsp; 달러 매도 · 원화 매수</th></tr>
{rows(INFLOW, S, XL)}
{rows([('in_total', '소계')], S, XL, 'tot')}
<tr class="sec"><th scope="row" colspan="{ncol}">유출 &nbsp;·&nbsp; 원화 매도 · 달러 매수</th></tr>
{rows(OUTFLOW, S, XL)}
{rows([('out_total', '소계')], S, XL, 'tot')}
<tr class="sec"><th scope="row" colspan="{ncol}">종합</th></tr>
{rows([('net', '순유입 (유입−유출)')], S, XL, 'net')}
{rows([('current', '경상수지'), ('financial', '금융계정')], S, XL)}
<tr class="sec"><th scope="row" colspan="{ncol}">참고</th></tr>
{rows(ref, S, XL)}
"""

# ── 월별 표 ─────────────────────────────────────────────────────────
mcard = ''
if M:
    MS, MSER = M['months'], M['series']
    mn = len(MS)
    mhead = ''.join(f'<th>{m[2:].replace("-", "/")}</th>' for m in MS)
    mcol = mn + 1
    mbody = f"""
<tr class="sec"><th scope="row" colspan="{mcol}">거주자외화예금 잔액 &nbsp;·&nbsp; 기업이 국내에 쌓아둔 외화</th></tr>
{rows([('dep_total', '총잔액')], MSER, MS, 'tot')}
{rows([('dep_corp', '기업'), ('dep_indiv', '개인')], MSER, MS)}
<tr class="sec"><th scope="row" colspan="{mcol}">월별 유출입</th></tr>
{rows([('frn_eq', '외국인 국내주식'), ('res_eq', '거주자 해외주식'),
       ('current', '경상수지'), ('goods_ex', '상품수출')], MSER, MS)}
<tr class="sec"><th scope="row" colspan="{mcol}">참고</th></tr>
{rows([('usdkrw', '원/달러 월평균 (원)')], MSER, MS)}
"""
    mcard = f"""
  <h2>월별</h2>
  <div class="card">
    <div class="bar">
      <button class="rng" data-m="12">12M</button>
      <button class="rng active" data-m="24">24M</button>
      <button class="rng" data-m="0">전체</button>
      <span class="unit">잔액·플로우 $B</span>
    </div>
    <div class="wrap"><table id="tbl-m">
      <thead><tr><th>항목</th>{mhead}</tr></thead>
      <tbody>{mbody}</tbody>
    </table></div>
  </div>"""

PAGE = """<!doctype html>
<html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>__TITLE__</title>
<link rel="stylesheet" href="https://cdn.jsdelivr.net/gh/orioncactus/pretendard@v1.3.9/dist/web/static/pretendard.css">
<style>
  * { box-sizing: border-box; }
  body { font-family: Pretendard, -apple-system, sans-serif; color: #111;
         background: #f7f8f9; margin: 0; padding: 22px 26px 40px; }
  h1 { font-size: 20px; font-weight: 700; margin: 0 0 12px; }
  h2 { font-size: 17px; font-weight: 700; margin: 26px 0 10px; }
  .card { background: #fff; border-radius: 12px; box-shadow: 0 1px 3px rgba(0,0,0,.08);
          padding: 16px 18px; display: inline-block; max-width: 100%; }
  .bar { display: flex; align-items: center; gap: 8px; margin-bottom: 12px; }
  .rng { font-family: inherit; font-size: 12.5px; padding: 5px 14px; border-radius: 999px;
         border: 1px solid #d0d0d0; background: #fff; color: #111; cursor: pointer; }
  .rng.active { background: #404040; color: #fff; border-color: #404040; }
  .unit { margin-left: auto; font-size: 12.5px; color: #111; padding-left: 20px; }
  .wrap { overflow-x: auto; }
  table { border-collapse: separate; border-spacing: 0; font-size: 13.5px; }
  th, td { text-align: center; padding: 6px 10px; white-space: nowrap;
           border-bottom: 1px solid #ececec; }
  thead th { position: sticky; top: 0; background: #fff; font-weight: 700;
             border-bottom: 2px solid #111; }
  tbody th[scope=row] { text-align: left; padding-left: 12px; font-weight: 400;
                        position: sticky; left: 0; background: #fff; min-width: 152px; }
  tr.sec th { text-align: left; background: #f1f2f4; font-weight: 700; font-size: 12.5px;
              padding-top: 9px; padding-bottom: 9px; letter-spacing: .01em; }
  tr.tot th, tr.tot td { font-weight: 700; background: #fafafa; }
  tr.net th, tr.net td { font-weight: 700; border-bottom: 1px solid #111; }
  tbody tr:hover td { background: #f4f4f4; }
  td.hide, th.hide { display: none; }
</style></head>
<body>
  <h1>__TITLE__</h1>
  __NAV__
  <h2>연도별</h2>
  <div class="card">
    <div class="bar">
      <button class="rng" data-n="11">10Y</button>
      <button class="rng active" data-n="21">20Y</button>
      <button class="rng" data-n="0">전체</button>
      <span class="unit">단위 $B</span>
    </div>
    <div class="wrap"><table id="tbl-y">
      <thead><tr><th>항목</th>__HEAD__</tr></thead>
      <tbody>__BODY__</tbody>
    </table></div>
  </div>
__MCARD__
<script>
function applyRange(tblId, total, n) {
  const t = document.getElementById(tblId);
  if (!t) return;
  const from = n ? Math.max(0, total - n) : 0;
  t.querySelectorAll('tr').forEach(tr => {
    const cs = [...tr.children];
    if (cs.length <= 1) return;              // 섹션 헤더 행(colspan)은 제외
    cs.slice(1).forEach((c, i) => c.classList.toggle('hide', i < from));
  });
}
function wire(attr, tblId, total, def) {
  const bs = [...document.querySelectorAll('button[' + attr + ']')];
  bs.forEach(b => b.addEventListener('click', () => {
    bs.forEach(x => x.classList.remove('active'));
    b.classList.add('active');
    applyRange(tblId, total, +b.getAttribute(attr));
  }));
  applyRange(tblId, total, def);
}
wire('data-n', 'tbl-y', __N__, 21);
if (document.getElementById('tbl-m')) wire('data-m', 'tbl-m', __MN__, 24);
</script>
</body></html>
"""

out = (PAGE.replace('__TITLE__', '원화↔외화 환전 수급 (국제수지 기준)')
           .replace('__NAV__', nav_html('chart_viewer_bop.html'))
           .replace('__HEAD__', head)
           .replace('__BODY__', body)
           .replace('__MCARD__', mcard)
           .replace('__MN__', str(len(M['months']) if M else 0))
           .replace('__N__', str(N)))
for tok in ('__TITLE__', '__NAV__', '__HEAD__', '__BODY__', '__N__', '__MCARD__', '__MN__'):
    assert tok not in out, f'미치환 토큰 {tok}'

open(os.path.join(BASE, 'chart_viewer_bop.html'), 'w', encoding='utf-8').write(out)
print(f'WROTE chart_viewer_bop.html — 연도별 {N}구간({XL[0]}~{XL[-1]})'
      + (f', 월별 {len(M["months"])}개월({M["months"][0]}~{M["months"][-1]})' if M else ', 월별 없음'))
