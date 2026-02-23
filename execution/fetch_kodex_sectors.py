"""KOSPI 200 + KOSDAQ 150 정확한 구성종목 기반 섹터 비중 계산

pykrx 사용:
 - KOSPI 200 (인덱스 코드 1028) + KOSDAQ 150 (2203) 실제 구성종목 조회
 - 각 구성종목의 시총 가중으로 섹터 비중 계산
 - KOSPI + KOSDAQ 전종목 코드→KRX 표준 업종명 매핑 저장
결과: kodex_sectors.json (프로젝트 루트)
"""

import sys
import json
import pandas as pd
from datetime import datetime, timedelta

sys.stdout.reconfigure(encoding='utf-8')

OUTPUT_FILE = 'kodex_sectors.json'

KOSPI200_TICKER  = '1028'   # KOSPI 200
KOSDAQ150_TICKER = '2203'   # KOSDAQ 150


def get_recent_trading_date():
    """가장 최근 영업일 반환 (주말 제외, 최대 7일 전까지)"""
    today = datetime.now()
    for i in range(7):
        dt = today - timedelta(days=i)
        if dt.weekday() < 5:
            return dt.strftime('%Y%m%d')
    return today.strftime('%Y%m%d')


def fetch_all():
    """KOSPI 200 + KOSDAQ 150 구성종목 기반 섹터 비중 계산"""
    try:
        from pykrx import stock
    except ImportError:
        print("pykrx 미설치. pip install pykrx --no-deps")
        return None, None

    date_str = get_recent_trading_date()
    print(f"기준 날짜: {date_str}")

    # 1. 인덱스 구성종목 조회 (ticker 먼저, date 두 번째)
    print("KOSPI 200 구성종목 조회 중...")
    kospi200_tickers = stock.get_index_portfolio_deposit_file(
        KOSPI200_TICKER, date_str, alternative=True
    )
    print(f"  → {len(kospi200_tickers)}개")

    print("KOSDAQ 150 구성종목 조회 중...")
    kosdaq150_tickers = stock.get_index_portfolio_deposit_file(
        KOSDAQ150_TICKER, date_str, alternative=True
    )
    print(f"  → {len(kosdaq150_tickers)}개")

    all_index_tickers = set(kospi200_tickers) | set(kosdaq150_tickers)

    if not all_index_tickers:
        print("구성종목 조회 실패")
        return None, None

    # 2. KOSPI + KOSDAQ 전종목 섹터 분류 데이터
    print("KOSPI 섹터 분류 로드 중...")
    df_kospi_all = stock.get_market_sector_classifications(date_str, 'KOSPI')
    print(f"  → {len(df_kospi_all)}개")

    print("KOSDAQ 섹터 분류 로드 중...")
    df_kosdaq_all = stock.get_market_sector_classifications(date_str, 'KOSDAQ')
    print(f"  → {len(df_kosdaq_all)}개")

    # 3. 전종목 stock_sector_map (코드 → KRX 표준 업종명)
    print("전종목 코드→업종명 매핑 생성 중...")
    stock_sector_map = {}
    for df in [df_kospi_all, df_kosdaq_all]:
        sector_col = next((c for c in ['업종명', '업종', 'Sector'] if c in df.columns), None)
        if sector_col:
            for code, row in df.iterrows():
                stock_sector_map[str(code).zfill(6)] = str(row[sector_col])
    print(f"  → 총 {len(stock_sector_map)}개 종목 매핑")

    # 4. 구성종목의 시총·업종 추출
    df_all = pd.concat([df_kospi_all, df_kosdaq_all])
    cap_col    = next((c for c in ['시가총액', 'MktCap', 'Cap'] if c in df_all.columns), None)
    sector_col = next((c for c in ['업종명', '업종', 'Sector'] if c in df_all.columns), None)

    if cap_col is None or sector_col is None:
        print(f"필요 컬럼 없음: 시총={cap_col}, 섹터={sector_col}")
        return None, None

    df_bench = df_all[df_all.index.astype(str).str.zfill(6).isin(all_index_tickers)].copy()
    df_bench[cap_col] = pd.to_numeric(df_bench[cap_col], errors='coerce').fillna(0)
    df_bench = df_bench[df_bench[cap_col] > 0]

    print(f"\n벤치마크 종목 수: {len(df_bench)} "
          f"(KOSPI200 {len(kospi200_tickers)} + KOSDAQ150 {len(kosdaq150_tickers)}, "
          f"섹터 데이터 매칭 후)")

    # 5. 시총 가중 섹터 비중 계산
    total_cap = df_bench[cap_col].sum()
    df_bench['_w'] = df_bench[cap_col] / total_cap * 100

    benchmark_sectors = (
        df_bench.groupby(sector_col)['_w']
        .sum()
        .round(2)
        .sort_values(ascending=False)
        .to_dict()
    )

    print("\n섹터 비중:")
    for s, w in benchmark_sectors.items():
        print(f"  {s}: {w:.2f}%")

    return benchmark_sectors, stock_sector_map


if __name__ == '__main__':
    print("=== KOSPI 200 + KOSDAQ 150 벤치마크 섹터 비중 계산 ===")
    sectors, stock_sector_map = fetch_all()

    if sectors:
        result = {
            'updated': datetime.now().strftime('%Y-%m-%d'),
            'description': 'KOSPI 200 + KOSDAQ 150 실제 구성종목 기준 (시총 가중)',
            'sectors': sectors,
            'stock_sector_map': stock_sector_map or {},
        }
        with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
        print(f"\n✅ 저장: {OUTPUT_FILE}")
    else:
        print("❌ 데이터 계산 실패 (kodex_sectors.json 유지)")
