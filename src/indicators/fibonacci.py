"""Fibonacci-Kalkulator mit WMA-Variante.

Berechnet Retracement- und Extension-Level basierend auf
Swing-Hochs und Swing-Tiefs. Optionale WMA-Glättung der
Preisreihe vor der Swing-Erkennung.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

import numpy as np
import pandas as pd
from scipy.signal import argrelextrema


@dataclass
class FibLevel:
    """Ein einzelnes Fibonacci-Level."""
    ratio: float
    price: float
    label: str


@dataclass
class FibonacciZone:
    """Vollständiger Fibonacci-Rahmen mit allen Leveln."""
    swing_high: float
    swing_low: float
    direction: str          # "up" | "down"
    high_idx: int
    low_idx: int
    retracement_levels: list[FibLevel] = field(default_factory=list)
    extension_levels: list[FibLevel] = field(default_factory=list)

    def closest_level(
        self,
        price: float,
        tolerance: float = 0.003,
        include_extensions: bool = False,
    ) -> Optional[FibLevel]:
        """Gibt das nächste Fib-Level zurück, falls innerhalb der Toleranz."""
        levels = self.retracement_levels[:]
        if include_extensions:
            levels += self.extension_levels
        best: Optional[FibLevel] = None
        best_dist = float("inf")
        for lvl in levels:
            dist = abs(lvl.price - price) / price
            if dist < tolerance and dist < best_dist:
                best_dist = dist
                best = lvl
        return best


class FibonacciCalculator:
    """Berechnet Fibonacci-Level basierend auf Swing-Hochs/-Tiefs."""

    DEFAULT_RETRACEMENT = [0.0, 0.236, 0.382, 0.5, 0.618, 0.786, 1.0]
    DEFAULT_EXTENSION = [1.272, 1.414, 1.618, 2.0, 2.618]

    def __init__(self, config: dict) -> None:
        self.swing_window: int = config.get("swing_window", 10)
        self.use_wma: bool = config.get("use_wma", True)
        self.wma_period: int = config.get("wma_period", 14)
        self.retracement_ratios: list[float] = config.get(
            "levels_retracement", self.DEFAULT_RETRACEMENT
        )
        self.extension_ratios: list[float] = config.get(
            "levels_extension", self.DEFAULT_EXTENSION
        )
        self.confluence_tolerance: float = config.get("confluence_tolerance", 0.003)

    # ------------------------------------------------------------------
    # WMA
    # ------------------------------------------------------------------

    @staticmethod
    def wma(series: pd.Series, period: int) -> pd.Series:
        """Weighted Moving Average."""
        weights = np.arange(1, period + 1, dtype=float)
        return (
            series.rolling(period)
            .apply(lambda x: np.dot(x, weights) / weights.sum(), raw=True)
        )

    # ------------------------------------------------------------------
    # Swing-Erkennung
    # ------------------------------------------------------------------

    def find_swings(
        self, df: pd.DataFrame
    ) -> tuple[np.ndarray, np.ndarray]:
        """Findet Swing-Hochs und Swing-Tiefs via argrelextrema.

        Returns:
            (high_indices, low_indices)
        """
        prices = df["close"].copy()
        if self.use_wma and len(prices) >= self.wma_period:
            prices = self.wma(prices, self.wma_period).dropna()

        order = max(2, self.swing_window // 2)
        arr = prices.values

        highs = argrelextrema(arr, np.greater_equal, order=order)[0]
        lows = argrelextrema(arr, np.less_equal, order=order)[0]
        return highs, lows

    # ------------------------------------------------------------------
    # Level-Berechnung
    # ------------------------------------------------------------------

    def _build_zone(
        self,
        high: float,
        low: float,
        high_idx: int,
        low_idx: int,
    ) -> FibonacciZone:
        """Baut FibonacciZone aus Swing-High und Swing-Low."""
        diff = high - low
        direction = "up" if low_idx < high_idx else "down"

        retracements = []
        for r in self.retracement_ratios:
            if direction == "up":
                price = high - r * diff
            else:
                price = low + r * diff
            retracements.append(FibLevel(ratio=r, price=round(price, 8), label=f"{r:.3f}"))

        extensions = []
        for e in self.extension_ratios:
            if direction == "up":
                price = low - (e - 1.0) * diff if e > 1.0 else low + e * diff
                price = high + (e - 1.0) * diff
            else:
                price = low - (e - 1.0) * diff
            extensions.append(FibLevel(ratio=e, price=round(price, 8), label=f"{e:.3f}"))

        return FibonacciZone(
            swing_high=high,
            swing_low=low,
            direction=direction,
            high_idx=high_idx,
            low_idx=low_idx,
            retracement_levels=retracements,
            extension_levels=extensions,
        )

    def calculate(
        self, df: pd.DataFrame, n_recent: int = 1
    ) -> list[FibonacciZone]:
        """Berechnet die letzten n_recent Fibonacci-Zonen.

        Args:
            df: OHLCV DataFrame mit Spalten [open, high, low, close, volume].
            n_recent: Anzahl der zurückzugebenden Zonen (neueste zuerst).

        Returns:
            Liste von FibonacciZone-Objekten.
        """
        high_idxs, low_idxs = self.find_swings(df)

        if len(high_idxs) == 0 or len(low_idxs) == 0:
            return []

        zones: list[FibonacciZone] = []

        # Letzten n_recent Paare aus High + Low kombinieren
        recent_highs = high_idxs[-n_recent * 2:]
        recent_lows = low_idxs[-n_recent * 2:]

        for h_idx in recent_highs[-n_recent:]:
            # Nächstes Low vor oder nach diesem High suchen
            candidates_before = recent_lows[recent_lows < h_idx]
            candidates_after = recent_lows[recent_lows > h_idx]

            if len(candidates_before) > 0:
                l_idx = candidates_before[-1]
                high_val = df["high"].iloc[h_idx]
                low_val = df["low"].iloc[l_idx]
                zones.append(self._build_zone(high_val, low_val, h_idx, l_idx))

            if len(candidates_after) > 0:
                l_idx = candidates_after[0]
                high_val = df["high"].iloc[h_idx]
                low_val = df["low"].iloc[l_idx]
                zones.append(self._build_zone(high_val, low_val, h_idx, l_idx))

        # Neueste zuerst, Duplikate entfernen
        seen = set()
        unique_zones = []
        for z in reversed(zones):
            key = (z.swing_high, z.swing_low)
            if key not in seen:
                seen.add(key)
                unique_zones.append(z)

        return unique_zones[:n_recent]

    def price_at_level(
        self,
        zone: FibonacciZone,
        ratio: float,
    ) -> Optional[float]:
        """Gibt den Preis bei einem bestimmten Ratio zurück."""
        for lvl in zone.retracement_levels + zone.extension_levels:
            if abs(lvl.ratio - ratio) < 1e-6:
                return lvl.price
        return None

    def is_near_level(
        self,
        price: float,
        zone: FibonacciZone,
        tolerance: Optional[float] = None,
    ) -> Optional[FibLevel]:
        """Prüft ob Preis nahe einem Fib-Level liegt."""
        tol = tolerance if tolerance is not None else self.confluence_tolerance
        return zone.closest_level(price, tolerance=tol, include_extensions=True)
