# -*- coding: utf-8 -*-
"""위키 백엔드 A/B 평가 — 같은 질문을 API(/ask)와 headless 양쪽에 태워 비교.

실행: venv/bin/python3 datalake/webui/ab_eval.py
★2026-08-05 API 경로(/ask) 제거로 api 측은 더 이상 동작하지 않는다 — 이 스크립트는 이력 보존용.
결과: ~/datalake/ab_eval_latest.json  (테스트 페이지 /wiki/test/headless/ab 가 읽음)
★API 쪽은 실제 과금된다. 문항 수를 늘리기 전에 비용을 확인할 것.
"""
import json
import os
import sys
import time
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import headless_backend  # noqa: E402

DATALAKE_ROOT = os.path.expanduser(os.getenv("DATALAKE_ROOT", "~/datalake"))
OUT = os.path.join(DATALAKE_ROOT, "ab_eval_latest.json")
API_URL = "http://127.0.0.1:8787/ask"

QUESTIONS = [
    ("SQL", "삼성전자(005930)의 최근 5거래일 수정종가를 날짜와 함께 표로 보여줘."),
    ("SQL", "2026년 들어 KOSPI 지수의 최고 종가와 그 날짜는?"),
    ("SQL", "SK하이닉스(000660)의 가장 최근 외국인 보유비중은 얼마이고 기준일은 언제야?"),
    ("태그", "한화에어로스페이스에 대한 최근 리서치 언급을 3건만 날짜·출처와 함께 요약해줘."),
    ("단일문서", "2026-07-31 CCJ(카메코) 어닝콜에서 경영진이 강조한 핵심 3가지는?"),
    ("다중출처", "최근 리서치에서 HBM에 대한 논조를 종합해줘. 긍정·부정 근거를 날짜와 함께."),
    ("가정형", "두산에너빌리티가 AP1000 1기를 수주하면 해당 금액이 얼마냐"),
    ("근거없음", "짐바브웨 증권거래소의 2027년 예상 배당수익률이 코퍼스에 있어?"),
    ("시스템위키", "위키 태그 인덱스는 어떤 잡이 몇 시에 갱신해?"),
    ("SQL+해석", "2026년 들어 외국인 순매수 누적 흐름이 어떻게 됐는지 수치로 보여주고 해석해줘."),
]


def ask_api(q, timeout=900):
    body = json.dumps({"question": q, "history": []}).encode("utf-8")
    req = urllib.request.Request(API_URL, data=body,
                                 headers={"Content-Type": "application/json"})
    t0 = time.time()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            d = json.loads(r.read().decode("utf-8"))
        return {"ok": True, "answer": d.get("answer", ""),
                "steps": [s.get("tool") for s in d.get("steps") or []],
                "elapsed": round(time.time() - t0, 1),
                "cost_usd": (d.get("usage") or {}).get("cost_usd"),
                "error": None}
    except Exception as e:
        return {"ok": False, "answer": "", "steps": [],
                "elapsed": round(time.time() - t0, 1), "cost_usd": None,
                "error": "%s: %s" % (type(e).__name__, e)}


def ask_headless(q):
    t0 = time.time()
    out = headless_backend.run_question(q)
    return {"ok": bool(out.get("ok")), "answer": out.get("answer") or "",
            "steps": [s["tool"] for s in out.get("steps") or []],
            "elapsed": round(time.time() - t0, 1),
            "turns": (out.get("meta") or {}).get("num_turns"),
            "notional_cost_usd": (out.get("meta") or {}).get("notional_cost_usd"),
            "error": out.get("error")}


def main():
    rows, total_api_cost = [], 0.0
    for i, (cat, q) in enumerate(QUESTIONS, 1):
        print("[%d/%d] %s | %s" % (i, len(QUESTIONS), cat, q[:40]), flush=True)
        h = ask_headless(q)
        print("    headless %s %.0fs" % (h["ok"], h["elapsed"]), flush=True)
        a = ask_api(q)
        print("    api      %s %.0fs $%s" % (a["ok"], a["elapsed"], a["cost_usd"]), flush=True)
        total_api_cost += (a.get("cost_usd") or 0)
        rows.append({"n": i, "category": cat, "question": q,
                     "headless": h, "api": a})
        with open(OUT, "w", encoding="utf-8") as fh:
            json.dump({"generated_at": time.time(), "rows": rows,
                       "total_api_cost_usd": round(total_api_cost, 4)},
                      fh, ensure_ascii=False, indent=1)
    print("DONE. API 누적 비용 $%.4f → %s" % (total_api_cost, OUT), flush=True)


if __name__ == "__main__":
    main()
