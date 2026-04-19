"""Tests fuer Backtester."""

import numpy as np
import pandas as pd

from src.backtest.backtester import Backtester, BacktestResult
from src.strategies.base_strategy import BaseStrategy, Signal, SignalType
from typing import Optional


class AlwaysBuyStrategy(BaseStrategy):
    """Kauft immer auf der ersten Kerze."""
    _bought = False

    def generate_signal(self, df: pd.DataFrame) -> Optional[Signal]:
        if self._bought:
            return None
        price = float(df["close"].iloc[-1])
        self._bought = True
        return Signal(
            signal_type=SignalType.BUY,
            price=price,
            stop_loss=price * 0.95,
            take_profit=price * 1.10,
            size=0.05,
            confidence=1.0,
            reason="Always Buy Test",
        )


class NeverSignalStrategy(BaseStrategy):
    def generate_signal(self, df):
        return None


def _make_df(n: int = 300, trend: str = "up") -> pd.DataFrame:
    np.random.seed(1)
    if trend == "up":
        close = np.linspace(100, 150, n) + np.random.randn(n) * 0.5
    else:
        close = np.linspace(150, 100, n) + np.random.randn(n) * 0.5
    dates = pd.date_range("2023-01-01", periods=n, freq="1h")
    return pd.DataFrame({
        "open":   close - 0.2,
        "high":   close + 0.5,
        "low":    close - 0.5,
        "close":  close,
        "volume": np.abs(np.random.randn(n) * 100 + 1000),
    }, index=dates)


class TestBacktester:
    def test_no_signals_returns_zero_trades(self):
        bt = Backtester(NeverSignalStrategy({}), initial_capital=10_000)
        result = bt.run(_make_df())
        assert result.total_trades == 0

    def test_equity_curve_starts_with_initial_capital(self):
        bt = Backtester(NeverSignalStrategy({}), initial_capital=10_000)
        result = bt.run(_make_df())
        assert result.equity_curve[0] == 10_000

    def test_returns_backtest_result_type(self):
        bt = Backtester(AlwaysBuyStrategy({}), initial_capital=10_000)
        result = bt.run(_make_df())
        assert isinstance(result, BacktestResult)

    def test_win_rate_in_range(self):
        bt = Backtester(AlwaysBuyStrategy({}), initial_capital=10_000)
        result = bt.run(_make_df())
        assert 0.0 <= result.win_rate <= 1.0

    def test_max_drawdown_negative_or_zero(self):
        bt = Backtester(AlwaysBuyStrategy({}), initial_capital=10_000)
        result = bt.run(_make_df())
        assert result.max_drawdown <= 0.0

    def test_profit_factor_positive(self):
        bt = Backtester(AlwaysBuyStrategy({}), initial_capital=10_000)
        result = bt.run(_make_df())
        if result.total_trades > 0:
            assert result.profit_factor >= 0

    def test_commission_reduces_capital(self):
        bt_no_comm  = Backtester(AlwaysBuyStrategy({}), initial_capital=10_000, commission=0.0)
        bt_with_comm = Backtester(AlwaysBuyStrategy({}), initial_capital=10_000, commission=0.01)
        df = _make_df()
        r1 = bt_no_comm.run(df)
        AlwaysBuyStrategy._bought = False
        r2 = bt_with_comm.run(df)
        assert r1.equity_curve[-1] >= r2.equity_curve[-1]
