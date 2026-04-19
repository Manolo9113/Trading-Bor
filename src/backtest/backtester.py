"""Backtesting-Modul mit Performance-Metriken."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Optional

import numpy as np
import pandas as pd

from ..strategies.base_strategy import BaseStrategy, SignalType


@dataclass
class BacktestResult:
    total_return: float
    annual_return: float
    sharpe_ratio: float
    sortino_ratio: float
    max_drawdown: float
    win_rate: float
    profit_factor: float
    total_trades: int
    winning_trades: int
    losing_trades: int
    avg_win: float
    avg_loss: float
    equity_curve: list[float] = field(default_factory=list)

    def __str__(self) -> str:
        return (
            f"\n{'='*50}\n"
            f"  BACKTEST ERGEBNISSE\n"
            f"{'='*50}\n"
            f"  Gesamtrendite    : {self.total_return:+.2%}\n"
            f"  Jahresrendite    : {self.annual_return:+.2%}\n"
            f"  Sharpe Ratio     : {self.sharpe_ratio:.3f}\n"
            f"  Sortino Ratio    : {self.sortino_ratio:.3f}\n"
            f"  Max. Drawdown    : {self.max_drawdown:.2%}\n"
            f"  Trefferquote     : {self.win_rate:.1%}\n"
            f"  Profit Factor    : {self.profit_factor:.2f}\n"
            f"  Trades gesamt    : {self.total_trades}\n"
            f"  Gewinner         : {self.winning_trades}\n"
            f"  Verlierer        : {self.losing_trades}\n"
            f"  Ø Gewinn         : {self.avg_win:+.4f}\n"
            f"  Ø Verlust        : {self.avg_loss:+.4f}\n"
            f"{'='*50}"
        )


class Backtester:
    """Simuliert die Strategie auf historischen Daten."""

    def __init__(
        self,
        strategy: BaseStrategy,
        initial_capital: float = 10_000.0,
        commission: float = 0.001,
        slippage: float = 0.0005,
        lookback: int = 100,
    ) -> None:
        self.strategy = strategy
        self.initial_capital = initial_capital
        self.commission = commission
        self.slippage = slippage
        self.lookback = lookback
        self._logger = logging.getLogger(self.__class__.__name__)

    def run(self, df: pd.DataFrame) -> BacktestResult:
        """Fuehrt den Backtest durch.

        Args:
            df: OHLCV DataFrame mit DatetimeIndex.

        Returns:
            BacktestResult mit allen Metriken.
        """
        capital = self.initial_capital
        equity_curve: list[float] = [capital]
        trades: list[dict] = []
        open_trade: Optional[dict] = None

        for i in range(self.lookback, len(df)):
            window = df.iloc[:i].copy()
            bar = df.iloc[i]
            price = float(bar["close"])

            # Offenen Trade auf TP/SL pruefen
            if open_trade is not None:
                exit_price = None
                if open_trade["direction"] == "long":
                    if price <= open_trade["stop_loss"]:
                        exit_price = open_trade["stop_loss"]
                    elif price >= open_trade["take_profit"]:
                        exit_price = open_trade["take_profit"]
                else:
                    if price >= open_trade["stop_loss"]:
                        exit_price = open_trade["stop_loss"]
                    elif price <= open_trade["take_profit"]:
                        exit_price = open_trade["take_profit"]

                if exit_price is not None:
                    pnl = self._calc_pnl(open_trade, exit_price)
                    capital += pnl
                    equity_curve.append(capital)
                    trades.append({"pnl": pnl, "exit": exit_price})
                    self._logger.debug(
                        f"Trade geschlossen @ {exit_price:.4f} | PnL={pnl:+.2f} | Kapital={capital:.2f}"
                    )
                    open_trade = None

            # Neues Signal generieren (nur wenn kein offener Trade)
            if open_trade is None:
                signal = self.strategy.generate_signal(window)
                if signal and signal.is_entry:
                    entry = price * (1 + self.slippage if signal.signal_type == SignalType.BUY else 1 - self.slippage)
                    cost = entry * signal.size * capital * self.commission
                    capital -= cost
                    open_trade = {
                        "direction": "long" if signal.signal_type == SignalType.BUY else "short",
                        "entry": entry,
                        "stop_loss": signal.stop_loss,
                        "take_profit": signal.take_profit,
                        "size": signal.size,
                        "capital_at_entry": capital,
                    }
                    self._logger.debug(
                        f"Trade eroeffnet @ {entry:.4f} | SL={signal.stop_loss:.4f} TP={signal.take_profit:.4f}"
                    )

        # Letzten offenen Trade zum Schlusskurs schliessen
        if open_trade is not None:
            last_price = float(df.iloc[-1]["close"])
            pnl = self._calc_pnl(open_trade, last_price)
            capital += pnl
            trades.append({"pnl": pnl, "exit": last_price})
        equity_curve.append(capital)

        return self._compute_metrics(equity_curve, trades)

    def _calc_pnl(self, trade: dict, exit_price: float) -> float:
        size_capital = trade["capital_at_entry"] * trade["size"]
        if trade["direction"] == "long":
            ret = (exit_price - trade["entry"]) / trade["entry"]
        else:
            ret = (trade["entry"] - exit_price) / trade["entry"]
        return size_capital * ret

    def _compute_metrics(self, equity: list[float], trades: list[dict]) -> BacktestResult:
        eq = np.array(equity)
        returns = np.diff(eq) / eq[:-1]

        total_return = (eq[-1] - eq[0]) / eq[0]
        n_years = max(len(equity) / (252 * 24), 1 / 365)
        annual_return = (1 + total_return) ** (1 / n_years) - 1

        rf = 0.0
        excess = returns - rf / (252 * 24)
        sharpe = float(np.mean(excess) / np.std(excess) * np.sqrt(252 * 24)) if np.std(excess) > 0 else 0.0

        neg = excess[excess < 0]
        sortino = float(np.mean(excess) / np.std(neg) * np.sqrt(252 * 24)) if len(neg) > 0 and np.std(neg) > 0 else 0.0

        peak = np.maximum.accumulate(eq)
        drawdowns = (eq - peak) / peak
        max_dd = float(drawdowns.min())

        pnls = [t["pnl"] for t in trades]
        wins = [p for p in pnls if p > 0]
        losses = [p for p in pnls if p <= 0]
        win_rate = len(wins) / len(pnls) if pnls else 0.0
        profit_factor = sum(wins) / abs(sum(losses)) if losses and sum(losses) != 0 else float("inf")

        return BacktestResult(
            total_return=total_return,
            annual_return=annual_return,
            sharpe_ratio=sharpe,
            sortino_ratio=sortino,
            max_drawdown=max_dd,
            win_rate=win_rate,
            profit_factor=profit_factor,
            total_trades=len(trades),
            winning_trades=len(wins),
            losing_trades=len(losses),
            avg_win=float(np.mean(wins)) if wins else 0.0,
            avg_loss=float(np.mean(losses)) if losses else 0.0,
            equity_curve=equity,
        )

    def print_results(self, result: BacktestResult) -> None:
        print(result)
