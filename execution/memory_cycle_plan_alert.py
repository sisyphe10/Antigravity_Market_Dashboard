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


# ── DRAM 현물/고정가 감시 (백워데이션 전조) ─────────────────────
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120 Safari/537.36"
SPOT_LOG = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                        "logs", "dram_spot_log.csv")
# 고정거래가 상수 — 트렌드포스/DRAMeXchange 월별 발표 감지 시 수동 갱신 (미등록=None)
CONTRACT = {
    "DDR5": {"price": None, "month": None},   # DDR5 16Gb (2Gx8) 고정가
    "DDR4": {"price": None, "month": None},   # DDR4 8Gb (1Gx8) 고정가
}


def fetch_dram_spot():
    """DRAMeXchange 홈 무료 현물 표에서 주력 품목 평균가 추출."""
    import re as _re
    req = urllib.request.Request("https://www.dramexchange.com/", headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=25) as r:
        html = r.read().decode("utf-8", "ignore")
    out = {}
    for row in _re.findall(r"<tr[^>]*>(.*?)</tr>", html, _re.S):
        txt = _re.sub(r"<[^>]+>", " ", row)
        txt = _re.sub(r"\s+", " ", txt).strip()
        if "eTT" in txt:
            continue
        for key, label in (("DDR5", "DDR5 16Gb (2Gx8) 4800/5600 "), ("DDR4", "DDR4 8Gb (1Gx8) 3200 ")):
            if txt.startswith(label) and key not in out:
                nums = _re.findall(r"\d+(?:\.\d+)?", txt[len(label):])
                if len(nums) >= 5:
                    out[key] = float(nums[4])   # 세션 평균가
    return out


def spot_log_update(spot, today):
    """일별 현물가 로그 append (같은 날짜 중복 기록 방지). 5일 전 값 반환."""
    rows = []
    if os.path.exists(SPOT_LOG):
        with open(SPOT_LOG) as f:
            rows = [l.strip().split(",") for l in f if l.strip()]
    if not rows or rows[-1][0] != today:
        os.makedirs(os.path.dirname(SPOT_LOG), exist_ok=True)
        with open(SPOT_LOG, "a") as f:
            f.write("%s,%s,%s\n" % (today, spot.get("DDR5", ""), spot.get("DDR4", "")))
        rows.append([today, str(spot.get("DDR5", "")), str(spot.get("DDR4", ""))])
    prev = rows[-6] if len(rows) >= 6 else None
    return prev


def spot_section():
    """현물/고정 라인 + 트리거 목록 반환."""
    triggers = []
    try:
        spot = fetch_dram_spot()
        if not spot:
            return "현물/고정: 조회 실패(표 구조 변경?)", triggers
        today = datetime.now(KST).strftime("%Y-%m-%d")
        prev = spot_log_update(spot, today)
        parts = []
        for key in ("DDR5", "DDR4"):
            if key not in spot:
                continue
            sp = spot[key]
            seg = "%s $%.1f" % (key, sp)
            if prev:
                try:
                    p = float(prev[1 if key == "DDR5" else 2])
                    seg += " (5일 %+.1f%%)" % ((sp / p - 1) * 100)
                except (ValueError, IndexError):
                    pass
            ct = CONTRACT[key]
            if ct["price"]:
                prem = (sp / ct["price"] - 1) * 100
                seg += " /고정 $%.1f(%s) %+.0f%%" % (ct["price"], ct["month"], prem)
                if prem < 0:
                    triggers.append("⚠ 백워데이션: %s 현물($%.1f)이 고정가($%.1f, %s) 하회 — 과거 1~2분기 내 고정가 정점 전환" % (key, sp, ct["price"], ct["month"]))
            else:
                seg += " /고정 미등록"
            parts.append(seg)
        # 현물 하락 전환 전조: 5일 변화율 -5% 이하
        if prev:
            for key, idx in (("DDR5", 1), ("DDR4", 2)):
                try:
                    p = float(prev[idx])
                    if key in spot and (spot[key] / p - 1) * 100 <= -5:
                        triggers.append("⚠ %s 현물 5일 -5%% 이상 하락 — 백워데이션 전조 주시" % key)
                except (ValueError, IndexError):
                    pass
        return "현물: " + " · ".join(parts), triggers
    except Exception as e:
        return "현물/고정: 조회 실패(%s)" % type(e).__name__, triggers


