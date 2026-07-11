# -*- coding: utf-8 -*-
"""금투협 증시 수급 자금 이력 백필 → kr_flows parquet.

소스: data.go.kr 금융위원회_금융투자협회종합통계 (GetKofiaStatisticsInfoService)
- getSecuritiesMarketTotalCapitalInfo: 투자자예탁금·파생예수금·RP·미수금·반대매매
- getGrantingOfCreditBalanceInfo: 신용거래융자(전체/코스피/코스닥)·대주·담보융자

금액은 원 → 억원 환산 저장. 날짜 미지정 시 최신일 내림차순 페이지네이션으로
가용 전 기간 수집. 일일 증분도 이 스크립트 재실행으로 충분(upsert 멱등).

키: env DATA_GO_KR_API_KEY 또는 REPO/secrets/api_keys.env
사용: python3 datalake/backfill_kofia.py [--pages N (기본 전체)]
"""
import argparse
import json
import os
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from dl_common import REPO, merge_into_year_files

DATASET = "kr_flows"
BASE = "http://apis.data.go.kr/1160100/service/GetKofiaStatisticsInfoService"
ROWS_PER_PAGE = 500
PACE_SEC = 0.3
EOK = 1e-8  # 원 → 억원

# 오퍼레이션별 (필드 → 시리즈명, 스케일)  스케일 None=원값 유지(%)
OPERATIONS = {
    "getSecuritiesMarketTotalCapitalInfo": {
        "invrDpsgAmt": ("투자자예탁금", EOK),
        "onbdDrvPrdTrRcAdvAmt": ("장내파생 거래예수금", EOK),
        "toCstRpchCndBndSlgBal": ("대고객 RP 매도잔고", EOK),
        "brkTrdUcolMny": ("위탁매매 미수금", EOK),
        "brkTrdUcolMnyVsOppsTrdAmt": ("미수금 반대매매금액", EOK),
        "ucolMnyVsOppsTrdRlImpt": ("반대매매 비중", None),
    },
    "getGrantingOfCreditBalanceInfo": {
        "crdTrFingWhl": ("신용거래융자", EOK),
        "crdTrFingScrs": ("신용거래융자 코스피", EOK),
        "crdTrFingKosdaq": ("신용거래융자 코스닥", EOK),
        "crdTrLndrWhl": ("신용거래대주", EOK),
        "sbscCapLn": ("청약자금대출", EOK),
        "dpsgScrtMogFing": ("예탁증권담보융자", EOK),
    },
}


def load_key():
    from dl_common import load_api_key
    return load_api_key("DATA_GO_KR_API_KEY")


def fetch_page(key, op, page):
    qs = urllib.parse.urlencode({
        "serviceKey": key, "numOfRows": ROWS_PER_PAGE, "pageNo": page,
        "resultType": "json"})
    req = urllib.request.Request(f"{BASE}/{op}?{qs}",
                                 headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=30) as r:
        payload = json.loads(r.read().decode("utf-8"))
    body = payload.get("response", {}).get("body", {})
    items = body.get("items", {})
    rows = items.get("item", []) if isinstance(items, dict) else []
    return rows, int(body.get("totalCount", 0))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pages", type=int, help="최대 페이지 수 (기본 전체)")
    args = ap.parse_args()

    import pandas as pd
    key = load_key()
    if not key:
        print("ERROR: DATA_GO_KR_API_KEY 없음 (env 또는 secrets/api_keys.env)")
        return 1

    frames = []
    for op, fields in OPERATIONS.items():
        recs, page = [], 1
        while True:
            time.sleep(PACE_SEC)
            try:
                rows, total = fetch_page(key, op, page)
            except Exception as e:
                print(f"  ! {op} p{page}: {type(e).__name__}: {e}", flush=True)
                break
            if not rows:
                break
            for r in rows:
                bas = str(r.get("basDt", "")).strip()
                if len(bas) != 8:
                    continue
                d = datetime.strptime(bas, "%Y%m%d").date()
                for field, (series, scale) in fields.items():
                    v = r.get(field)
                    if v in (None, "", "-"):
                        continue
                    try:
                        val = float(str(v).replace(",", ""))
                    except ValueError:
                        continue
                    if scale:
                        val = round(val * scale, 1)  # 억원
                    recs.append((d, series, val))
            if page * ROWS_PER_PAGE >= total or (args.pages and page >= args.pages):
                break
            page += 1
        if recs:
            frames.append(pd.DataFrame(recs, columns=["date", "series", "value"]))
            print(f"  ✓ {op}: {len(recs):,}레코드 (p{page}까지)", flush=True)
        else:
            print(f"  - {op}: 데이터 없음 (미신청 403이면 data.go.kr 활용신청 확인)", flush=True)

    if not frames:
        return 1
    df = pd.concat(frames, ignore_index=True)
    df["source"] = "KOFIA"
    merge_into_year_files(DATASET, df, ["date", "series"])
    print(f"완료: 총 {len(df):,}행 → {DATASET}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
