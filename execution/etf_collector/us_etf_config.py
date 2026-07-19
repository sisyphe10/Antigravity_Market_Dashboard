# -*- coding: utf-8 -*-
"""미국(+홍콩) ETF NAV·AUM 수집 대상 정의 — 단일 출처.

- kr: 한국 노출 여부 (대시보드 O/X 표기 · 하이라이트 집계 대상)
- kr_weight: 한국 실투자 비중.
    'idx'  = (삼전+하이닉스 보유비중) / KR_SH_RATIO 로 국가비중 자동 추정
    'auto' = 삼성전자+SK하이닉스 보유비중 합 그대로 (메모리 ETF — 한국 보유가 두 종목뿐)
    'lev2' = 2x 스왑 노출 (AUM×2)
    float  = 고정 (한국 단일국가 = 1.0)
- 홍콩 2종(.HK)은 yfinance NAV 미갱신 → 가격(HKD)·AUM(USD)만 수집.

정적 국가 비중 갱신 이력: 2026-07-19 최초 설정 (MSCI/FTSE factsheet 기준 추정).
"""

US_ETFS = [
    # ticker, name, group(구분), kr, kr_weight
    {'ticker': 'VXUS',    'name': 'Vanguard Total Intl Stock (FTSE)',      'group': '글로벌',      'kr': True,  'kr_weight': 'idx'},
    {'ticker': 'VEA',     'name': 'Vanguard FTSE Developed',               'group': '선진',        'kr': True,  'kr_weight': 'idx'},
    {'ticker': 'VWO',     'name': 'Vanguard FTSE EM',                      'group': '신흥국',      'kr': False, 'kr_weight': 0.0},
    {'ticker': 'IEMG',    'name': 'iShares Core MSCI EM',                  'group': '신흥국',      'kr': True,  'kr_weight': 'idx'},
    {'ticker': 'VT',      'name': 'Vanguard Total World (FTSE)',           'group': '글로벌',      'kr': True,  'kr_weight': 'idx'},
    {'ticker': 'EFA',     'name': 'iShares MSCI EAFE',                     'group': '선진',        'kr': False, 'kr_weight': 0.0},
    {'ticker': 'SMH',     'name': 'VanEck Semiconductor',                  'group': '반도체',      'kr': False, 'kr_weight': 0.0},
    {'ticker': 'IXUS',    'name': 'iShares Core MSCI Total Intl',          'group': '글로벌',      'kr': True,  'kr_weight': 'idx'},
    {'ticker': 'SOXX',    'name': 'iShares Semiconductor',                 'group': '반도체',      'kr': False, 'kr_weight': 0.0},
    {'ticker': 'SPDW',    'name': 'SPDR Developed World ex-US (S&P)',      'group': '선진',        'kr': True,  'kr_weight': 'idx'},
    {'ticker': 'ACWI',    'name': 'iShares MSCI ACWI',                     'group': '글로벌',      'kr': True,  'kr_weight': 'idx'},
    {'ticker': 'SOXL',    'name': 'Direxion Semiconductor Bull 3x',        'group': '반도체 3x',   'kr': False, 'kr_weight': 0.0},
    {'ticker': 'EEM',     'name': 'iShares MSCI EM',                       'group': '신흥국',      'kr': True,  'kr_weight': 'idx'},
    {'ticker': 'EMXC',    'name': 'iShares MSCI EM ex-China',              'group': '신흥국',      'kr': True,  'kr_weight': 'idx'},
    {'ticker': 'DRAM',    'name': 'Roundhill Memory ETF',                  'group': '메모리',      'kr': True,  'kr_weight': 'auto'},
    {'ticker': 'EWY',     'name': 'iShares MSCI South Korea',              'group': '한국',        'kr': True,  'kr_weight': 1.0},
    {'ticker': 'SPEM',    'name': 'SPDR Portfolio EM (S&P)',               'group': '신흥국',      'kr': False, 'kr_weight': 0.0},
    {'ticker': '7709.HK', 'name': 'CSOP SK Hynix Daily 2x',                'group': '하이닉스 2x', 'kr': True,  'kr_weight': 'lev2'},
    {'ticker': 'AAXJ',    'name': 'iShares Asia ex-Japan',                 'group': '아시아',      'kr': True,  'kr_weight': 'idx'},
    {'ticker': '7747.HK', 'name': 'CSOP Samsung Electronics Daily 2x',     'group': '삼성전자 2x', 'kr': True,  'kr_weight': 'lev2'},
    {'ticker': 'XSD',     'name': 'SPDR S&P Semiconductor (동일가중)',     'group': '반도체',      'kr': False, 'kr_weight': 0.0},
    {'ticker': 'USD',     'name': 'ProShares Ultra Semiconductors 2x',     'group': '반도체 2x',   'kr': False, 'kr_weight': 0.0},
    {'ticker': 'PSI',     'name': 'Invesco Semiconductors',                'group': '반도체',      'kr': False, 'kr_weight': 0.0},
    {'ticker': 'SOXQ',    'name': 'Invesco PHLX Semiconductor (SOX)',      'group': '반도체',      'kr': False, 'kr_weight': 0.0},
    {'ticker': 'FTXL',    'name': 'First Trust Nasdaq Semiconductor',      'group': '반도체',      'kr': False, 'kr_weight': 0.0},
    {'ticker': 'FLKR',    'name': 'Franklin FTSE South Korea',             'group': '한국',        'kr': True,  'kr_weight': 1.0},
    {'ticker': 'SOXS',    'name': 'Direxion Semiconductor Bear 3x',        'group': '반도체 -3x',  'kr': False, 'kr_weight': 0.0},
    {'ticker': 'RAM',     'name': 'T-REX 2x Long DRAM Daily',              'group': '메모리 2x',   'kr': True,  'kr_weight': 'auto'},
]

# 삼성전자(005930/005935 우선주 포함)·SK하이닉스(000660) 보유비중 폴백.
# top holdings(상위 10)에서 안 잡히는 글로벌 대형 펀드용 추정치 (분기 1회 갱신, 2026-07-19 설정).
# top holdings 에서 실측되면 실측값이 우선한다.
FALLBACK_WEIGHTS = {
    # ticker: (w_samsung, w_hynix)
    'VXUS': (0.008, 0.008),
    'VEA':  (0.011, 0.012),
    'VT':   (0.004, 0.004),
    'IXUS': (0.008, 0.008),
    'SPDW': (0.010, 0.011),
    'ACWI': (0.007, 0.007),
    'AAXJ': (0.090, 0.075),
    'FLKR': (0.210, 0.240),
}

# 홍콩 2x 단일종목 — 스왑 노출 (삼전/하이닉스 비중 = 2.0 고정)
HK_SINGLE = {'7747.HK': 'samsung', '7709.HK': 'hynix'}

# 한국 시총에서 삼성전자+SK하이닉스가 차지하는 비율 추정 (idx 국가비중 역산용, 분기 1회 점검)
KR_SH_RATIO = 0.60

HISTORY_CSV = 'us_etf_history.csv'
