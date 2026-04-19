"""Tests fuer technische Indikatoren."""

import numpy as np
import pandas as pd

from src.indicators.technical import rsi, macd, atr, bollinger_bands, ema, sma, stochastic


def _close(n: int = 100) -> pd.Series:
    np.random.seed(7)
    return pd.Series(100 + np.random.randn(n).cumsum())


def _ohlcv(n: int = 100) -> pd.DataFrame:
    np.random.seed(7)
    close = 100 + np.random.randn(n).cumsum()
    return pd.DataFrame({
        "open":   close - np.abs(np.random.randn(n) * 0.5),
        "high":   close + np.abs(np.random.randn(n) * 1.0),
        "low":    close - np.abs(np.random.randn(n) * 1.0),
        "close":  close,
        "volume": np.abs(np.random.randn(n) * 1000 + 5000),
    })


class TestRsi:
    def test_range(self):
        vals = rsi(_close(), 14).dropna()
        assert (vals >= 0).all() and (vals <= 100).all()

    def test_length(self):
        s = _close(50)
        result = rsi(s, 14)
        assert len(result) == 50


class TestMacd:
    def test_returns_three_series(self):
        m, sig, hist = macd(_close())
        assert len(m) == len(sig) == len(hist) == 100

    def test_histogram_is_diff(self):
        m, sig, hist = macd(_close())
        diff = (m - sig - hist).dropna()
        assert (diff.abs() < 1e-10).all()


class TestAtr:
    def test_positive(self):
        result = atr(_ohlcv(), 14).dropna()
        assert (result > 0).all()

    def test_length(self):
        result = atr(_ohlcv(50), 14)
        assert len(result) == 50


class TestBollingerBands:
    def test_upper_above_lower(self):
        upper, mid, lower = bollinger_bands(_close())
        valid = upper.dropna()
        low_v = lower.dropna()
        assert (valid.values > low_v.values).all()

    def test_middle_is_sma(self):
        s = _close()
        _, mid, _ = bollinger_bands(s, 20)
        expected = s.rolling(20).mean()
        diff = (mid - expected).dropna().abs()
        assert (diff < 1e-10).all()


class TestEmaAndSma:
    def test_ema_length(self):
        assert len(ema(_close(), 20)) == 100

    def test_sma_first_nan(self):
        result = sma(_close(50), 10)
        assert result.iloc[:9].isna().all()
        assert not pd.isna(result.iloc[9])


class TestStochastic:
    def test_k_range(self):
        k, d = stochastic(_ohlcv())
        valid_k = k.dropna()
        assert (valid_k >= 0).all() and (valid_k <= 100).all()
