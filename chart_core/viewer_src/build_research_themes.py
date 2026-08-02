# -*- coding: utf-8 -*-
"""리서치 노트 테마·섹터 언급 추이 차트 (chart_viewer_research.html).

데이터: 데이터레이크의 research_item_themes / research_entity_mentions / research_items
        (datalake/tagging/ 파이프라인 산출물, DuckDB 뷰).

**주별 막대 + 실제 언급 메시지 수**. 일별은 127개 막대라 판독이 안 되고, 월별은 5개뿐이라
추세가 안 보여 주 단위(월요일 기준)로 묶는다.

★절대 횟수는 그 주 수집량에 그대로 오염된다(주별 원문 수가 2배 이상 벌어지는 주가 있다).
그래서 '기준' 그룹에 **그 주 전체 태깅 원문 수**를 계열로 넣어두었다. 막대가 커진 게
관심 증가인지 원문이 많아진 건지 이 계열을 같이 켜서 판별한다.
"""
import json
import os
import sys

import duckdb

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from chart_common import apply_common, core_template  # noqa: E402

BASE = os.path.dirname(os.path.abspath(__file__))
DUCK = "/Users/sisyphe/datalake/market/market.duckdb"
TOP_THEMES = 20
TOP_SECTORS = 12

PALETTE = ["#1f77b4", "#d62728", "#2ca02c", "#ff7f0e", "#9467bd", "#8c564b",
           "#e377c2", "#17becf", "#bcbd22", "#7f7f7f", "#393b79", "#843c39",
           "#5254a3", "#8c6d31", "#a55194", "#6b6ecf", "#b5cf6b", "#e7969c",
           "#9c9ede", "#ce6dbd"]


def weekly(con, sql):
    """주(월요일)별 집계 → {라벨: [주별 값]} 과 주 축."""
    rows = con.execute(sql).fetchall()
    weeks = [r[0] for r in con.execute(
        "SELECT DISTINCT strftime(date_trunc('week', CAST(date AS DATE)), '%Y-%m-%d') w "
        "FROM research_items ORDER BY w").fetchall()]
    idx = {w: i for i, w in enumerate(weeks)}
    out = {}
    for w, label, n in rows:
        out.setdefault(label, [0] * len(weeks))[idx[w]] = n
    return weeks, out


