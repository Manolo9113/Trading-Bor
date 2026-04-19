"""Stock-Momentum-Strategie fuer Alpaca (US-Aktien).

Nutzt die Screener-Watchlist als Universum.
Signal: EMA-Crossover + RSI-Bestaetigung + ATR-basierter Stop.
"""

from __future__ import annotations

from typing import Optional

import numpy as np
import pandas as pd

from .base_strategy import BaseStrategy, Signal, SignalType
from ..indicators.technical import rsi, ema, atr


class StockMomentumStrategy(BaseStrategy):
    """EMA-Crossover + RSI-Filter fuer Screener-Aktien.

    Einstieg (Long):
      - EMA20 kreuzt EMA50 von unten (Golden Cross auf kuerzerer Basis)
      - RSI zwischen 45 und 70 (Momentum ohne Ueberkauf)
      - Kurs ueber EMA200 (langfristiger Aufwaertstrend)

    Ausstieg:
      - Stop-Loss: 2x ATR unter Einstieg
      - Take-Profit: 3x ATR ueber Einstieg (R:R = 1:1.5)
    """

    def __init__(self, config: dict) -> None:
        super().__init__(config)
        cfg = config.get("stock_momentum", {})
        self.ema_fast: int   = cfg.get("ema_fast", 20)
        self.ema_slow: int   = cfg.get("ema_slow", 50)
        self.ema_trend: int  = cfg.get("ema_trend", 200)
        self.rsi_period: int = cfg.get("rsi_period", 14)
        self.rsi_min: float  = cfg.get("rsi_min", 45.0)
        self.rsi_max: float  = cfg.get("rsi_max", 70.0)
        self.atr_period: int = cfg.get("atr_period", 14)
        self.sl_mult: float  = config.get("risk", {}).get("stop_loss_atr_mult", 2.0)
        self.tp_mult: float  = config.get("risk", {}).get("take_profit_ratio", 1.5)
        self.risk_pct: float = config.get("risk", {}).get("risk_per_trade", 0.02)

    def generate_signal(self, df: pd.DataFrame) -> Optional[Signal]:
        """Gibt BUY-Signal wenn alle Bedingungen erfuellt."""
        min_bars = self.ema_trend + self.rsi_period + 5
        if len(df) < min_bars:
            return None

        close = df["close"]
        price = float(close.iloc[-1])

        # Indikatoren
        ema_f  = ema(close, self.ema_fast)
        ema_s  = ema(close, self.ema_slow)
        ema_t  = ema(close, self.ema_trend)
        rsi_v  = rsi(close, self.rsi_period)
        atr_v  = atr(df, self.atr_period)

        curr_rsi  = float(rsi_v.iloc[-1])
        curr_atr  = float(atr_v.iloc[-1])
        curr_ema_f = float(ema_f.iloc[-1])
        curr_ema_s = float(ema_s.iloc[-1])
        prev_ema_f = float(ema_f.iloc[-2])
        prev_ema_s = float(ema_s.iloc[-2])
        curr_ema_t = float(ema_t.iloc[-1])

        if any(np.isnan(v) for v in [curr_rsi, curr_atr, curr_ema_f, curr_ema_s, curr_ema_t]):
            return None

        # Bedingungen
        golden_cross = prev_ema_f < prev_ema_s and curr_ema_f >= curr_ema_s
        rsi_ok       = self.rsi_min <= curr_rsi <= self.rsi_max
        above_trend  = price > curr_ema_t

        if not (golden_cross and rsi_ok and above_trend):
            return None

        stop_loss   = price - self.sl_mult * curr_atr
        take_profit = price + self.tp_mult * self.sl_mult * curr_atr
        size = min(
            self.risk_pct / (abs(price - stop_loss) / price),
            config.get("risk", {}).get("max_position_size", 0.1)
            if False else 0.1,
        )

        return Signal(
            signal_type=SignalType.BUY,
            price=price,
            stop_loss=round(stop_loss, 2),
            take_profit=round(take_profit, 2),
            size=round(min(size, 0.1), 4),
            confidence=round(min(1.0, (curr_rsi - self.rsi_min) / 25), 2),
            reason=(
                f"EMA{self.ema_fast}/{self.ema_slow} Crossover "
                f"| RSI={curr_rsi:.1f} "
                f"| Kurs ueber EMA{self.ema_trend}"
            ),
        )
