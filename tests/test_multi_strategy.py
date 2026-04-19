"""Tests fuer MultiStrategy und PaperTrader."""

import numpy as np
import pandas as pd

from src.strategies.base_strategy import BaseStrategy, Signal, SignalType
from src.strategies.multi_strategy import MultiStrategy
from src.strategies.paper_trader import PaperTrader


def _make_df(n: int = 150) -> pd.DataFrame:
    np.random.seed(42)
    close = 100 + np.random.randn(n).cumsum()
    dates = pd.date_range("2023-01-01", periods=n, freq="1h")
    return pd.DataFrame({
        "open":   close - 0.2,
        "high":   close + 0.5,
        "low":    close - 0.5,
        "close":  close,
        "volume": abs(np.random.randn(n) * 100 + 1000),
    }, index=dates)


class FixedBuyStrategy(BaseStrategy):
    def generate_signal(self, df) -> Signal:
        p = float(df["close"].iloc[-1])
        return Signal(SignalType.BUY, p, p * 0.95, p * 1.10, 0.05, 0.8, "fixed buy")


class FixedSellStrategy(BaseStrategy):
    def generate_signal(self, df) -> Signal:
        p = float(df["close"].iloc[-1])
        return Signal(SignalType.SELL, p, p * 1.05, p * 0.90, 0.05, 0.8, "fixed sell")


class NoneStrategy(BaseStrategy):
    def generate_signal(self, df) -> None:
        return None


class TestMultiStrategy:
    def test_no_signal_when_no_consensus(self):
        ms = MultiStrategy([FixedBuyStrategy({}), FixedSellStrategy({})], {}, min_votes=2)
        df = _make_df()
        assert ms.generate_signal(df) is None

    def test_buy_signal_with_consensus(self):
        ms = MultiStrategy([FixedBuyStrategy({}), FixedBuyStrategy({})], {}, min_votes=2)
        df = _make_df()
        sig = ms.generate_signal(df)
        assert sig is not None
        assert sig.signal_type == SignalType.BUY

    def test_sell_signal_with_consensus(self):
        ms = MultiStrategy([FixedSellStrategy({}), FixedSellStrategy({})], {}, min_votes=2)
        df = _make_df()
        sig = ms.generate_signal(df)
        assert sig is not None
        assert sig.signal_type == SignalType.SELL

    def test_min_votes_1_buys_with_single_strategy(self):
        ms = MultiStrategy([FixedBuyStrategy({}), NoneStrategy({})], {}, min_votes=1)
        df = _make_df()
        sig = ms.generate_signal(df)
        assert sig is not None
        assert sig.signal_type == SignalType.BUY

    def test_merged_signal_averages_price(self):
        ms = MultiStrategy([FixedBuyStrategy({}), FixedBuyStrategy({})], {}, min_votes=2)
        df = _make_df()
        sig = ms.generate_signal(df)
        price = float(df["close"].iloc[-1])
        assert abs(sig.price - price) < 1e-6

    def test_confidence_in_range(self):
        ms = MultiStrategy([FixedBuyStrategy({}), FixedBuyStrategy({})], {}, min_votes=2)
        sig = ms.generate_signal(_make_df())
        if sig:
            assert 0.0 <= sig.confidence <= 1.0

    def test_none_strategies_dont_crash(self):
        ms = MultiStrategy([NoneStrategy({}), NoneStrategy({})], {}, min_votes=1)
        assert ms.generate_signal(_make_df()) is None


class TestPaperTrader:
    def test_stats_initial_capital(self):
        pt = PaperTrader(NoneStrategy({}), initial_capital=5_000, log_file="/tmp/test_paper.csv")
        stats = pt.stats()
        assert stats["capital"] == 5_000
        assert stats["total_return"] == 0.0
        assert stats["total_trades"] == 0

    def test_tick_returns_signal_on_entry(self):
        pt = PaperTrader(FixedBuyStrategy({}), initial_capital=10_000, log_file="/tmp/test_paper2.csv")
        df = _make_df()
        sig = pt.tick(df)
        assert sig is not None
        assert sig.signal_type == SignalType.BUY

    def test_tick_no_double_entry(self):
        pt = PaperTrader(FixedBuyStrategy({}), initial_capital=10_000, log_file="/tmp/test_paper3.csv")
        df = _make_df()
        pt.tick(df)
        sig2 = pt.tick(df)
        assert sig2 is None  # Bereits offen

    def test_open_position_flag(self):
        pt = PaperTrader(FixedBuyStrategy({}), initial_capital=10_000, log_file="/tmp/test_paper4.csv")
        pt.tick(_make_df())
        assert pt.stats()["open_position"] is True

    def test_no_signal_with_none_strategy(self):
        pt = PaperTrader(NoneStrategy({}), initial_capital=10_000, log_file="/tmp/test_paper5.csv")
        sig = pt.tick(_make_df())
        assert sig is None
        assert pt.stats()["total_trades"] == 0
