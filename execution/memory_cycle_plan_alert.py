# -*- coding: utf-8 -*-
"""memory_cycle_plan_alert.py — 메모리 3사 사이클 액션플랜 일일 점검 텔레그램 알림.

기준: work/analysis/260719_메모리3사_주가실적PER/메모리3사_사이클_리포트.md (85% 판정 기준)
- 시나리오 판별: 저점 형성 후 반등고점이 전고점의 84~88% '무인지대'를 통과하는지
- 통상형(기저율 80%): 반등 93~100% 도달이 관례 / 약세장형(20%): 천장 79~84%
- 반등고점 = "-20% 앵커 이후 최저점"이 나온 뒤의 최고 종가 (초기 하락기의 되돌림은 제외)
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
        "name": "삼성전자", "ticker": "005930.KS", "cur": "KRW", "unit": 1000,
        "peak": 362500, "anchor": "2026-07-02",
        "norm_low": 248900,                         # 통상형 중앙 저점(-31%)
        "bear_low": 190900,                         # 약세장형 중앙 저점(-47%)
        "band": (338400, 360900),                   # 통상형 반등(93~100%)
        "bear_reb": 301000,                         # 약세장형 반등 천장(~83%)
        "confirm88": 319000,                        # 통상형 확인선(88%) — 트리거용
        "deep25": 239700,                           # 통상형 깊은25% 저점(-34%) — 트리거용
    },
    {
        "name": "SK하이닉스", "ticker": "000660.KS", "cur": "KRW", "unit": 10000,
        "peak": 2919000, "anchor": "2026-07-02",
        "norm_low": 1973500,
        "bear_low": 1230700,
        "band": (2808500, 2885700),
        "bear_reb": 2410100,
        "confirm88": 2568700,
        "deep25": 1792200,
    },
    {
        "name": "마이크론", "ticker": "MU", "cur": "USD", "unit": 10,
        "peak": 1213.0, "anchor": "2026-07-07",
        "norm_low": 846.0,
        "bear_low": 514.0,
        "band": (1160.0, 1204.0),
        "bear_reb": 1016.0,
        "confirm88": 1067.0,
        "deep25": 746.0,
    },
]


def fmt(v, s):
    # 표기 반올림 (2026-07-19 사용자 확정): 삼전=천원·하이닉스=만원·MU=십달러. half-up 고정(파이썬 round는 은행가 반올림)
    u = s["unit"]
    r = int(v / u + 0.5) * u
    if s["cur"] == "KRW":
        return f"{r:,d}"
    return f"${r:,d}"


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
    # 저점(앵커 이후 최저) → 그 이후의 최고 종가만 '반등고점'으로 인정
    low = float(since.min()) if len(since) else last
    low_date = since.idxmin() if len(since) else px.index[-1]
    after_low = since[since.index > low_date]
    reb_high = float(after_low.max()) if len(after_low) else None
    reb_pct = reb_high / s["peak"] * 100 if reb_high else None

    triggers = []
    # 이벤트 트리거 (발동 시에만 메시지 하단에 표시)
    if reb_pct is not None:
        if reb_pct >= 88 and cur_pct < 93:
            triggers.append("✅ %s 통상형 확인선(88%%) 통과 — 역사상 이후 전부 93%%+ 도달" % s["name"])
        if reb_pct >= 93:
            triggers.append("🎯 %s 통상형 목표밴드(93~100%%) 진입 — 잔여 처분 구간" % s["name"])
        if 83 <= reb_pct < 84:
            triggers.append("🔽 %s 반등이 약세장 천장(83~84%%) 도달 — 1차 축소 검토 구간" % s["name"])
        # 약세장 판정: 저점 후 반등고점이 81~88%에서 형성된 뒤 고점 대비 -10% 이탈
        if 81 <= reb_pct < 88 and last <= reb_high * 0.90:
            triggers.append("⚠ %s 약세장 판정: 반등고점(정점의 %.0f%%) -10%% 이탈 — 철수 검토" % (s["name"], reb_pct))
    # 통상형 깊은25% 저점 하회
    if last < s["deep25"]:
        triggers.append("⚠ %s 통상형 깊은25%%(%s) 하회 — 약세장 저점 %s 참조" % (s["name"], fmt(s["deep25"], s), fmt(s["bear_low"], s)))

    below = "(하회)" if last < s["norm_low"] else ""
    block = (
        "%s %s · 정점비 %.0f%%\n"
        "저점: 통상 %s%s | 약세 %s\n"
        "반등: 통상 %s~%s | 약세 ~%s"
    ) % (
        s["name"], fmt(last, s), cur_pct,
        fmt(s["norm_low"], s), below, fmt(s["bear_low"], s),
        fmt(s["band"][0], s), fmt(s["band"][1], s), fmt(s["bear_reb"], s),
    )
    return block, triggers, reb_pct


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
    blocks, all_triggers, rebs = [], [], {}
    for s in STOCKS:
        try:
            block, triggers, reb_pct = analyze(s)
            blocks.append(block)
            all_triggers.extend(triggers)
            rebs[s["name"]] = reb_pct
        except Exception as e:
            blocks.append("%s  조회 실패: %s" % (s["name"], e))
            all_triggers.append("⚠ %s 데이터 조회 실패 — 수동 확인 필요" % s["name"])

    def r(name):
        v = rebs.get(name)
        return "%.0f%%" % v if v is not None else "—"

    msg = "📐 메모리 플랜 %s\n\n" % now.strftime("%m/%d")
    msg += "\n\n".join(blocks)
    msg += "\n\n★판별 = MU $1,020(84%) 돌파 여부"
    msg += "\n✔오늘 체크: 저점 후 반등 삼전 %s · 닉스 %s · MU %s (84%% 도달 시 판별 개시)" % (
        r("삼성전자"), r("SK하이닉스"), r("마이크론"))
    if all_triggers:
        msg += "\n" + "\n".join(all_triggers)

    if not send_telegram(msg):
        sys.exit(1)
    print("sent", now.isoformat())


if __name__ == "__main__":
    main()
