# -*- coding: utf-8 -*-
"""RoC² 판독성 점수 전수 산출 → 화이트리스트 후보 생성.

기준: 부호 런 평균 길이(무작위 기대 2.0) + lag-1 자기상관. MA 끈 원값으로 계산.
월(M)·주(W) 각각 산출하고, 둘 중 하나라도 통과하면 허용 후보로 본다.
"""
import io, json, re, statistics, datetime

H = io.open('/Users/sisyphe/Antigravity_Market_Dashboard/market.html', encoding='utf-8').read()


def grab(v):
    i = H.index('var %s = ' % v); j = H.index('{', i)
    depth, k, instr, esc = 0, j, False, False
    while k < len(H):
        c = H[k]
        if instr:
            if esc: esc = False
            elif c == '\\': esc = True
            elif c == '"': instr = False
        else:
            if c == '"': instr = True
            elif c == '{': depth += 1
            elif c == '}':
                depth -= 1
                if depth == 0: return json.loads(H[j:k+1])
        k += 1


cmb, hist, units = grab('cmbData'), grab('cmbRocHist'), grab('cmbSeriesUnit')
dates, data = cmb['dates'], cmb['data']
EP = datetime.date(1970, 1, 1)


def wkey(d):
    return (datetime.date(int(d[:4]), int(d[5:7]), int(d[8:10])) - EP).days // 7


def score(name, freq):
    arr = data.get(name)
    if not arr: return None
    keyOf = (lambda d: d[:7]) if freq == 'M' else wkey
    b, order = {}, []
    for i, d in enumerate(dates):
        v = arr[i] if i < len(arr) else None
        if v is None: continue
        k = keyOf(d)
        if k not in b: order.append(k)
        b[k] = v
    if name in hist:
        for d, v in zip(hist[name]['d'], hist[name]['v']):
            k = keyOf(d)
            if k not in b: order.append(k)
            b[k] = v
    order = sorted(order) if freq == 'M' else sorted(order, key=int)
    kd = 'level' if re.search(r'전년동월비|전년동기|전년비|증감률', name) else (
        'diff' if units.get(name, '') in ('%', '%p') else 'yoy')
    lag = 12 if freq == 'M' else 52
    def back(k, nb):
        if freq == 'M':
            y, mo = int(order[k][:4]), int(order[k][5:7]) - nb
            while mo <= 0: mo += 12; y -= 1
            return b.get('%04d-%02d' % (y, mo))
        return b.get(order[k] - nb)
    r1 = []
    for i in range(len(order)):
        if kd == 'level': r1.append(b[order[i]]); continue
        p = back(i, lag)
        if p is None: r1.append(None); continue
        r1.append(b[order[i]] - p if kd == 'diff' else ((b[order[i]]/p - 1)*100 if p else None))
    r2 = [None if (i == 0 or r1[i] is None or r1[i-1] is None) else r1[i]-r1[i-1]
          for i in range(len(r1))]
    v = [x for x in r2 if x is not None]
    if len(v) < 24: return None
    runs, cur = [], 1
    for j in range(1, len(v)):
        if (v[j] >= 0) == (v[j-1] >= 0): cur += 1
        else: runs.append(cur); cur = 1
    runs.append(cur)
    m_ = statistics.mean(v)
    num = sum((v[j]-m_)*(v[j-1]-m_) for j in range(1, len(v)))
    den = sum((x-m_)**2 for x in v)
    return statistics.mean(runs), (num/den if den else 0.0), len(v)


RUN_T, AC_T = 2.7, 0.25
rows = []
for name in data:
    m, w = score(name, 'M'), score(name, 'W')
    if not m and not w: continue
    ok = (m and m[0] >= RUN_T and m[1] >= AC_T) or (w and w[0] >= RUN_T and w[1] >= AC_T)
    rows.append((m[0] if m else 0, name, m, w, ok))

rows.sort(reverse=True)
allow = [r[1] for r in rows if r[4]]
print(f'점수 산출 {len(rows)}종 / 기준 통과 {len(allow)}종  (런≥{RUN_T}, AC1≥{AC_T})')
print()
print(f"{'시리즈':<28}{'M런':>6}{'M AC1':>7}{'Mn':>5}{'W런':>6}{'W AC1':>7}{'Wn':>5}  판정")
for _, name, m, w, ok in rows:
    ms = f"{m[0]:>6.2f}{m[1]:>7.2f}{m[2]:>5}" if m else f"{'-':>6}{'-':>7}{'-':>5}"
    ws = f"{w[0]:>6.2f}{w[1]:>7.2f}{w[2]:>5}" if w else f"{'-':>6}{'-':>7}{'-':>5}"
    print(f'{name:<28}{ms}{ws}  {"✅ 허용" if ok else "제외"}')
# 점수 포함 dict 를 파일로 — create_dashboard.py 에 그대로 삽입한다(전사 오류 방지)
sc = {}
for _, name, m, w, ok in rows:
    if not ok: continue
    sc[name] = (round(m[0], 2) if m else None, round(m[1], 2) if m else None,
                round(w[0], 2) if w else None, round(w[1], 2) if w else None)
lines = ['CMB_ROC_ALLOW = {']
for n in sorted(sc):
    lines.append(f'    {n!r}: {sc[n]!r},')
lines.append('}')
with io.open('/tmp/roc_allow.txt', 'w', encoding='utf-8', newline='') as f:
    f.write('\n'.join(lines) + '\n')
print(f'/tmp/roc_allow.txt 기록 ({len(sc)}종)')
