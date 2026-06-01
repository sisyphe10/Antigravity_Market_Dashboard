"""
Featured 병렬검증: 기존(featured_data.json, KRX) vs KIS(featured_data_kis.json) 비교.

같은 날짜에 대해 랭킹 타입별로:
- 양쪽 건수
- top-N 종목코드 교집합 비율 (겹침/기존N)
- 상위 랭크 불일치 일부

10거래일 누적 비교 후 컷오버 판단. 신고가(newhigh_*)는 KIS 범위 밖이라 제외.

사용: python compare_featured.py [YYYY-MM-DD]   (생략 시 KIS 파일의 ranked_at 날짜)
"""
import sys
import json
from collections import defaultdict

try:
    sys.stdout.reconfigure(encoding='utf-8')
except Exception:
    pass

RANK_TYPES = ['absolute', 'turnover', 'kospi_cap', 'kosdaq_cap', 'kospi_chg', 'kosdaq_chg']


def load_existing(date):
    with open('featured_data.json', encoding='utf-8') as f:
        data = json.load(f)
    out = defaultdict(list)
    for r in data:
        if r['d'] == date and r['type'] in RANK_TYPES:
            out[r['type']].append(r)
    for t in out:
        out[t].sort(key=lambda x: x['rank'])
    return out


def load_kis(date):
    with open('featured_data_kis.json', encoding='utf-8') as f:
        obj = json.load(f)
    recs = obj.get('records', []) if isinstance(obj, dict) else obj   # bare array 호환
    out = defaultdict(list)
    for r in recs:
        if r['d'] == date and r['type'] in RANK_TYPES:
            out[r['type']].append(r)
    for t in out:
        out[t].sort(key=lambda x: x['rank'])
    return out, {}


def main():
    date = sys.argv[1] if len(sys.argv) > 1 else None
    if date is None:
        with open('featured_data_kis.json', encoding='utf-8') as f:
            obj = json.load(f)
        recs = obj.get('records', []) if isinstance(obj, dict) else obj
        date = max((r['d'] for r in recs), default='')
    kis, _ = load_kis(date)

    existing = load_existing(date)
    print(f"=== Featured 비교 {date} ===")
    if not any(existing.values()):
        print(f"[주의] 기존 featured_data.json에 {date} 데이터 없음 → 같은 날 양쪽 생성 후 비교 필요(배포 후 VM에서)")

    for t in RANK_TYPES:
        ex = existing.get(t, [])
        ks = kis.get(t, [])
        ex_codes = [r['code'] for r in ex]
        ks_codes = [r['code'] for r in ks]
        ex_set, ks_set = set(ex_codes), set(ks_codes)
        inter = ex_set & ks_set
        denom = len(ex_set) or 1
        overlap = len(inter) / denom * 100
        print(f"\n[{t}] 기존 {len(ex)} / KIS {len(ks)}  | 교집합 {len(inter)}/{len(ex_set)} ({overlap:.0f}%)")
        if ex and ks:
            only_ex = [c for c in ex_codes if c not in ks_set][:5]
            only_ks = [c for c in ks_codes if c not in ex_set][:5]
            if only_ex:
                print(f"   기존에만(상위5): {only_ex}")
            if only_ks:
                print(f"   KIS에만(상위5):  {only_ks}")
            # 상위 10 랭크 일치 여부
            mism = [(i + 1, ex_codes[i], ks_codes[i])
                    for i in range(min(10, len(ex_codes), len(ks_codes)))
                    if ex_codes[i] != ks_codes[i]]
            if mism:
                print(f"   상위10 랭크 불일치: {mism[:5]}")
            else:
                print("   상위10 랭크 일치 ✓")


if __name__ == '__main__':
    main()
