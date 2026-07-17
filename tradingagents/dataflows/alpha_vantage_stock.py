from datetime import datetime

from .alpha_vantage_common import _filter_csv_by_date_range, _make_api_request


def get_stock(
    symbol: str,
    start_date: str,
    end_date: str
) -> str:
    """
    Returns raw daily OHLCV values filtered to the specified date range.

    Uses TIME_SERIES_DAILY (unadjusted), not TIME_SERIES_DAILY_ADJUSTED: Alpha
    Vantage moved the adjusted endpoint behind a paid plan, so on a free key
    it deterministically fails with a "premium endpoint" error every single
    call -- not a transient rate limit, a permanent wall regardless of quota.
    That made this vendor's get_stock_data fallback pure dead weight (it
    still burned a request against the free tier's 25/day budget before
    failing). Unadjusted prices are a real, if imperfect, fallback -- no
    split/dividend adjustment -- which beats no data at all when yfinance is
    the one that's rate-limited.

    Args:
        symbol: The name of the equity. For example: symbol=IBM
        start_date: Start date in yyyy-mm-dd format
        end_date: End date in yyyy-mm-dd format

    Returns:
        CSV string containing the daily time series data filtered to the date range.
    """
    # Parse dates to determine the range
    start_dt = datetime.strptime(start_date, "%Y-%m-%d")
    today = datetime.now()

    # Choose outputsize based on whether the requested range is within the latest 100 days
    # Compact returns latest 100 data points, so check if start_date is recent enough
    days_from_today_to_start = (today - start_dt).days
    outputsize = "compact" if days_from_today_to_start < 100 else "full"

    params = {
        "symbol": symbol,
        "outputsize": outputsize,
        "datatype": "csv",
    }

    response = _make_api_request("TIME_SERIES_DAILY", params)

    return _filter_csv_by_date_range(response, start_date, end_date)
