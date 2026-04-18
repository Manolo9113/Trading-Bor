"""Paper-Trading-Wrapper.

Simuliert Trades ohne echtes Kapital. Protokolliert alle Signale
und PnL in einer lokalen CSV-Datei fuer spaetere Auswertung.
"""

from __future__ import annotations

import csv
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional

import pandas as pd

from .base_strategy import BaseStrategy, Signal, SignalType


class PaperTrader:
    """Wrapped eine Strategie fuer Paper-Trading mit PnL-Tracking."""

    def __init__(
        self,
        strategy: BaseStrategy,
        initial_capital: float = 10_000.0,
        log_file: str = "logs/paper_trades.csv",
    ) -> None:
        self.strategy = strategy
        self.capital = initial_capital
        self._initial = initial_capital
        self.log_file = Path(log_file)
        self.log_file.parent.mkdir(parents=True, exist_ok=True)
        self._open_trade: Optional[dict] = None
        self._trade_count = 0
        self._logger = logging.getLogger(self.__class__.__name__)
        self._init_csv()

    def _init_csv(self) -> None:
        if not self.log_file.exists():
            with open(self.log_file, "w", newline="") as f:
                writer = csv.writer(f)
                writer.writerow([
                    "timestamp", "action", "price",
                    "stop_loss", "take_profit", "size",
                    "pnl", "capital", "reason",
                ])

    def tick(self, df: pd.DataFrame) -> Optional[Signal]:
        """Verarbeitet neue Kerze: prueft offene Position und generiert Signale."""
        price = float(df["close"].iloc[-1])
        ts = str(df.index[-1])

        # Offene Position auf SL/TP pruefen
        if self._open_trade is not None:
            t = self._open_trade
            exit_price = None
            exit_reason = ""

            if t["direction"] == "long":
                if price <= t["stop_loss"]:
                    exit_price, exit_reason = t["stop_loss"], "Stop-Loss"
                elif price >= t["take_profit"]:
                    exit_price, exit_reason = t["take_profit"], "Take-Profit"
            else:
                if price >= t["stop_loss"]:
                    exit_price, exit_reason = t["stop_loss"], "Stop-Loss"
                elif price <= t["take_profit"]:
                    exit_price, exit_reason = t["take_profit"], "Take-Profit"

            if exit_price is not None:
                size_val = t["capital_at_entry"] * t["size"]
                if t["direction"] == "long":
                    pnl = size_val * (exit_price - t["entry"]) / t["entry"]
                else:
                    pnl = size_val * (t["entry"] - exit_price) / t["entry"]
                self.capital += pnl
                self._log(ts, "CLOSE", exit_price, t["stop_loss"],
                          t["take_profit"], t["size"], pnl, exit_reason)
                self._logger.info(
                    f"[Paper] CLOSE @ {exit_price:.4f} | PnL={pnl:+.2f} "
                    f"| Kapital={self.capital:.2f} | {exit_reason}"
                )
                self._open_trade = None

        # Neues Signal
        if self._open_trade is None:
            signal = self.strategy.generate_signal(df)
            if signal and signal.is_entry:
                direction = "long" if signal.signal_type == SignalType.BUY else "short"
                self._open_trade = {
                    "direction": direction,
                    "entry": signal.price,
                    "stop_loss": signal.stop_loss,
                    "take_profit": signal.take_profit,
                    "size": signal.size,
                    "capital_at_entry": self.capital,
                }
                self._trade_count += 1
                self._log(ts, signal.signal_type.value, signal.price,
                          signal.stop_loss, signal.take_profit,
                          signal.size, 0.0, signal.reason)
                self._logger.info(
                    f"[Paper] {signal.signal_type.value} @ {signal.price:.4f} "
                    f"SL={signal.stop_loss:.4f} TP={signal.take_profit:.4f} "
                    f"| {signal.reason}"
                )
                return signal
        return None

    def stats(self) -> dict:
        """Gibt aktuelle Paper-Trading-Statistiken zurueck."""
        total_return = (self.capital - self._initial) / self._initial
        return {
            "capital": round(self.capital, 2),
            "initial_capital": self._initial,
            "total_return": round(total_return, 4),
            "total_trades": self._trade_count,
            "open_position": self._open_trade is not None,
        }

    def _log(self, ts, action, price, sl, tp, size, pnl, reason) -> None:
        with open(self.log_file, "a", newline="") as f:
            writer = csv.writer(f)
            writer.writerow([ts, action, price, sl, tp,
                             size, round(pnl, 6), round(self.capital, 2), reason])
