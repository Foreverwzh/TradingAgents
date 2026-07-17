"""Daily OHLCV via Alpaca -- the same ALPACA_API_KEY/ALPACA_SECRET_KEY this
monorepo already uses for live trading/VWAP data (see quant-above-all's
ib_example/kline_fetch.py), with a far more generous free-tier rate limit
than yfinance (frequently 429s) or Alpha Vantage (25 requests/day). US-listed
equities only -- non-US symbols (A-share/HK/forex/futures) come back as
NoMarketDataError so the router falls through to a vendor that covers them.
"""

import os
from datetime import datetime, timedelta

import pandas as pd

from .errors import NoMarketDataError, VendorNotConfiguredError, VendorRateLimitError


class AlpacaNotConfiguredError(VendorNotConfiguredError):
    """Raised when Alpaca is selected but no API key/secret is configured."""


class AlpacaRateLimitError(VendorRateLimitError):
    """Raised when the Alpaca API rate limit is exceeded."""


def _get_client():
    key = os.getenv("ALPACA_API_KEY")
    secret = os.getenv("ALPACA_SECRET_KEY")
    if not key or not secret:
        raise AlpacaNotConfiguredError(
            "ALPACA_API_KEY/ALPACA_SECRET_KEY environment variables are not set."
        )
    from alpaca.data.historical.stock import StockHistoricalDataClient

    return StockHistoricalDataClient(key, secret)


def _fetch_bars_df(symbol: str, start_date: str, end_date: str) -> pd.DataFrame:
    """Raw Alpaca daily bars as a DataFrame with Date/Open/High/Low/Close/Volume
    columns (Date is tz-naive, not yet stringified). Shared by ``get_stock``
    (the LLM-facing CSV tool) and ``stockstats_utils.load_ohlcv``'s
    cross-vendor fallback -- callers needing a DataFrame use this directly
    instead of parsing ``get_stock``'s formatted text back out.
    """
    from alpaca.common.exceptions import APIError
    from alpaca.data.enums import Adjustment, DataFeed
    from alpaca.data.requests import StockBarsRequest
    from alpaca.data.timeframe import TimeFrame

    client = _get_client()
    start_dt = datetime.strptime(start_date, "%Y-%m-%d")
    # Alpaca's ``end`` is inclusive already, but bars for "today" may not have
    # settled yet -- request one extra day like the yfinance path does so a
    # same-day request isn't silently short a row (#986/#987 precedent).
    end_dt = datetime.strptime(end_date, "%Y-%m-%d") + timedelta(days=1)

    req = StockBarsRequest(
        symbol_or_symbols=symbol, timeframe=TimeFrame.Day,
        start=start_dt, end=end_dt, feed=DataFeed.SIP, adjustment=Adjustment.RAW,
    )
    try:
        raw = client.get_stock_bars(req).df
    except APIError as e:
        msg = str(e).lower()
        if "429" in msg or "rate limit" in msg or "too many requests" in msg:
            raise AlpacaRateLimitError(f"Alpaca rate limit exceeded: {e}") from e
        # Alpaca doesn't cover non-US symbols (A-share/HK/forex/futures) --
        # those come back as a 404/"not found" APIError, which reads as "no
        # data from this vendor" rather than a hard failure.
        raise NoMarketDataError(symbol, symbol, f"Alpaca: {e}") from e

    if raw is None or raw.empty:
        raise NoMarketDataError(symbol, symbol, "no rows from Alpaca")

    df = raw.reset_index()
    df = df.rename(columns={
        "timestamp": "Date", "open": "Open", "high": "High",
        "low": "Low", "close": "Close", "volume": "Volume",
    })
    df["Date"] = pd.to_datetime(df["Date"]).dt.tz_localize(None)
    keep = [c for c in ("Date", "Open", "High", "Low", "Close", "Volume") if c in df.columns]
    return df[keep]


def get_stock(symbol: str, start_date: str, end_date: str) -> str:
    """Returns raw daily OHLCV values filtered to the specified date range.

    Args:
        symbol: The name of the equity. For example: symbol=IBM
        start_date: Start date in yyyy-mm-dd format
        end_date: End date in yyyy-mm-dd format

    Returns:
        CSV string containing the daily time series data.
    """
    df = _fetch_bars_df(symbol, start_date, end_date)
    for col in ("Open", "High", "Low", "Close"):
        if col in df.columns:
            df[col] = df[col].round(2)
    df = df.assign(Date=df["Date"].dt.strftime("%Y-%m-%d"))

    csv_string = df.to_csv(index=False)
    header = f"# Stock data for {symbol.upper()} from {start_date} to {end_date} (source: Alpaca)\n"
    header += f"# Total records: {len(df)}\n"
    header += f"# Data retrieved on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"

    return header + csv_string
