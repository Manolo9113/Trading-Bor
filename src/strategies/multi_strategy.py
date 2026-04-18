"""Multi-Strategy mit Majority-Voting.

Kombiniert Signale mehrerer Strategien. Ein Trade wird nur
eingegangen wenn eine konfigurierbare Mindestanzahl von
Strategien dieselbe Richtung signalisiert.
"""

from __future__ import annotations

from typing import Optional

import pandas as pd

from .base_strategy import BaseStrategy, Signal, SignalType


class MultiStrategy(BaseStrategy):
    """Majority-Voting ueber mehrere Strategien.

    Args:
        strategies: Liste von Strategien die befragt werden.
        min_votes:  Mindestanzahl uebereinstimmender Signale
                    damit ein Trade ausgefuehrt wird.
    """

    def __init__(
        self,
        strategies: list[BaseStrategy],
        config: dict,
        min_votes: int = 2,
    ) -> None:
        super().__init__(config)
        self.strategies = strategies
        self.min_votes = min_votes
        self.name = f"MultiStrategy({len(strategies)}-of-{min_votes})"

    def generate_signal(self, df: pd.DataFrame) -> Optional[Signal]:
        """Gibt ein Signal zurueck wenn mindestens min_votes Strategien
        dieselbe Richtung (BUY/SELL) signalisieren.
        """
        buy_signals: list[Signal] = []
        sell_signals: list[Signal] = []

        for strategy in self.strategies:
            try:
                sig = strategy.generate_signal(df)
            except Exception:
                continue
            if sig is None:
                continue
            if sig.signal_type == SignalType.BUY:
                buy_signals.append(sig)
            elif sig.signal_type == SignalType.SELL:
                sell_signals.append(sig)

        # BUY-Konsens
        if len(buy_signals) >= self.min_votes:
            return self._merge(buy_signals, SignalType.BUY)

        # SELL-Konsens
        if len(sell_signals) >= self.min_votes:
            return self._merge(sell_signals, SignalType.SELL)

        return None

    @staticmethod
    def _merge(signals: list[Signal], direction: SignalType) -> Signal:
        """Mittelt die Parameter aller Einzel-Signale."""
        avg_price      = sum(s.price       for s in signals) / len(signals)
        avg_sl         = sum(s.stop_loss   for s in signals) / len(signals)
        avg_tp         = sum(s.take_profit for s in signals) / len(signals)
        avg_size       = sum(s.size        for s in signals) / len(signals)
        avg_confidence = sum(s.confidence  for s in signals) / len(signals)
        reasons = " | ".join(s.reason for s in signals if s.reason)
        return Signal(
            signal_type=direction,
            price=round(avg_price, 8),
            stop_loss=round(avg_sl, 8),
            take_profit=round(avg_tp, 8),
            size=round(avg_size, 4),
            confidence=round(avg_confidence, 2),
            reason=f"[Voting {len(signals)}x] {reasons}",
        )
