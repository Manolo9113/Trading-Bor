"""RSI + MACD Strategie.

Alternative Strategie zum Vergleich mit der Fibonacci-Confluence-Strategie.
Signal: RSI ueberkauft/ueberverkauft + MACD-Crossover.
"""

from __future__ import annotations

from typing import Optional

import numpy as np
import pandas as pd

from .base_strategy import BaseStrategy, Signal, SignalType
from ..indicators.technical import rsi, macd, atr


class RsiMacdStrategy(BaseStrategy):
    """RSI-Ueberkauft/Ueberverkauft + MACD-Crossover-Strategie."""

    def __init__(self, config: dict) -> None:
        super().__init__(config)
        strat_cfg = config.get("rsi_macd", {})
        self.rsi_period: int = strat_cfg.get("rsi_period", 14)
        self.rsi_oversold: float = strat_cfg.get("rsi_oversold", 30.0)
        self.rsi_overbought: float = strat_cfg.get("rsi_overbought", 70.0)
        self.macd_fast: int = strat_cfg.get("macd_fast", 12)
        self.macd_slow: int = strat_cfg.get("macd_slow", 26)
        self.macd_signal: int = strat_cfg.get("macd_signal", 9)
        self.atr_period: int = strat_cfg.get("atr_period", 14)
        self.atr_sl_mult: float = config.get("risk", {}).get("stop_loss_atr_mult", 2.0)
        self.rr_ratio: float = config.get("risk", {}).get("take_profit_ratio", 2.0)
        self.risk_per_trade: float = config.get("risk", {}).get("risk_per_trade", 0.02)

    def generate_signal(self, df: pd.DataFrame) -> Optional[Signal]:
        if len(df) < self.macd_slow + self.macd_signal + 5:
            return None

        close = df["close"]
        current_price = float(close.iloc[-1])

        rsi_vals = rsi(close, self.rsi_period)
        macd_line, signal_line, histogram = macd(
            close, self.macd_fast, self.macd_slow, self.macd_signal
        )
        atr_val = float(atr(df, self.atr_period).iloc[-1])

        if np.isnan(atr_val) or atr_val == 0:
            return None

        current_rsi = float(rsi_vals.iloc[-1])
        prev_hist = float(histogram.iloc[-2])
        curr_hist = float(histogram.iloc[-1])

        # Bullisch: RSI ueberverkauft + MACD-Histogram dreht positiv
        if current_rsi < self.rsi_oversold and prev_hist < 0 and curr_hist > prev_hist:
            stop_loss = current_price - atr_val * self.atr_sl_mult
            take_profit = current_price + atr_val * self.atr_sl_mult * self.rr_ratio
            size = min(
                self.risk_per_trade / (abs(current_price - stop_loss) / current_price),
                0.1,
            )
            return Signal(
                signal_type=SignalType.BUY,
                price=current_price,
                stop_loss=stop_loss,
                take_profit=take_profit,
                size=round(size, 4),
                confidence=round((self.rsi_oversold - current_rsi) / self.rsi_oversold, 2),
                reason=f"RSI={current_rsi:.1f} ueberverkauft + MACD-Histogram dreht hoch",
            )

        # Baerisch: RSI ueberkauft + MACD-Histogram dreht negativ
        if current_rsi > self.rsi_overbought and prev_hist > 0 and curr_hist < prev_hist:
            stop_loss = current_price + atr_val * self.atr_sl_mult
            take_profit = current_price - atr_val * self.atr_sl_mult * self.rr_ratio
            size = min(
                self.risk_per_trade / (abs(stop_loss - current_price) / current_price),
                0.1,
            )
            return Signal(
                signal_type=SignalType.SELL,
                price=current_price,
                stop_loss=stop_loss,
                take_profit=take_profit,
                size=round(size, 4),
                confidence=round((current_rsi - self.rsi_overbought) / (100 - self.rsi_overbought), 2),
                reason=f"RSI={current_rsi:.1f} ueberkauft + MACD-Histogram dreht tief",
            )

        return None
