"""KOSPI 200 + KOSDAQ 150 정확한 구성종목 기반 섹터 비중 계산

pykrx 사용:
 - KOSPI 200 (인덱스 코드 1028) + KOSDAQ 150 (2203) 실제 구성종목 조회
 - 각 구성종목의 시총 가중으로 섹터 비중 계산
 - KOSPI + KOSDAQ 전종목 코드→KRX 표준 업종명 매핑 저장
 - 전종목 시총 가중 1개월 섹터 수익률 계산
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
    """KOSPI 200 + KOSDAQ 150 구성종목 기반 섹터 비중 + 1M 수익률 계산"""
    try:
        from pykrx import stock
    except ImportError:
        print("pykrx 미설치. pip install pykrx --no-deps")
        return None, None, {}

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
        return None, None, {}

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
        return None, None, {}

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

    # 6. 1개월 섹터 수익률 계산 (전종목 시총 가중 평균)
    print("\n1M 섹터 수익률 계산 중...")
    sector_1m_returns = {}
    try:
        date_dt = datetime.strptime(date_str, '%Y%m%d')
        # 30일 전 가장 가까운 평일 찾기
        date_1m_str = None
        for i in range(37):
            candidate = date_dt - timedelta(days=30 + i)
            if candidate.weekday() < 5:
                date_1m_str = candidate.strftime('%Y%m%d')
                break
        if date_1m_str is None:
            raise ValueError("1M 기준일 산출 실패")
        print(f"  기준: {date_1m_str} → {date_str}")

        # 현재·1M 전 종가 조회
        now_k = stock.get_market_ohlcv_by_ticker(date_str,    market='KOSPI')[['종가']]
        now_q = stock.get_market_ohlcv_by_ticker(date_str,    market='KOSDAQ')[['종가']]
        ago_k = stock.get_market_ohlcv_by_ticker(date_1m_str, market='KOSPI')[['종가']]
        ago_q = stock.get_market_ohlcv_by_ticker(date_1m_str, market='KOSDAQ')[['종가']]

        df_now = pd.concat([now_k, now_q])
        df_ago = pd.concat([ago_k, ago_q])

        df_now = df_now[df_now['종가'] > 0]
        df_ago = df_ago[df_ago['종가'] > 0]

        df_ret = df_now.join(df_ago.rename(columns={'종가': '종가_ago'}), how='inner')
        df_ret['수익률'] = (df_ret['종가'] - df_ret['종가_ago']) / df_ret['종가_ago'] * 100

        # 시총·섹터 정보 (df_all 재사용)
        cap_sec = df_all[[cap_col, sector_col]].copy()
        cap_sec.index = cap_sec.index.astype(str).str.zfill(6)
        cap_sec[cap_col] = pd.to_numeric(cap_sec[cap_col], errors='coerce').fillna(0)

        df_ret.index = df_ret.index.astype(str).str.zfill(6)
        df_merged = df_ret.join(cap_sec, how='inner')
        df_merged = df_merged[df_merged[cap_col] > 0]

        def weighted_ret(g):
            total = g[cap_col].sum()
            return (g['수익률'] * g[cap_col]).sum() / total if total > 0 else 0.0

        sector_1m_returns = (
            df_merged.groupby(sector_col)
            .apply(weighted_ret, include_groups=False)
            .round(2)
            .to_dict()
        )
        print(f"  → {len(sector_1m_returns)}개 섹터 완료")
        for s, r in sorted(sector_1m_returns.items(), key=lambda x: -x[1])[:5]:
            print(f"    {s}: {r:+.2f}%")
    except Exception as e:
        print(f"  1M 수익률 계산 실패: {e}")

    return benchmark_sectors, stock_sector_map, sector_1m_returns


if __name__ == '__main__':
    print("=== KOSPI 200 + KOSDAQ 150 벤치마크 섹터 비중 계산 ===")
    sectors, stock_sector_map, sector_1m_returns = fetch_all()

    if sectors:
        result = {
            'updated': datetime.now().strftime('%Y-%m-%d'),
            'description': 'KOSPI 200 + KOSDAQ 150 기준',
            'sectors': sectors,
            'stock_sector_map': stock_sector_map or {},
            'sector_1m_returns': sector_1m_returns or {},
        }
        with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
        print(f"\n✅ 저장: {OUTPUT_FILE}")
    else:
        print("❌ 데이터 계산 실패 (kodex_sectors.json 유지)")
