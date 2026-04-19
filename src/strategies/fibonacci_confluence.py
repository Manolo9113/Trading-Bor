"""Fibonacci-Confluence-Strategie.

Generiert Signale nur wenn BEIDE Bedingungen erfüllt sind:
  1. Preis liegt nahe einem Fibonacci-Level (Retracement/Extension)
  2. Mindestens ein Chart-Pattern bestätigt die Richtung

Das erhöht die Trefferquote erheblich (Confluence-Filter).
"""

from __future__ import annotations

from typing import Optional

import numpy as np
import pandas as pd

from .base_strategy import BaseStrategy, Signal, SignalType
from ..indicators.fibonacci import FibonacciCalculator
from ..indicators.patterns import PatternDetector
from ..risk.risk_manager import RiskManager


class FibonacciConfluenceStrategy(BaseStrategy):
    """Fibonacci + Chart-Pattern Confluence-Strategie."""

    def __init__(
        self,
        fib_calc: FibonacciCalculator,
        pattern_det: PatternDetector,
        risk_mgr: RiskManager,
        config: dict,
    ) -> None:
        super().__init__(config)
        self.fib_calc = fib_calc
        self.pattern_det = pattern_det
        self.risk_mgr = risk_mgr
        self.min_rr: float = config.get("risk", {}).get("take_profit_ratio", 2.0)
        self.atr_period: int = 14

    # ------------------------------------------------------------------
    # ATR-Hilfsmethode
    # ------------------------------------------------------------------

    @staticmethod
    def _atr(df: pd.DataFrame, period: int = 14) -> float:
        """Berechnet den letzten ATR-Wert."""
        high = df["high"]
        low = df["low"]
        close = df["close"]
        tr = pd.concat([
            high - low,
            (high - close.shift()).abs(),
            (low - close.shift()).abs(),
        ], axis=1).max(axis=1)
        return float(tr.rolling(period).mean().iloc[-1])

    # ------------------------------------------------------------------
    # Signal-Generierung
    # ------------------------------------------------------------------

    def generate_signal(self, df: pd.DataFrame) -> Optional[Signal]:
        """Prüft Fib-Level + Pattern-Confluence und gibt Signal zurück."""
        if len(df) < 50:
            return None

        current_price = float(df["close"].iloc[-1])
        atr = self._atr(df, self.atr_period)
        if atr == 0 or np.isnan(atr):
            return None

        # 1. Fibonacci-Zonen berechnen
        zones = self.fib_calc.calculate(df, n_recent=2)
        if not zones:
            return None

        # 2. Chart-Pattern erkennen
        patterns = self.pattern_det.detect(df)
        if not patterns:
            return None

        bullish_patterns = [p for p in patterns if p.direction == "bullish"]
        bearish_patterns = [p for p in patterns if p.direction == "bearish"]

        # 3. Confluence prüfen
        for zone in zones:
            fib_level = self.fib_calc.is_near_level(current_price, zone)
            if fib_level is None:
                continue

            # Bullisches Confluence-Signal
            if bullish_patterns:
                best_pattern = max(bullish_patterns, key=lambda p: p.strength)
                stop_loss = current_price - atr * self.config["risk"]["stop_loss_atr_mult"]
                take_profit = current_price + atr * self.config["risk"]["stop_loss_atr_mult"] * self.min_rr
                size = self.risk_mgr.position_size(
                    capital=1.0,  # normiert; Backtester skaliert
                    entry=current_price,
                    stop_loss=stop_loss,
                )
                confidence = round(
                    (fib_level.ratio if fib_level.ratio in (0.382, 0.5, 0.618) else 0.5)
                    * best_pattern.strength,
                    2,
                )
                # Key Fib-Level bekommen höhere Confidence
                if fib_level.ratio in (0.382, 0.5, 0.618):
                    confidence = min(1.0, confidence * 1.2)

                return Signal(
                    signal_type=SignalType.BUY,
                    price=current_price,
                    stop_loss=stop_loss,
                    take_profit=take_profit,
                    size=size,
                    confidence=confidence,
                    reason=(
                        f"Fib {fib_level.label} + {best_pattern.description} "
                        f"(Zone: {zone.swing_low:.4f}–{zone.swing_high:.4f})"
                    ),
                )

            # Bärisches Confluence-Signal
            if bearish_patterns:
                best_pattern = max(bearish_patterns, key=lambda p: p.strength)
                stop_loss = current_price + atr * self.config["risk"]["stop_loss_atr_mult"]
                take_profit = current_price - atr * self.config["risk"]["stop_loss_atr_mult"] * self.min_rr
                size = self.risk_mgr.position_size(
                    capital=1.0,
                    entry=current_price,
                    stop_loss=stop_loss,
                )
                confidence = round(
                    (fib_level.ratio if fib_level.ratio in (0.382, 0.5, 0.618) else 0.5)
                    * best_pattern.strength,
                    2,
                )
                if fib_level.ratio in (0.382, 0.5, 0.618):
                    confidence = min(1.0, confidence * 1.2)

                return Signal(
                    signal_type=SignalType.SELL,
                    price=current_price,
                    stop_loss=stop_loss,
                    take_profit=take_profit,
                    size=size,
                    confidence=confidence,
                    reason=(
                        f"Fib {fib_level.label} + {best_pattern.description} "
                        f"(Zone: {zone.swing_low:.4f}–{zone.swing_high:.4f})"
                    ),
                )

        return None
