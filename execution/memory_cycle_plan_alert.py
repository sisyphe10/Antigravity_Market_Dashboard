# -*- coding: utf-8 -*-
"""memory_cycle_plan_alert.py — 메모리 3사 사이클 액션플랜 일일 점검 텔레그램 알림.

기준: work/analysis/260719_메모리3사_주가실적PER/메모리3사_사이클_리포트.md (85% 판정 기준)
- 시나리오 판별: -20% 도달 후 12개월 내 반등고점이 전고점의 84~88% '무인지대'를 통과하는지
- 통상형(기저율 80%): 반등 93~100% 도달이 관례 / 약세장형(20%): 천장 79~84%
매일 07:45 KST launchd 타이머(memory-cycle-alert)로 실행. 데이터=yfinance 종가.
"""
import os
import sys
import json
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

KST = timezone(timedelta(hours=9))

STOCKS = [
    {
        "name": "삼성전자", "ticker": "005930.KS", "cur": "KRW",
        "peak": 362500, "peak_date": "2026-06-18", "anchor": "2026-07-02",
        "trim_lo": 300900, "trim_hi": 308100,      # 정점의 83~85% (1차 축소 구간)
        "confirm88": 319000,                        # 통상형 확인선(88%)
        "band": (338400, 354600, 360900),           # 통상형 반등 93/98/100% (하단·중앙·상단)
        "deep25": 239700,                           # 통상형 깊은25% 저점(-34%)
        "bear_low": 190900,                         # 약세장형 중앙 저점(-47%)
    },
    {
        "name": "SK하이닉스", "ticker": "000660.KS", "cur": "KRW",
        "peak": 2919000, "peak_date": "2026-06-22", "anchor": "2026-07-02",
        "trim_lo": 2422800, "trim_hi": 2481200,
        "confirm88": 2568700,
        "band": (2808500, 2867500, 2885700),
        "deep25": 1792200,
        "bear_low": 1230700,
    },
    {
        "name": "마이크론", "ticker": "MU", "cur": "USD",
        "peak": 1213.0, "peak_date": "2026-06-25", "anchor": "2026-07-07",
        "trim_lo": 1007.0, "trim_hi": 1031.0,
        "confirm88": 1067.0,
        "band": (1160.0, 1186.0, 1204.0),
        "deep25": 746.0,
        "bear_low": 514.0,
    },
]


def fmt(v, cur):
    if cur == "KRW":
        return f"{v:,.0f}원"
    return f"${v:,.0f}"


def fetch_closes(ticker, start):
    import yfinance as yf
    px = yf.download(ticker, start=start, auto_adjust=False, progress=False)["Close"]
    if hasattr(px, "columns"):
        px = px[ticker]
    px = px.dropna()
    if len(px) == 0:
        raise RuntimeError(f"{ticker}: no price data")
    return px


