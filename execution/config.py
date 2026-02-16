"""
Shared configuration for Antigravity Market Dashboard
Centralized definitions for categories, tickers, and target items
"""

# Category mapping for data types
CATEGORY_MAP = {
    'DRAM': 'Memory',
    'NAND': 'Memory',
    'CRYPTO': 'Cryptocurrency',
    'COMMODITY': 'Commodities',
    'FX': 'Exchange Rate',
    'INDEX_US': 'US Indices',
    'INTEREST_RATE': 'Interest Rates',
    'INDEX': 'US Indices',
    'OCEAN_FREIGHT': 'Commodities',
    'WRAP': 'Wrap',
    'INDEX_KR': 'Market Indices'
}

# Target DRAM items to scrape from DRAMeXchange
TARGET_DRAM_ITEMS = {
    'DDR5 16G (2Gx8) 4800/5600': 'DDR5 16G (2Gx8) 4800/5600',
    'DDR4 8Gb (512Mx16) 3200': 'DDR4 8Gb (512Mx16) 3200',
    'DDR4 8Gb (1Gx8) 3200': 'DDR4 8Gb (1Gx8) 3200',
    'DDR4 16Gb (1Gx16)3200': 'DDR4 16Gb (1Gx16)3200',
    'DDR4 16Gb (2Gx8)3200': 'DDR4 16Gb (2Gx8)3200'
}

# Target NAND items to scrape from DRAMeXchange
TARGET_NAND_ITEMS = {
    'SLC 2Gb 256MBx8': 'SLC 2Gb 256MBx8',
    'SLC 1Gb 128MBx8': 'SLC 1Gb 128MBx8',
    'MLC 64Gb 8GBx8': 'MLC 64Gb 8GBx8',
    'MLC 32Gb 4GBx8': 'MLC 32Gb 4GBx8'
}

# yfinance ticker definitions
YFINANCE_TICKERS = {
    # --- Cryptocurrencies ---
    'Bitcoin': {'ticker': 'BTC-USD', 'type': 'CRYPTO'},
    'Ethereum': {'ticker': 'ETH-USD', 'type': 'CRYPTO'},
    'Binance Coin': {'ticker': 'BNB-USD', 'type': 'CRYPTO'},
    'Ripple': {'ticker': 'XRP-USD', 'type': 'CRYPTO'},
    'Solana': {'ticker': 'SOL-USD', 'type': 'CRYPTO'},

    # --- Commodities ---
    'WTI Crude Oil': {'ticker': 'CL=F', 'type': 'COMMODITY'},
    'Brent Crude Oil': {'ticker': 'BZ=F', 'type': 'COMMODITY'},
    'Natural Gas': {'ticker': 'NG=F', 'type': 'COMMODITY'},
    'Gold': {'ticker': 'GC=F', 'type': 'COMMODITY'},
    'Silver': {'ticker': 'SI=F', 'type': 'COMMODITY'},
    'Copper': {'ticker': 'HG=F', 'type': 'COMMODITY'},
    'Sprott Physical Uranium Trust': {'ticker': 'SRUUF', 'type': 'COMMODITY'},
    'Wheat Futures': {'ticker': 'ZW=F', 'type': 'COMMODITY'},

    # --- Indices and Interest Rates ---
    'VIX Index': {'ticker': '^VIX', 'type': 'INDEX_US'},
    'US 13 Week Treasury Yield': {'ticker': '^IRX', 'type': 'INTEREST_RATE'},
    'US 5 Year Treasury Yield': {'ticker': '^FVX', 'type': 'INTEREST_RATE'},
    'US 10 Year Treasury Yield': {'ticker': '^TNX', 'type': 'INTEREST_RATE'},
    'US 30 Year Treasury Yield': {'ticker': '^TYX', 'type': 'INTEREST_RATE'},

    # --- Foreign Exchange ---
    'Dollar Index (DXY)': {'ticker': 'DX-Y.NYB', 'type': 'FX'},
    'KRW/USD': {'ticker': 'KRW=X', 'type': 'FX'},
    'JPY/USD': {'ticker': 'JPY=X', 'type': 'FX'},
    'CNY/USD': {'ticker': 'CNY=X', 'type': 'FX'},
    'TWD/USD': {'ticker': 'TWD=X', 'type': 'FX'},
    'EUR/USD': {'ticker': 'EUR=X', 'type': 'FX'},
}

# CSV file path
CSV_FILE = 'dataset.csv'
