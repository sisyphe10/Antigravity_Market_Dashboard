
"""
Check if we can get historical PER/PBR data from yfinance.

Unfortunately, yfinance only provides current fundamental data (PER, PBR) 
through the .info property, which doesn't include historical values.

The .history() method only provides OHLCV (Open, High, Low, Close, Volume) data,
not fundamental metrics.

Alternative approaches:
1. Calculate PER manually: PER = Price / EPS
   - We can get historical prices from .history()
   - But we need historical EPS data, which yfinance doesn't provide in time series

2. Use premium data providers (not free):
   - Alpha Vantage
   - Financial Modeling Prep
   - Quandl

3. Accept limitation: Only collect current PER/PBR values going forward

For this project, we'll use approach #3 - collect current values daily,
which will build up historical data over time.
"""

import yfinance as yf

# Test what data is available
ticker = yf.Ticker("SPY")

print("=" * 60)
print("Testing yfinance data availability for SPY")
print("=" * 60)

# Check .info (current fundamentals)
print("\n1. Current fundamentals from .info:")
info = ticker.info
print(f"  Trailing PE: {info.get('trailingPE', 'N/A')}")
print(f"  Price to Book: {info.get('priceToBook', 'N/A')}")

# Check .history (historical OHLCV)
print("\n2. Historical data from .history():")
hist = ticker.history(period="5d")
print(f"  Available columns: {list(hist.columns)}")
print(f"  Sample data:\n{hist.head()}")

# Check if there's any fundamental data in history
print("\n3. Checking for fundamental data in history:")
print(f"  No PER/PBR columns available in historical data")

print("\n" + "=" * 60)
print("CONCLUSION: Historical PER/PBR not available from yfinance")
print("We can only collect current values daily to build history")
print("=" * 60)
