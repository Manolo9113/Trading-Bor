"""Tests fuer RsiMacdStrategy."""

import numpy as np
import pandas as pd

from src.strategies.rsi_macd_strategy import RsiMacdStrategy
from src.strategies.base_strategy import SignalType


CONFIG = {
    "rsi_macd": {
        "rsi_period": 14,
        "rsi_oversold": 30,
        "rsi_overbought": 70,
        "macd_fast": 12,
        "macd_slow": 26,
        "macd_signal": 9,
        "atr_period": 14,
    },
    "risk": {
        "stop_loss_atr_mult": 2.0,
        "take_profit_ratio": 2.0,
        "risk_per_trade": 0.02,
    },
}


def _make_df(n: int = 150) -> pd.DataFrame:
    np.random.seed(99)
    close = 100 + np.random.randn(n).cumsum()
    return pd.DataFrame({
        "open":   close - np.abs(np.random.randn(n) * 0.5),
        "high":   close + np.abs(np.random.randn(n) * 1.0),
        "low":    close - np.abs(np.random.randn(n) * 1.0),
        "close":  close,
        "volume": np.abs(np.random.randn(n) * 1000 + 5000),
    })


class TestRsiMacdStrategy:
    def setup_method(self):
        self.strategy = RsiMacdStrategy(CONFIG)

    def test_returns_none_on_small_df(self):
        df = _make_df(10)
        assert self.strategy.generate_signal(df) is None

    def test_signal_or_none_on_normal_df(self):
        df = _make_df(150)
        result = self.strategy.generate_signal(df)
        assert result is None or result.signal_type in (SignalType.BUY, SignalType.SELL)

    def test_signal_has_valid_sl_tp(self):
        df = _make_df(150)
        sig = self.strategy.generate_signal(df)
        if sig:
            assert sig.stop_loss != sig.price
            assert sig.take_profit != sig.price
            if sig.signal_type == SignalType.BUY:
                assert sig.stop_loss < sig.price
                assert sig.take_profit > sig.price
            else:
                assert sig.stop_loss > sig.price
                assert sig.take_profit < sig.price

    def test_signal_size_in_range(self):
        df = _make_df(150)
        sig = self.strategy.generate_signal(df)
        if sig:
            assert 0.0 < sig.size <= 0.1

    def test_risk_reward_positive(self):
        df = _make_df(150)
        sig = self.strategy.generate_signal(df)
        if sig:
            assert sig.risk_reward > 0