def contract_news_line():
    """트렌드포스 최근 기사 제목에서 고정가 발표 감지 (최근 2일)."""
    try:
        url = "https://www.trendforce.com/news/wp-json/wp/v2/posts?per_page=50&_fields=date,title"
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=25) as r:
            posts = json.loads(r.read().decode())
        import re as _re
        cutoff = (datetime.now(KST) - timedelta(days=2)).strftime("%Y-%m-%d")
        for p in posts:
            if p.get("date", "")[:10] < cutoff:
                continue
            t = _re.sub(r"<[^>]+>", "", p.get("title", {}).get("rendered", ""))
            if _re.search(r"contract\s+price|fixed\s+price", t, _re.I):
                return "📰 고정가 발표 감지: %s" % t[:80]
    except Exception:
        pass
    return None


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
    started = reb_high is not None and reb_high >= low * 1.05   # 저점 대비 +5% 이상이면 '반등 개시'

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
        "<b>%s %s · 정점비 %.0f%%</b>\n"
        "저점: 통상 %s%s | 약세 %s\n"
        "반등: 통상 %s~%s | 약세 ~%s"
    ) % (
        s["name"], fmt(last, s), cur_pct,
        fmt(s["norm_low"], s), below, fmt(s["bear_low"], s),
        fmt(s["band"][0], s), fmt(s["band"][1], s), fmt(s["bear_reb"], s),
    )
    info = {"reb_pct": reb_pct, "started": started, "last": last,
            "post_low_high": max(last, reb_high or 0)}
    return block, triggers, info


def send_telegram(text):
    token = os.environ.get("TELEGRAM_SISYPHE_BOT_TOKEN", "")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "")
    if not token or not chat_id:
        sys.stderr.write("memory_cycle_plan_alert: missing telegram env\n")
        return False
    body = urllib.parse.urlencode({"chat_id": chat_id, "text": text, "parse_mode": "HTML"}).encode()
    req = urllib.request.Request("https://api.telegram.org/bot%s/sendMessage" % token, data=body)
    with urllib.request.urlopen(req, timeout=30) as res:
        return bool(json.load(res).get("ok"))


def main():
    now = datetime.now(KST)
    blocks, all_triggers, infos = [], [], {}
    for s in STOCKS:
        try:
            block, triggers, info = analyze(s)
            blocks.append(block)
            all_triggers.extend(triggers)
            infos[s["name"]] = info
        except Exception as e:
            blocks.append("%s  조회 실패: %s" % (s["name"], e))
            all_triggers.append("⚠ %s 데이터 조회 실패 — 수동 확인 필요" % s["name"])

    # 예/아니오 관문 3개: ①반등 개시(어느 한 종목이라도 저점 대비 +5%) ②MU $1,019(84%) 도달 ③무인지대(88%) 통과
    def mark(b):
        return "O" if b else "X"
    g1 = any(i["started"] for i in infos.values())
    mu = infos.get("마이크론")
    g2 = bool(mu and mu["post_low_high"] >= 1019)
    g3 = any(i["reb_pct"] is not None and i["reb_pct"] >= 88 for i in infos.values())

    spot_line, spot_triggers = spot_section()
    all_triggers.extend(spot_triggers)
    news = contract_news_line()

    wd = ["월", "화", "수", "목", "금", "토", "일"][now.weekday()]
    msg = "<b>&lt; 메모리 플랜 %s(%s) &gt;</b>\n\n" % (now.strftime("%m.%d"), wd)
    msg += "\n\n".join(blocks)
    msg += "\n\n* 판별 = MU $1,020(84%) 돌파 여부"
    msg += "\n* 체크: 반등 개시? %s · MU $1,020 돌파? %s · 84~88%% 통과? %s" % (mark(g1), mark(g2), mark(g3))
    msg += "\n" + spot_line
    if news:
        msg += "\n" + news
    if all_triggers:
        msg += "\n" + "\n".join(all_triggers)

    if not send_telegram(msg):
        sys.exit(1)
    print("sent", now.isoformat())


if __name__ == "__main__":
    main()
