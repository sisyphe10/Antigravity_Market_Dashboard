"""
KRX 외국인 보유비중 수집 → dataset.csv 적재

수집 대상 (8개 시리즈):
- 코스피/코스닥 지수단위 외국인 보유비중 (시총가중: Σ(보유수량×종가)/Σ(시가총액))
- 6종목 외국인 지분율: 삼성전자, 삼성전자우, SK하이닉스, 삼성생명, SK스퀘어, 삼성물산
  (6종목 모두 KOSPI 소속 → KOSPI by_ticker 결과에서 부산물 추출, 추가 호출 없음)

pykrx 사용 → KRX 로그인 필요 (환경변수 KRX_ID / KRX_PW).
  로컬:  set -a; source secrets/data.krx.txt; set +a
  GHA:   env KRX_ID / KRX_PW (repository secret)

일배치 1회 = 4 HTTP 콜 (KOSPI/KOSDAQ × by_ticker + market_cap).
증분 수집: 'KOSPI 외국인 보유비중'의 마지막 날짜 이후만. 없으면 BACKFILL_START부터.
차트는 create_dashboard.py(_build_foreign_ownership_section)가 dataset.csv를 읽어 생성.
"""
import os
import sys
import pandas as pd
from datetime import datetime, timedelta

DATASET_FILE = 'dataset.csv'
BACKFILL_START = '2025-01-01'
DATA_TYPE = 'INDEX_KR'          # CATEGORY_MAP에서 INDEX_KOREA로 매핑 (신규 타입 불필요)

# 지수 외국인 보유비중 (시장 → 제품명)
INDEX_PRODUCTS = {
    'KOSPI':  'KOSPI 외국인 보유비중',
    'KOSDAQ': 'KOSDAQ 외국인 보유비중',
}
# 개별종목 외국인 지분율 (코드 → 제품명). 6종목 모두 KOSPI.
STOCK_TARGETS = {
    '005930': '삼성전자 외국인 지분율',
    '005935': '삼성전자우 외국인 지분율',
    '000660': 'SK하이닉스 외국인 지분율',
    '032830': '삼성생명 외국인 지분율',
    '402340': 'SK스퀘어 외국인 지분율',
    '028260': '삼성물산 외국인 지분율',
}
MASTER_PRODUCT = 'KOSPI 외국인 보유비중'   # 증분 수집 기준 시리즈


def _market_foreign_ratio(stock_mod, date_str, market):
    """시장 외국인 보유비중(%) + (KOSPI일 때) 6종목 지분율 dict 반환.
    휴장일/빈응답이면 (None, {})."""
    # 휴장일엔 pykrx가 빈 응답을 KeyError(FORN_SHR_RT 등 컬럼 없음)로 던짐 → 휴장일로 간주
    try:
        fx = stock_mod.get_exhaustion_rates_of_foreign_investment_by_ticker(date_str, market)
        cap = stock_mod.get_market_cap_by_ticker(date_str, market=market)
    except KeyError:
        return None, {}
    if fx is None or fx.empty or cap is None or cap.empty:
        return None, {}
    df = fx.join(cap[['시가총액', '종가']], how='inner')
    foreign_cap = (df['보유수량'] * df['종가']).sum()
    total_cap = df['시가총액'].sum()
    ratio = round(foreign_cap / total_cap * 100, 4) if total_cap > 0 else None

    stock_ratios = {}
    if market == 'KOSPI':
        for code, name in STOCK_TARGETS.items():
            if code in fx.index:
                stock_ratios[name] = round(float(fx.loc[code, '지분율']), 4)
    return ratio, stock_ratios


def compute_for_date(stock_mod, date_str):
    """특정일 8개 시리즈 계산. 반환 {제품명: 값}. 휴장/실패면 빈 dict."""
    out = {}
    kospi_ratio, stock_ratios = _market_foreign_ratio(stock_mod, date_str, 'KOSPI')
    if kospi_ratio is None:
        return {}   # KOSPI가 비면 휴장일로 간주 → 전체 skip
    out[INDEX_PRODUCTS['KOSPI']] = kospi_ratio
    out.update(stock_ratios)

    kosdaq_ratio, _ = _market_foreign_ratio(stock_mod, date_str, 'KOSDAQ')
    if kosdaq_ratio is not None:
        out[INDEX_PRODUCTS['KOSDAQ']] = kosdaq_ratio
    return out


def main():
    if not (os.environ.get('KRX_ID') and os.environ.get('KRX_PW')):
        print("경고: KRX_ID/KRX_PW 환경변수 없음 → pykrx 로그인 실패 가능", file=sys.stderr)

    from pykrx import stock   # import 시 KRX 자동 로그인

    df = pd.read_csv(DATASET_FILE, encoding='utf-8-sig')

    existing = df[df['제품명'] == MASTER_PRODUCT]
    if not existing.empty:
        start = pd.to_datetime(existing['날짜']).max() + timedelta(days=1)
    else:
        start = pd.to_datetime(BACKFILL_START)

    today = pd.Timestamp(datetime.now().date())
    print(f"외국인 보유비중 수집: {start.strftime('%Y-%m-%d')} ~ {today.strftime('%Y-%m-%d')}")

    new_rows = []
    days_done = 0
    current = start
    while current <= today:
        if current.weekday() < 5:   # 평일만 (휴장일은 빈응답으로 추가 필터)
            date_str = current.strftime('%Y%m%d')
            try:
                vals = compute_for_date(stock, date_str)
            except Exception as e:
                print(f"  {current.strftime('%Y-%m-%d')}: 오류 {e!r}", file=sys.stderr)
                vals = {}
            if vals:
                for name, val in vals.items():
                    new_rows.append({
                        '날짜': current.strftime('%Y-%m-%d'),
                        '제품명': name,
                        '가격': val,
                        '데이터 타입': DATA_TYPE,
                    })
                days_done += 1
                if days_done % 20 == 0:
                    print(f"  ...{current.strftime('%Y-%m-%d')} 까지 {days_done}거래일 수집")
        current += timedelta(days=1)

    if new_rows:
        new_df = pd.DataFrame(new_rows)
        df = pd.concat([df, new_df], ignore_index=True)
        df['날짜'] = pd.to_datetime(df['날짜'])
        df = df.drop_duplicates(subset=['날짜', '제품명'], keep='last')
        df = df.sort_values('날짜')
        df['날짜'] = df['날짜'].dt.strftime('%Y-%m-%d')
        df.to_csv(DATASET_FILE, index=False, encoding='utf-8-sig')
        print(f"완료: {days_done}거래일, {len(new_rows)}행 추가")
    else:
        print("신규 데이터 없음")


if __name__ == '__main__':
    main()
