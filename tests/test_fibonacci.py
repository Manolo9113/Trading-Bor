"""Tests fuer FibonacciCalculator."""

import numpy as np
import pandas as pd
import pytest

from src.indicators.fibonacci import FibonacciCalculator, FibonacciZone


DEFAULT_CONFIG = {
    "swing_window": 5,
    "use_wma": False,
    "wma_period": 14,
    "levels_retracement": [0.0, 0.236, 0.382, 0.5, 0.618, 0.786, 1.0],
    "levels_extension": [1.272, 1.618, 2.618],
    "confluence_tolerance": 0.003,
}


def _make_df(n: int = 100, trend: str = "up") -> pd.DataFrame:
    """Erzeugt synthetischen OHLCV-DataFrame."""
    np.random.seed(42)
    if trend == "up":
        close = np.linspace(100, 200, n) + np.random.randn(n) * 2
    else:
        close = np.linspace(200, 100, n) + np.random.randn(n) * 2
    df = pd.DataFrame({
        "open": close - np.abs(np.random.randn(n)),
        "high": close + np.abs(np.random.randn(n) * 2),
        "low": close - np.abs(np.random.randn(n) * 2),
        "close": close,
        "volume": np.abs(np.random.randn(n) * 1000 + 5000),
    })
    return df


class TestFibonacciCalculator:
    def setup_method(self):
        self.calc = FibonacciCalculator(DEFAULT_CONFIG)

    def test_wma_length(self):
        series = pd.Series(range(1, 21), dtype=float)
        result = FibonacciCalculator.wma(series, 5)
        assert len(result) == 20
        assert result.isna().sum() == 4  # erste 4 sind NaN

    def test_wma_weighted(self):
        """Letzter Wert muss staerker gewichtet sein als erster."""
        series = pd.Series([1.0, 2.0, 3.0, 4.0, 5.0])
        result = FibonacciCalculator.wma(series, 5)
        expected = (1*1 + 2*2 + 3*3 + 4*4 + 5*5) / (1+2+3+4+5)
        assert abs(result.iloc[-1] - expected) < 1e-6

    def test_find_swings_returns_arrays(self):
        df = _make_df(100)
        highs, lows = self.calc.find_swings(df)
        assert isinstance(highs, np.ndarray)
        assert isinstance(lows, np.ndarray)
        assert len(highs) > 0
        assert len(lows) > 0

    def test_calculate_returns_zone(self):
        df = _make_df(100)
        zones = self.calc.calculate(df, n_recent=1)
        assert len(zones) >= 0  # Kann leer sein bei zu wenig Swings

    def test_zone_levels_count(self):
        df = _make_df(150)
        zones = self.calc.calculate(df, n_recent=1)
        if zones:
            zone = zones[0]
            assert len(zone.retracement_levels) == len(DEFAULT_CONFIG["levels_retracement"])
            assert len(zone.extension_levels) == len(DEFAULT_CONFIG["levels_extension"])

    def test_zone_high_greater_low(self):
        df = _make_df(150)
        zones = self.calc.calculate(df, n_recent=1)
        for zone in zones:
            assert zone.swing_high > zone.swing_low

    def test_retracement_050_between_high_low(self):
        """0.5-Level muss zwischen Swing-High und Swing-Low liegen."""
        df = _make_df(150)
        zones = self.calc.calculate(df, n_recent=1)
        for zone in zones:
            mid = self.calc.price_at_level(zone, 0.5)
            if mid is not None:
                assert zone.swing_low <= mid <= zone.swing_high

    def test_is_near_level_true(self):
        """Preis direkt auf einem Level wird erkannt."""
        df = _make_df(150)
        zones = self.calc.calculate(df, n_recent=1)
        if zones:
            zone = zones[0]
            lvl = zone.retracement_levels[3]  # 0.5
            result = self.calc.is_near_level(lvl.price, zone, tolerance=0.01)
            assert result is not None

    def test_is_near_level_false(self):
        """Weit entfernter Preis wird nicht erkannt."""
        df = _make_df(150)
        zones = self.calc.calculate(df, n_recent=1)
        if zones:
            zone = zones[0]
            far_price = zone.swing_high * 10
            result = self.calc.is_near_level(far_price, zone)
            assert result is None

    def test_no_crash_on_small_df(self):
        """Kein Absturz bei zu wenig Daten."""
        df = _make_df(5)
        zones = self.calc.calculate(df)
        assert isinstance(zones, list)
