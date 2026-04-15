"""Abstrakte Basis-Strategie.

Alle konkreten Strategien müssen von BaseStrategy erben
und die Methode `generate_signal` implementieren.
"""

from __future__ import annotations

import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from typing import Optional

import pandas as pd


class SignalType(str, Enum):
    BUY = "BUY"
    SELL = "SELL"
    CLOSE_LONG = "CLOSE_LONG"
    CLOSE_SHORT = "CLOSE_SHORT"
    HOLD = "HOLD"


@dataclass
class Signal:
    """Handelssignal einer Strategie."""
    signal_type: SignalType
    price: float
    stop_loss: float
    take_profit: float
    size: float             # Anteil des Kapitals (0.0 – 1.0)
    confidence: float       # 0.0 – 1.0
    reason: str = ""

    @property
    def is_entry(self) -> bool:
        return self.signal_type in (SignalType.BUY, SignalType.SELL)

    @property
    def is_exit(self) -> bool:
        return self.signal_type in (SignalType.CLOSE_LONG, SignalType.CLOSE_SHORT)

    @property
    def risk_reward(self) -> float:
        if self.signal_type == SignalType.BUY:
            risk = self.price - self.stop_loss
            reward = self.take_profit - self.price
        elif self.signal_type == SignalType.SELL:
            risk = self.stop_loss - self.price
            reward = self.price - self.take_profit
        else:
            return 0.0
        return reward / risk if risk > 0 else 0.0


class BaseStrategy(ABC):
    """Abstrakte Basisklasse für alle Handelsstrategien."""

    def __init__(self, config: dict) -> None:
        self.config = config
        self.name = self.__class__.__name__
        self._open_positions: list[Signal] = []

    @abstractmethod
    def generate_signal(
        self, df: pd.DataFrame
    ) -> Optional[Signal]:
        """Generiert ein Handelssignal basierend auf dem DataFrame.

        Args:
            df: OHLCV DataFrame mit mind. [open, high, low, close, volume].

        Returns:
            Signal-Objekt oder None wenn kein Signal.
        """
        ...

    def run_live(
        self,
        connector,
        symbol: str,
        timeframe: str,
        poll_interval: int = 60,
    ) -> None:
        """Echtzeit-Loop: holt neue Daten und generiert Signale."""
        import logging
        logger = logging.getLogger(self.name)
        logger.info(f"Live-Loop gestartet: {symbol} @ {timeframe}")

        while True:
            try:
                df = connector.fetch_ohlcv(
                    symbol=symbol,
                    timeframe=timeframe,
                    limit=200,
                )
                if df is not None and not df.empty:
                    signal = self.generate_signal(df)
                    if signal and signal.is_entry:
                        logger.info(
                            f"Signal: {signal.signal_type.value} @ {signal.price:.4f} "
                            f"SL={signal.stop_loss:.4f} TP={signal.take_profit:.4f} "
                            f"R:R={signal.risk_reward:.2f} | {signal.reason}"
                        )
                        connector.place_order(symbol, signal)
            except KeyboardInterrupt:
                logger.info("Live-Loop durch Benutzer beendet.")
                break
            except Exception as exc:
                logger.error(f"Fehler im Live-Loop: {exc}")

            time.sleep(poll_interval)
