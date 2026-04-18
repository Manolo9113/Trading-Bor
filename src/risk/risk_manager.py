"""Risk Manager: Positionsgroesse, Stop-Loss, Drawdown-Kontrolle."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Trade:
    entry_price: float
    stop_loss: float
    take_profit: float
    size: float
    direction: str  # "long" | "short"
    pnl: float = 0.0
    closed: bool = False


class RiskManager:
    """Berechnet Positionsgroessen und ueberwacht Risikolimits."""

    def __init__(self, config: dict) -> None:
        self.max_position_size: float = config.get("max_position_size", 0.1)
        self.risk_per_trade: float = config.get("risk_per_trade", 0.02)
        self.stop_loss_atr_mult: float = config.get("stop_loss_atr_mult", 2.0)
        self.take_profit_ratio: float = config.get("take_profit_ratio", 2.0)
        self.max_open_positions: int = config.get("max_open_positions", 3)
        self.max_daily_drawdown: float = config.get("max_daily_drawdown", 0.05)
        self.position_spacing: float = config.get("position_spacing", 0.005)
        self._open_trades: list[Trade] = []
        self._daily_start_capital: Optional[float] = None
        self._logger = logging.getLogger(self.__class__.__name__)

    def position_size(
        self,
        capital: float,
        entry: float,
        stop_loss: float,
    ) -> float:
        """Berechnet die Positionsgroesse basierend auf 2%-Risiko-Regel.

        Returns:
            Anteil des Kapitals (0.0 - 1.0) fuer diese Position.
        """
        risk_amount = capital * self.risk_per_trade
        price_risk = abs(entry - stop_loss)
        if price_risk == 0:
            return 0.0
        units = risk_amount / price_risk
        position_value = units * entry
        size = position_value / capital
        return round(min(size, self.max_position_size), 4)

    def can_open_position(self, capital: float, current_capital: float) -> bool:
        """Prueft ob ein neuer Trade erlaubt ist."""
        if len(self._open_trades) >= self.max_open_positions:
            self._logger.warning("Max offene Positionen erreicht.")
            return False
        if self._daily_start_capital is None:
            self._daily_start_capital = capital
        drawdown = (self._daily_start_capital - current_capital) / self._daily_start_capital
        if drawdown >= self.max_daily_drawdown:
            self._logger.warning(f"Max. Tages-Drawdown erreicht: {drawdown:.1%}")
            return False
        return True

    def has_position_spacing(self, new_entry: float) -> bool:
        """Prueft Mindestabstand zu bestehenden Positionen."""
        for trade in self._open_trades:
            dist = abs(trade.entry_price - new_entry) / trade.entry_price
            if dist < self.position_spacing:
                return False
        return True

    def register_trade(self, trade: Trade) -> None:
        self._open_trades.append(trade)

    def close_trade(self, trade: Trade, exit_price: float) -> float:
        """Schliesst einen Trade und berechnet PnL."""
        if trade.direction == "long":
            trade.pnl = (exit_price - trade.entry_price) / trade.entry_price * trade.size
        else:
            trade.pnl = (trade.entry_price - exit_price) / trade.entry_price * trade.size
        trade.closed = True
        if trade in self._open_trades:
            self._open_trades.remove(trade)
        return trade.pnl

    def reset_daily(self, capital: float) -> None:
        self._daily_start_capital = capital

    @property
    def open_trade_count(self) -> int:
        return len(self._open_trades)
