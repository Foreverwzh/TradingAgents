"""alpaca_stock.get_stock: not-configured/rate-limit/no-data/success paths."""
import pandas as pd
import pytest
from unittest import mock

from tradingagents.dataflows import alpaca_stock
from tradingagents.dataflows.errors import NoMarketDataError, VendorNotConfiguredError, VendorRateLimitError


@pytest.mark.unit
def test_not_configured_without_keys(monkeypatch):
    monkeypatch.delenv("ALPACA_API_KEY", raising=False)
    monkeypatch.delenv("ALPACA_SECRET_KEY", raising=False)
    with pytest.raises(VendorNotConfiguredError):
        alpaca_stock.get_stock("AAPL", "2026-01-01", "2026-01-05")


def _bars_df(dates):
    idx = pd.MultiIndex.from_product([["AAPL"], pd.to_datetime(dates, utc=True)],
                                      names=["symbol", "timestamp"])
    return pd.DataFrame(
        {"open": [1.0] * len(dates), "high": [2.0] * len(dates), "low": [0.5] * len(dates),
         "close": [1.5] * len(dates), "volume": [100] * len(dates)},
        index=idx,
    )


@pytest.mark.unit
def test_success_returns_formatted_csv(monkeypatch):
    monkeypatch.setenv("ALPACA_API_KEY", "k")
    monkeypatch.setenv("ALPACA_SECRET_KEY", "s")

    class FakeBarsResult:
        df = _bars_df(["2026-01-02", "2026-01-05"])

    class FakeClient:
        def __init__(self, key, secret):
            pass

        def get_stock_bars(self, req):
            return FakeBarsResult()

    with mock.patch("alpaca.data.historical.stock.StockHistoricalDataClient", FakeClient):
        out = alpaca_stock.get_stock("AAPL", "2026-01-02", "2026-01-05")

    assert "source: Alpaca" in out
    assert "Total records: 2" in out
    assert "2026-01-02,1.0,2.0,0.5,1.5,100" in out
    assert "2026-01-05,1.0,2.0,0.5,1.5,100" in out


@pytest.mark.unit
def test_empty_result_raises_no_market_data(monkeypatch):
    monkeypatch.setenv("ALPACA_API_KEY", "k")
    monkeypatch.setenv("ALPACA_SECRET_KEY", "s")

    class FakeBarsResult:
        df = pd.DataFrame()

    class FakeClient:
        def __init__(self, key, secret):
            pass

        def get_stock_bars(self, req):
            return FakeBarsResult()

    with mock.patch("alpaca.data.historical.stock.StockHistoricalDataClient", FakeClient), \
            pytest.raises(NoMarketDataError):
        alpaca_stock.get_stock("300750.SZ", "2026-01-02", "2026-01-05")


@pytest.mark.unit
def test_api_error_rate_limit_maps_to_rate_limit_error(monkeypatch):
    from alpaca.common.exceptions import APIError

    monkeypatch.setenv("ALPACA_API_KEY", "k")
    monkeypatch.setenv("ALPACA_SECRET_KEY", "s")

    class FakeClient:
        def __init__(self, key, secret):
            pass

        def get_stock_bars(self, req):
            raise APIError("429 Too Many Requests: rate limit exceeded")

    with mock.patch("alpaca.data.historical.stock.StockHistoricalDataClient", FakeClient), \
            pytest.raises(VendorRateLimitError):
        alpaca_stock.get_stock("AAPL", "2026-01-02", "2026-01-05")


@pytest.mark.unit
def test_api_error_unknown_symbol_maps_to_no_market_data(monkeypatch):
    from alpaca.common.exceptions import APIError

    monkeypatch.setenv("ALPACA_API_KEY", "k")
    monkeypatch.setenv("ALPACA_SECRET_KEY", "s")

    class FakeClient:
        def __init__(self, key, secret):
            pass

        def get_stock_bars(self, req):
            raise APIError("404 symbol not found")

    with mock.patch("alpaca.data.historical.stock.StockHistoricalDataClient", FakeClient), \
            pytest.raises(NoMarketDataError):
        alpaca_stock.get_stock("300750.SZ", "2026-01-02", "2026-01-05")
