"""Tests fuer PatternDetector."""

import numpy as np
import pandas as pd

from src.indicators.patterns import PatternDetector


DEFAULT_CONFIG = {
    "enabled": [
        "engulfing", "hammer", "shooting_star", "doji",
        "double_top", "double_bottom",
        "head_and_shoulders", "inverse_head_and_shoulders",
    ],
    "swing_order": 3,
    "tolerance": 0.02,
}


def _base_df(n: int = 50) -> pd.DataFrame:
    np.random.seed(0)
    close = 100 + np.random.randn(n).cumsum()
    return pd.DataFrame({
        "open": close - np.abs(np.random.randn(n) * 0.5),
        "high": close + np.abs(np.random.randn(n) * 1.0),
        "low": close - np.abs(np.random.randn(n) * 1.0),
        "close": close,
        "volume": np.abs(np.random.randn(n) * 1000 + 5000),
    })


class TestPatternDetector:
    def setup_method(self):
        self.det = PatternDetector(DEFAULT_CONFIG)

    def test_detect_returns_list(self):
        df = _base_df(50)
        signals = self.det.detect(df)
        assert isinstance(signals, list)

    def test_signal_direction_valid(self):
        df = _base_df(50)
        for sig in self.det.detect(df):
            assert sig.direction in ("bullish", "bearish", "neutral")

    def test_signal_strength_range(self):
        df = _base_df(50)
        for sig in self.det.detect(df):
            assert 0.0 <= sig.strength <= 1.0

    def test_bullish_engulfing(self):
        """Konstruiere explizites Bullish-Engulfing-Muster."""
        df = _base_df(10)
        # Letzte Kerze: grosse gruene Kerze
        df.iloc[-2, df.columns.get_loc("open")] = 105.0
        df.iloc[-2, df.columns.get_loc("close")] = 100.0  # rote Kerze
        df.iloc[-1, df.columns.get_loc("open")] = 99.0
        df.iloc[-1, df.columns.get_loc("close")] = 107.0  # grosse gruene Kerze
        df.iloc[-1, df.columns.get_loc("high")] = 108.0
        df.iloc[-1, df.columns.get_loc("low")] = 98.5
        det = PatternDetector({"enabled": ["engulfing"], "swing_order": 3})
        sig = det._detect_engulfing(df)
        assert sig is not None
        assert sig.direction == "bullish"

    def test_bearish_engulfing(self):
        df = _base_df(10)
        df.iloc[-2, df.columns.get_loc("open")] = 100.0
        df.iloc[-2, df.columns.get_loc("close")] = 105.0  # gruene Kerze
        df.iloc[-1, df.columns.get_loc("open")] = 106.0
        df.iloc[-1, df.columns.get_loc("close")] = 98.0   # grosse rote Kerze
        df.iloc[-1, df.columns.get_loc("high")] = 107.0
        df.iloc[-1, df.columns.get_loc("low")] = 97.5
        det = PatternDetector({"enabled": ["engulfing"], "swing_order": 3})
        sig = det._detect_engulfing(df)
        assert sig is not None
        assert sig.direction == "bearish"

    def test_hammer_pattern(self):
        df = _base_df(10)
        # Hammer: langer unterer Docht
        df.iloc[-1, df.columns.get_loc("open")] = 100.0
        df.iloc[-1, df.columns.get_loc("close")] = 101.0
        df.iloc[-1, df.columns.get_loc("high")] = 101.5
        df.iloc[-1, df.columns.get_loc("low")] = 95.0   # langer unterer Docht
        det = PatternDetector({"enabled": ["hammer"], "swing_order": 3})
        sig = det._detect_hammer(df)
        assert sig is not None
        assert sig.direction == "bullish"

    def test_shooting_star_pattern(self):
        df = _base_df(10)
        df.iloc[-1, df.columns.get_loc("open")] = 100.0
        df.iloc[-1, df.columns.get_loc("close")] = 101.0
        df.iloc[-1, df.columns.get_loc("high")] = 107.0  # langer oberer Docht
        df.iloc[-1, df.columns.get_loc("low")] = 99.8
        det = PatternDetector({"enabled": ["shooting_star"], "swing_order": 3})
        sig = det._detect_shooting_star(df)
        assert sig is not None
        assert sig.direction == "bearish"

    def test_doji_pattern(self):
        df = _base_df(10)
        df.iloc[-1, df.columns.get_loc("open")] = 100.0
        df.iloc[-1, df.columns.get_loc("close")] = 100.05  # fast identisch
        df.iloc[-1, df.columns.get_loc("high")] = 101.0
        df.iloc[-1, df.columns.get_loc("low")] = 99.0
        det = PatternDetector({"enabled": ["doji"], "swing_order": 3})
        sig = det._detect_doji(df)
        assert sig is not None
        assert sig.direction == "neutral"

    def test_no_crash_small_df(self):
        df = _base_df(3)
        signals = self.det.detect(df)
        assert isinstance(signals, list)

    def test_disabled_patterns_not_detected(self):
        det = PatternDetector({"enabled": [], "swing_order": 3})
        df = _base_df(50)
        signals = det.detect(df)
        assert signals == []
