"""KOSPI 200 + KOSDAQ 150 합산 벤치마크 섹터 비중 계산

pykrx 사용:
 - KOSPI 시총 상위 200 + KOSDAQ 시총 상위 150 → 벤치마크 섹터 비중
 - KOSPI + KOSDAQ 전종목 코드→KRX 표준 업종명 매핑 저장
결과: kodex_sectors.json (프로젝트 루트)
"""

import sys
import json
import pandas as pd
from datetime import datetime, timedelta

sys.stdout.reconfigure(encoding='utf-8')

OUTPUT_FILE = 'kodex_sectors.json'

# 벤치마크 구성: KOSPI 상위 N개 + KOSDAQ 상위 N개
KOSPI_TOP_N = 200
KOSDAQ_TOP_N = 150


def get_recent_trading_date():
    """가장 최근 영업일 반환 (주말 제외, 최대 7일 전까지)"""
    today = datetime.now()
    for i in range(7):
        dt = today - timedelta(days=i)
        if dt.weekday() < 5:  # 0=Mon, 4=Fri
            return dt.strftime('%Y%m%d')
    return today.strftime('%Y%m%d')


def fetch_market_sectors(date_str, market):
    """KOSPI 또는 KOSDAQ 전종목 섹터+시총 데이터 반환"""
    from pykrx import stock
    df = stock.get_market_sector_classifications(date_str, market)
    if df is None or len(df) == 0:
        print(f"  {market} 데이터 없음 ({date_str})")
        return pd.DataFrame()
    cap_col = next((c for c in ['시가총액', 'MktCap', 'Cap'] if c in df.columns), None)
    sector_col = next((c for c in ['업종명', '업종', 'Sector'] if c in df.columns), None)
    if cap_col is None or sector_col is None:
        print(f"  {market} 필요 컬럼 없음: {df.columns.tolist()}")
        return pd.DataFrame()
    df = df[[sector_col, cap_col]].copy()
    df.columns = ['업종명', '시가총액']
    df['시가총액'] = pd.to_numeric(df['시가총액'], errors='coerce').fillna(0)
    df = df[df['시가총액'] > 0]
    print(f"  {market}: {len(df)}개 종목")
    return df


def fetch_all():
    """KOSPI + KOSDAQ 데이터 수집 및 벤치마크/매핑 계산"""
    try:
        from pykrx import stock as _  # import 확인용
    except ImportError:
        print("pykrx 미설치. pip install pykrx --no-deps")
        return None, None

    date_str = get_recent_trading_date()
    print(f"기준 날짜: {date_str}")

    from pykrx import stock

    # --- KOSPI ---
    print("KOSPI 섹터 데이터 로드 중...")
    df_kospi = fetch_market_sectors(date_str, 'KOSPI')

    # --- KOSDAQ ---
    print("KOSDAQ 섹터 데이터 로드 중...")
    df_kosdaq = fetch_market_sectors(date_str, 'KOSDAQ')

    if df_kospi.empty and df_kosdaq.empty:
        return None, None

    # --- stock_sector_map: 종목코드(str) → KRX 업종명 ---
    # KOSPI 전종목 + KOSDAQ 전종목 재조회 (업종명만 필요)
    print("전종목 코드→업종명 매핑 생성 중...")
    stock_sector_map = {}
    for market in ['KOSPI', 'KOSDAQ']:
        try:
            df_full = stock.get_market_sector_classifications(date_str, market)
            sector_col = next((c for c in ['업종명', '업종', 'Sector'] if c in df_full.columns), None)
            if sector_col and len(df_full) > 0:
                for code, row in df_full.iterrows():
                    stock_sector_map[str(code).zfill(6)] = str(row[sector_col])
        except Exception as e:
            print(f"  {market} 매핑 실패: {e}")
    print(f"  총 {len(stock_sector_map)}개 종목 매핑 완료")

    # --- 벤치마크: KOSPI top 200 + KOSDAQ top 150 (시총 가중) ---
    frames = []
    if not df_kospi.empty:
        frames.append(df_kospi.sort_values('시가총액', ascending=False).head(KOSPI_TOP_N))
    if not df_kosdaq.empty:
        frames.append(df_kosdaq.sort_values('시가총액', ascending=False).head(KOSDAQ_TOP_N))

    df_bench = pd.concat(frames)
    total_cap = df_bench['시가총액'].sum()
    df_bench = df_bench.copy()
    df_bench['_w'] = df_bench['시가총액'] / total_cap * 100

    benchmark_sectors = (
        df_bench.groupby('업종명')['_w']
        .sum()
        .round(2)
        .sort_values(ascending=False)
        .to_dict()
    )

    print(f"\n벤치마크 섹터 비중 (KOSPI {KOSPI_TOP_N} + KOSDAQ {KOSDAQ_TOP_N}):")
    for s, w in benchmark_sectors.items():
        print(f"  {s}: {w:.2f}%")

    return benchmark_sectors, stock_sector_map


if __name__ == '__main__':
    print("=== KOSPI 200 + KOSDAQ 150 벤치마크 섹터 비중 계산 ===")
    sectors, stock_sector_map = fetch_all()

    if sectors:
        result = {
            'updated': datetime.now().strftime('%Y-%m-%d'),
            'description': f'KOSPI 시총 상위 {KOSPI_TOP_N} + KOSDAQ 시총 상위 {KOSDAQ_TOP_N} 기준',
            'sectors': sectors,
            'stock_sector_map': stock_sector_map or {},
        }
        with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
        print(f"\n✅ 저장: {OUTPUT_FILE}")
    else:
        print("❌ 데이터 계산 실패 (kodex_sectors.json 유지)")