def main():
    con = duckdb.connect(DUCK, read_only=True)
    W = "strftime(date_trunc('week', CAST(i.date AS DATE)), '%Y-%m-%d')"

    weeks, groups_w = weekly(con, f"""
        SELECT {W} w, t.theme_parent, COUNT(DISTINCT t.message_id)
        FROM research_item_themes t JOIN research_items i USING (message_id)
        GROUP BY 1,2""")
    _, themes_w = weekly(con, f"""
        SELECT {W} w, t.theme_label, COUNT(DISTINCT t.message_id)
        FROM research_item_themes t JOIN research_items i USING (message_id)
        GROUP BY 1,2""")
    _, sectors_w = weekly(con, f"""
        SELECT {W} w, e.sector, COUNT(DISTINCT e.message_id)
        FROM research_entity_mentions e JOIN research_items i USING (message_id)
        WHERE e.role='subject' AND e.sector <> ''
        GROUP BY 1,2""")
    _, base_w = weekly(con, f"""
        SELECT {W} w, '전체 원문', COUNT(*) FROM research_items i GROUP BY 1,2""")

    parent_label = {r[0]: r[1] for r in con.execute("""
        SELECT DISTINCT theme_parent, split_part(theme_label,'/',1)
        FROM research_item_themes""").fetchall()}
    con.close()

    def rank(d, k):
        return sorted(d, key=lambda x: -sum(d[x]))[:k]

    series, items_g, items_t, items_s = {}, [], [], []
    for i, g in enumerate(rank(groups_w, 20)):
        key = "g%d" % i
        series[key] = groups_w[g]
        items_g.append({"key": key, "label": parent_label.get(g, g),
                        "color": PALETTE[i % len(PALETTE)], "axis": "idx", "fmt": "cnt"})
    for i, t in enumerate(rank(themes_w, TOP_THEMES)):
        key = "t%d" % i
        series[key] = themes_w[t]
        items_t.append({"key": key, "label": t,
                        "color": PALETTE[i % len(PALETTE)], "axis": "idx", "fmt": "cnt"})
    for i, s in enumerate(rank(sectors_w, TOP_SECTORS)):
        key = "s%d" % i
        series[key] = sectors_w[s]
        items_s.append({"key": key, "label": s,
                        "color": PALETTE[i % len(PALETTE)], "axis": "idx", "fmt": "cnt"})
    series["base"] = base_w["전체 원문"]
    items_b = [{"key": "base", "label": "전체 원문 수", "color": "#9e9e9e",
                "axis": "idx", "fmt": "cnt"}]

    DATA = {"dates": weeks, "series": series}
    # prefix:false — 사이드바 그룹 머리글은 유지하되 범례·툴팁에는 그룹명을 붙이지
    # 않는다. 라벨 자체가 이미 '메모리/HBM' 처럼 자기설명적이라 접두가 군더더기다.
    CONFIG = {"groups": [{"name": "테마", "items": items_g, "prefix": False},
                         {"name": "세부", "items": items_t, "prefix": False},
                         {"name": "섹터", "items": items_s, "prefix": False},
                         {"name": "기준", "items": items_b, "prefix": False}],
              "defaultOn": [it["key"] for it in items_g[:5]]}

    tpl = core_template()   # P6: AoE 코어 셸 (막대는 데이터셋 type 패스스루)
    tpl = tpl.replace("man: '만', usd: '$', num: '' };",
                      "man: '만', usd: '$', num: '', cnt: '건' };")
    # 표준 라인 데이터셋 속성 → 막대 (건수 주별 막대 — 코어는 type 패스스루)
    tpl = tpl.replace("""    datasets.push({
      label: it.fullLabel,
      data,
      borderColor: it.color,
      backgroundColor: 'transparent',
      borderWidth: 3,
      borderJoinStyle: 'round',
      borderCapStyle: 'round',
      pointRadius: 0,
      tension: 0.4,
      cubicInterpolationMode: 'monotone',
      spanGaps: true,
      yAxisID: it.axis === 'idx' ? 'y' : 'y1',
    });""", """    datasets.push({
      label: it.fullLabel, data, type: 'bar',
      borderColor: it.color, backgroundColor: it.color,
      borderWidth: 0, pointRadius: 0,
      yAxisID: it.axis === 'idx' ? 'y' : 'y1',
    });""")
    # 건수 축은 0 시작 (코어 beginAtZero)
    tpl = tpl.replace("logOn: logMode", "logOn: logMode, beginAtZero: true")
    # 주 단위 축이라 기본 기간 = 전체
    tpl = tpl.replace("let rangeMonths = 'ytd';   // 기본 기간 = YTD",
                      "let rangeMonths = 0;   // 기본 = 전체 (수집 시작이 2026-03)")
    tpl = tpl.replace('<button class="rng active" data-rng="ytd">YTD</button>\n'
                      '        <button class="rng" data-rng="0">전체</button>',
                      '<button class="rng" data-rng="ytd">YTD</button>\n'
                      '        <button class="rng active" data-rng="0">전체</button>')
    # 건수 막대에 로그축은 무의미
    tpl = tpl.replace("let logMode = true;", "let logMode = false;")
    tpl = tpl.replace('<button class="rng active" id="btn-log">Log</button>',
                      '<button class="rng" id="btn-log">Log</button>')

    tpl = tpl.replace("__TITLE__", "리서치 노트 관심축 (주별 언급 건수)")
    tpl = tpl.replace("__DLNAME__", "research_themes")
    tpl = tpl.replace("__NOTE__", "")
    tpl = tpl.replace("__DATA__", json.dumps(DATA, ensure_ascii=False, separators=(",", ":")))
    tpl = tpl.replace("__CONFIG__", json.dumps(CONFIG, ensure_ascii=False, separators=(",", ":")))
    out = os.path.join(BASE, "chart_viewer_research.html")
    open(out, "w", encoding="utf-8").write(
        apply_common(tpl, "chart_viewer_research.html", nav=True))
    print("WROTE chart_viewer_research.html — %d주 (%s ~ %s), 계열 %d"
          % (len(weeks), weeks[0], weeks[-1], len(series)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
