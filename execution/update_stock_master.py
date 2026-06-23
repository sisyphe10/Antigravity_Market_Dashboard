"""주간 종목 마스터 자동 갱신 (KRX 신규상장 / 사명변경 → Wrap_NAV.xlsx 'Code' 시트).

동작:
  1) 사명 변경: 기존 종목 중 pykrx(KRX공식)==FDR 두 소스가 동의하고 시트명과 다른 것만 반영
     (한 소스만 다르거나 빈값이면 절대 덮어쓰지 않음 → 오탐/일시장애 차단).
  2) 신규 상장: 현재 상장목록 − Code시트 − ETF − 스팩. 섹터는 wics_all.json(FICS), 없으면 빈값.
  3) 폐지 종목: 삭제·변경하지 않고 보존 (과거 NEW/기여도 시트가 코드 참조).
  → stock_master.json 재생성 (create_portfolio_tables.py 와 동일 로직).

가드 (KRX 일시장애/포맷버그로 인한 대량 오염 방지):
  - 상장목록 < LISTED_FLOOR(1800) 이면 abort.
  - 신규 비율이 상장목록의 NEW_FRACTION_ABORT(40%) 초과면 abort (코드 포맷 불일치 의심).
  - 사명변경 > 1% 이면 경고 로그(백로그 일괄정정이면 정상).

멱등: 변경 없으면 파일을 건드리지 않음. 기본 dry-run, 실제 적용은 --apply.
로그만 (텔레그램 없음). 실패 시 systemd OnFailure 알림은 별도.
"""
import sys
import json
import argparse
import pandas as pd
import FinanceDataReader as fdr
from pykrx import stock

sys.stdout.reconfigure(encoding='utf-8')

FILE = 'Wrap_NAV.xlsx'
SHEET = 'Code'
WICS_FILE = 'wics_all.json'
MASTER_FILE = 'stock_master.json'

LISTED_FLOOR = 1800
NEW_FRACTION_ABORT = 0.40


def get_krx_names():
    """pykrx 공식 현재명 + 시장구분."""
    names, market_of = {}, {}
    for mkt in ['KOSPI', 'KOSDAQ', 'KONEX']:
        for t in stock.get_market_ticker_list(market=mkt):
            try:
                names[t] = stock.get_market_ticker_name(t).strip()
            except Exception:
                names[t] = ''
            market_of[t] = mkt
    return names, market_of


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--apply', action='store_true', help='실제 파일 수정 (미지정 시 dry-run)')
    args = ap.parse_args()

    cdf = pd.read_excel(FILE, sheet_name=SHEET)
    cols = list(cdf.columns)  # 종목명, 종목코드, 시장구분, 섹터
    cdf['_c'] = cdf['종목코드'].apply(lambda x: str(x).zfill(6))
    have = set(cdf['_c'])
    old_name = dict(zip(cdf['_c'], cdf['종목명'].astype(str).str.strip()))

    pk, market_of = get_krx_names()
    if len(pk) < LISTED_FLOOR:
        print(f"[ABORT] KRX 상장목록 비정상 {len(pk)}건 < {LISTED_FLOOR} — 중단")
        sys.exit(1)

    krx = fdr.StockListing('KRX')
    ccol = [c for c in krx.columns if c.lower() in ('code', 'symbol')][0]
    ncol = [c for c in krx.columns if c.lower() == 'name'][0]
    fd = dict(zip(krx[ccol].astype(str).str.zfill(6), krx[ncol].astype(str).str.strip()))

    etf = set(stock.get_etf_ticker_list()) if hasattr(stock, 'get_etf_ticker_list') else set()
    wics = {str(x.get('code')).zfill(6): (x.get('sector') or '')
            for x in json.load(open(WICS_FILE, encoding='utf-8'))}

    # 1) 사명 변경 (두 소스 동의 + 시트명과 다름)
    renames = {}
    for c in have:
        p, f = pk.get(c), fd.get(c)
        if p and p == f and p != old_name.get(c):
            renames[c] = p
    if len(renames) > len(have) * 0.01:
        print(f"[WARN] 사명변경 {len(renames)}건 (>1%) — 백로그 일괄정정이면 정상")

    # 2) 신규 상장 (ETF/스팩 제외)
    new_real = [c for c in pk
                if c not in have and c not in etf and '스팩' not in pk.get(c, '')]
    frac = len(new_real) / max(1, len(pk))
    if frac > NEW_FRACTION_ABORT:
        print(f"[ABORT] 신규 {len(new_real)}건 ({frac:.0%}) > {NEW_FRACTION_ABORT:.0%} "
              f"— 코드 포맷버그 의심, 중단")
        sys.exit(1)

    no_sector = sum(1 for c in new_real if not wics.get(c))
    print(f"[요약] 사명변경 {len(renames)}건 | 신규추가 {len(new_real)}건"
          f"(ETF·스팩 제외, 섹터미상 {no_sector}) | 폐지 보존")

    if not renames and not new_real:
        print("변경 없음 — 파일 미수정 (멱등)")
        return

    if not args.apply:
        print("(dry-run) --apply 미지정 → 저장 안 함. 샘플:")
        for c in list(renames)[:15]:
            print(f"  ~ {c} {old_name[c]} → {renames[c]}")
        for c in new_real[:15]:
            print(f"  + {c} {pk.get(c)} [{market_of.get(c)}] 섹터={wics.get(c, '')}")
        return

    # 적용: 사명 변경
    for i, row in cdf.iterrows():
        c = row['_c']
        if c in renames:
            cdf.at[i, '종목명'] = renames[c]
    # 종목코드 일관 정규화 (zfill str)
    cdf['종목코드'] = cdf['_c']
    cdf = cdf.drop(columns=['_c'])

    # 적용: 신규 추가
    new_rows = [{'종목명': pk.get(c, ''), '종목코드': c,
                 '시장구분': market_of.get(c, ''), '섹터': wics.get(c, '')}
                for c in new_real]
    out = pd.concat([cdf, pd.DataFrame(new_rows)[cols]], ignore_index=True) if new_rows else cdf

    with pd.ExcelWriter(FILE, engine='openpyxl', mode='a', if_sheet_exists='replace') as w:
        out.to_excel(w, sheet_name=SHEET, index=False)

    # stock_master.json 재생성 (create_portfolio_tables.py 동일 로직)
    master = []
    for _, r in out.iterrows():
        code = str(r['종목코드']).zfill(6)
        name = r.get('종목명')
        sector = r.get('섹터')
        if not code or pd.isna(name):
            continue
        master.append({'code': code, 'name': str(name),
                       'sector': '' if pd.isna(sector) else str(sector)})
    with open(MASTER_FILE, 'w', encoding='utf-8') as f:
        json.dump(master, f, ensure_ascii=False)

    print(f"[저장] Code 시트 {len(out)}행, {MASTER_FILE} {len(master)}종목")


if __name__ == '__main__':
    main()