def analyze(s):
    px = fetch_closes(s["ticker"], "2026-06-01")
    last = float(px.iloc[-1])
    last_date = px.index[-1].strftime("%m/%d")
    cur_pct = last / s["peak"] * 100

    since = px[px.index >= s["anchor"]]
    reb_high = float(since.max()) if len(since) else last
    reb_date = since.idxmax().strftime("%m/%d") if len(since) else last_date
    reb_pct = reb_high / s["peak"] * 100

    # ── 단계 판정 ──
    triggers = []
    if reb_pct >= 88:
        if cur_pct >= 93:
            stage = "통상형 목표밴드(93~100%) — 잔여 처분 구간"
        else:
            stage = "통상형 확정(88% 통과) — 잔여 홀드"
    elif reb_pct >= 84:
        stage = "무인지대(84~88%) 진입 — 확인 대기 (역사상 착지 사례 없음)"
    elif cur_pct >= 83:
        stage = "1차 축소 구간(83~85%) 진입"
        triggers.append("1차 축소 구간 진입 — 보험성 축소 검토")
    else:
        stage = "반등 대기 (판별 신호 미발생)"

    # 약세장 판정 트리거 A: 반등고점이 81~88% 사이에서 형성된 뒤 고점 대비 -10% 이탈
    if 81 <= reb_pct < 88 and last <= reb_high * 0.90:
        triggers.append("⚠ 약세장 판정 트리거 A 발동: 반등고점(%s, 정점의 %.0f%%) 대비 -10%% 이탈 — 철수 검토" % (reb_date, reb_pct))
    # 트리거 B: 통상형 깊은25% 저점 하회
    if last < s["deep25"]:
        triggers.append("⚠ 트리거 B 발동: 통상형 깊은25%%(%s) 종가 하회 — 통상형 가정 약화, 약세장 저점 %s 참조" % (fmt(s["deep25"], s["cur"]), fmt(s["bear_low"], s["cur"])))
    # 통상형 확인 순간 알림
    if reb_pct >= 88 and cur_pct < 93:
        triggers.append("✅ 통상형 확인선(88%) 통과 — 역사상 이후 전부 93%+ 도달")

    lines = [
        "[%s] %s (%s) · 정점 대비 %.0f%%" % (s["name"], fmt(last, s["cur"]), last_date, cur_pct),
        "  반등고점: %s (%s, 정점의 %.0f%%) · 단계: %s" % (fmt(reb_high, s["cur"]), reb_date, reb_pct, stage),
        "  기준선: 축소 %s~%s | 확인 %s | 목표 %s~%s" % (
            fmt(s["trim_lo"], s["cur"]), fmt(s["trim_hi"], s["cur"]),
            fmt(s["confirm88"], s["cur"]),
            fmt(s["band"][0], s["cur"]), fmt(s["band"][2], s["cur"])),
    ]
    return lines, triggers, reb_pct, cur_pct


def send_telegram(text):
    token = os.environ.get("TELEGRAM_SISYPHE_BOT_TOKEN", "")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "")
    if not token or not chat_id:
        sys.stderr.write("memory_cycle_plan_alert: missing telegram env\n")
        return False
    body = urllib.parse.urlencode({"chat_id": chat_id, "text": text}).encode()
    req = urllib.request.Request("https://api.telegram.org/bot%s/sendMessage" % token, data=body)
    with urllib.request.urlopen(req, timeout=30) as res:
        return bool(json.load(res).get("ok"))


def main():
    now = datetime.now(KST)
    header = "📐 메모리 사이클 플랜 점검 (%s)" % now.strftime("%m/%d %a")
    blocks, all_triggers = [], []
    mu_reb = None
    for s in STOCKS:
        try:
            lines, triggers, reb_pct, cur_pct = analyze(s)
            blocks.append("\n".join(lines))
            all_triggers.extend(triggers)
            if s["ticker"] == "MU":
                mu_reb = reb_pct
        except Exception as e:
            blocks.append("[%s] 조회 실패: %s" % (s["name"], e))
            all_triggers.append("⚠ %s 데이터 조회 실패 — 수동 확인 필요" % s["name"])

    # 마이크론 선행 신호 요약
    if mu_reb is not None:
        if mu_reb >= 88:
            watch = "MU 88% 통과 — 3사 통상형 청신호"
        elif mu_reb >= 84:
            watch = "MU $1,019(84%) 돌파, 무인지대 진행 중 — $1,067(88%) 안착 확인 대기"
        else:
            watch = "관찰: MU 반등고점 %.0f%% — $1,019(84%%) 돌파 여부가 첫 판별 신호" % mu_reb
    else:
        watch = "관찰: MU 데이터 없음"

    msg = header + "\n\n" + "\n\n".join(blocks) + "\n\n" + watch
    if all_triggers:
        msg += "\n\n" + "\n".join(all_triggers)

    if not send_telegram(msg):
        sys.exit(1)
    print("sent", now.isoformat())


if __name__ == "__main__":
    main()
