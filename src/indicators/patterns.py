"""Chart-Pattern-Erkennung.

Nutzt scipy.signal.argrelextrema für Swing-basierte Pattern
und Candlestick-Analyse für einzelne Kerzen-Pattern.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import numpy as np
import pandas as pd
from scipy.signal import argrelextrema


@dataclass
class PatternSignal:
    """Erkanntes Chart-Pattern."""
    name: str
    direction: str          # "bullish" | "bearish" | "neutral"
    strength: float         # 0.0 – 1.0
    bar_index: int
    description: str = ""


class PatternDetector:
    """Erkennt Chart-Patterns in OHLCV-Daten."""

    CANDLESTICK_PATTERNS = {
        "engulfing", "hammer", "shooting_star", "doji",
        "morning_star", "evening_star",
    }
    SWING_PATTERNS = {
        "double_top", "double_bottom", "head_and_shoulders",
        "inverse_head_and_shoulders",
    }

    def __init__(self, config: dict) -> None:
        self.enabled: set[str] = set(config.get("enabled", list(self.CANDLESTICK_PATTERNS)))
        self.swing_order: int = config.get("swing_order", 5)
        self.tolerance: float = config.get("tolerance", 0.02)  # 2%

    # ------------------------------------------------------------------
    # Haupt-Methode
    # ------------------------------------------------------------------

    def detect(self, df: pd.DataFrame) -> list[PatternSignal]:
        """Erkennt alle aktivierten Pattern im DataFrame.

        Args:
            df: OHLCV DataFrame. Benötigt mind. 20 Kerzen.

        Returns:
            Liste der erkannten PatternSignal-Objekte (neueste zuerst).
        """
        signals: list[PatternSignal] = []

        if len(df) < 5:
            return signals

        # Candlestick-Pattern (letzte 3 Kerzen)
        if "engulfing" in self.enabled:
            sig = self._detect_engulfing(df)
            if sig:
                signals.append(sig)

        if "hammer" in self.enabled:
            sig = self._detect_hammer(df)
            if sig:
                signals.append(sig)

        if "shooting_star" in self.enabled:
            sig = self._detect_shooting_star(df)
            if sig:
                signals.append(sig)

        if "doji" in self.enabled:
            sig = self._detect_doji(df)
            if sig:
                signals.append(sig)

        # Swing-Pattern (brauchen mehr Kerzen)
        if len(df) >= 20:
            if "double_top" in self.enabled:
                sig = self._detect_double_top(df)
                if sig:
                    signals.append(sig)

            if "double_bottom" in self.enabled:
                sig = self._detect_double_bottom(df)
                if sig:
                    signals.append(sig)

            if "head_and_shoulders" in self.enabled:
                sig = self._detect_head_and_shoulders(df)
                if sig:
                    signals.append(sig)

            if "inverse_head_and_shoulders" in self.enabled:
                sig = self._detect_inverse_head_and_shoulders(df)
                if sig:
                    signals.append(sig)

        return signals

    # ------------------------------------------------------------------
    # Candlestick-Pattern
    # ------------------------------------------------------------------

    def _detect_engulfing(self, df: pd.DataFrame) -> Optional[PatternSignal]:
        """Bullish oder Bearish Engulfing Candle."""
        if len(df) < 2:
            return None
        prev = df.iloc[-2]
        curr = df.iloc[-1]
        idx = len(df) - 1

        prev_body = abs(prev["close"] - prev["open"])
        curr_body = abs(curr["close"] - curr["open"])

        if curr_body < prev_body * 1.1:
            return None

        # Bullish: vorherige Kerze rot, aktuelle grün und umhüllt
        if (
            prev["close"] < prev["open"]
            and curr["close"] > curr["open"]
            and curr["open"] <= prev["close"]
            and curr["close"] >= prev["open"]
        ):
            strength = min(1.0, curr_body / prev_body - 1.0)
            return PatternSignal(
                name="engulfing",
                direction="bullish",
                strength=round(strength, 2),
                bar_index=idx,
                description="Bullish Engulfing",
            )

        # Bearish: vorherige Kerze grün, aktuelle rot und umhüllt
        if (
            prev["close"] > prev["open"]
            and curr["close"] < curr["open"]
            and curr["open"] >= prev["close"]
            and curr["close"] <= prev["open"]
        ):
            strength = min(1.0, curr_body / prev_body - 1.0)
            return PatternSignal(
                name="engulfing",
                direction="bearish",
                strength=round(strength, 2),
                bar_index=idx,
                description="Bearish Engulfing",
            )

        return None

    def _detect_hammer(self, df: pd.DataFrame) -> Optional[PatternSignal]:
        """Hammer (bullishes Umkehrmuster)."""
        c = df.iloc[-1]
        idx = len(df) - 1
        body = abs(c["close"] - c["open"])
        total_range = c["high"] - c["low"]
        if total_range == 0 or body == 0:
            return None

        lower_wick = min(c["open"], c["close"]) - c["low"]
        upper_wick = c["high"] - max(c["open"], c["close"])

        # Hammer: langer unterer Docht, kleiner Körper, kurzer oberer Docht
        if (
            lower_wick >= body * 2.0
            and upper_wick <= body * 0.5
            and body / total_range >= 0.1
        ):
            strength = min(1.0, lower_wick / total_range)
            return PatternSignal(
                name="hammer",
                direction="bullish",
                strength=round(strength, 2),
                bar_index=idx,
                description="Hammer",
            )
        return None

    def _detect_shooting_star(self, df: pd.DataFrame) -> Optional[PatternSignal]:
        """Shooting Star (bearishes Umkehrmuster)."""
        c = df.iloc[-1]
        idx = len(df) - 1
        body = abs(c["close"] - c["open"])
        total_range = c["high"] - c["low"]
        if total_range == 0 or body == 0:
            return None

        upper_wick = c["high"] - max(c["open"], c["close"])
        lower_wick = min(c["open"], c["close"]) - c["low"]

        if (
            upper_wick >= body * 2.0
            and lower_wick <= body * 0.5
            and body / total_range >= 0.1
        ):
            strength = min(1.0, upper_wick / total_range)
            return PatternSignal(
                name="shooting_star",
                direction="bearish",
                strength=round(strength, 2),
                bar_index=idx,
                description="Shooting Star",
            )
        return None

    def _detect_doji(self, df: pd.DataFrame) -> Optional[PatternSignal]:
        """Doji (Unentschlossenheit)."""
        c = df.iloc[-1]
        idx = len(df) - 1
        body = abs(c["close"] - c["open"])
        total_range = c["high"] - c["low"]
        if total_range == 0:
            return None
        if body / total_range < 0.05:
            return PatternSignal(
                name="doji",
                direction="neutral",
                strength=0.5,
                bar_index=idx,
                description="Doji",
            )
        return None

    # ------------------------------------------------------------------
    # Swing-Pattern
    # ------------------------------------------------------------------

    def _get_swing_highs_lows(
        self, df: pd.DataFrame
    ) -> tuple[np.ndarray, np.ndarray]:
        highs = argrelextrema(df["high"].values, np.greater_equal, order=self.swing_order)[0]
        lows = argrelextrema(df["low"].values, np.less_equal, order=self.swing_order)[0]
        return highs, lows

    def _detect_double_top(self, df: pd.DataFrame) -> Optional[PatternSignal]:
        """Double Top: zwei ähnlich hohe Swings mit Tief dazwischen."""
        highs, _ = self._get_swing_highs_lows(df)
        if len(highs) < 2:
            return None

        last = highs[-1]
        prev = highs[-2]
        h1 = df["high"].iloc[prev]
        h2 = df["high"].iloc[last]

        # Beide Hochs müssen ähnlich sein
        if abs(h1 - h2) / h1 > self.tolerance:
            return None

        # Tief muss zwischen den Hochs liegen
        valley = df["low"].iloc[prev:last].min()
        if valley >= min(h1, h2) * 0.98:
            return None

        strength = 1.0 - abs(h1 - h2) / h1 / self.tolerance
        return PatternSignal(
            name="double_top",
            direction="bearish",
            strength=round(min(1.0, strength), 2),
            bar_index=last,
            description=f"Double Top @ {h1:.4f} / {h2:.4f}",
        )

    def _detect_double_bottom(self, df: pd.DataFrame) -> Optional[PatternSignal]:
        """Double Bottom: zwei ähnlich tiefe Swings mit Hoch dazwischen."""
        _, lows = self._get_swing_highs_lows(df)
        if len(lows) < 2:
            return None

        last = lows[-1]
        prev = lows[-2]
        l1 = df["low"].iloc[prev]
        l2 = df["low"].iloc[last]

        if abs(l1 - l2) / l1 > self.tolerance:
            return None

        peak = df["high"].iloc[prev:last].max()
        if peak <= max(l1, l2) * 1.02:
            return None

        strength = 1.0 - abs(l1 - l2) / l1 / self.tolerance
        return PatternSignal(
            name="double_bottom",
            direction="bullish",
            strength=round(min(1.0, strength), 2),
            bar_index=last,
            description=f"Double Bottom @ {l1:.4f} / {l2:.4f}",
        )

    def _detect_head_and_shoulders(self, df: pd.DataFrame) -> Optional[PatternSignal]:
        """Head & Shoulders (bearishes Umkehrmuster)."""
        highs, _ = self._get_swing_highs_lows(df)
        if len(highs) < 3:
            return None

        r_shoulder_idx = highs[-1]
        head_idx = highs[-2]
        l_shoulder_idx = highs[-3]

        head = df["high"].iloc[head_idx]
        l_sh = df["high"].iloc[l_shoulder_idx]
        r_sh = df["high"].iloc[r_shoulder_idx]

        # Kopf muss höher als beide Schultern sein
        if not (head > l_sh and head > r_sh):
            return None

        # Schultern müssen ähnlich hoch sein
        if abs(l_sh - r_sh) / l_sh > self.tolerance * 2:
            return None

        strength = (head - max(l_sh, r_sh)) / head
        return PatternSignal(
            name="head_and_shoulders",
            direction="bearish",
            strength=round(min(1.0, strength * 5), 2),
            bar_index=r_shoulder_idx,
            description=f"H&S: LS={l_sh:.4f} H={head:.4f} RS={r_sh:.4f}",
        )

    def _detect_inverse_head_and_shoulders(
        self, df: pd.DataFrame
    ) -> Optional[PatternSignal]:
        """Inverse Head & Shoulders (bullishes Umkehrmuster)."""
        _, lows = self._get_swing_highs_lows(df)
        if len(lows) < 3:
            return None

        r_shoulder_idx = lows[-1]
        head_idx = lows[-2]
        l_shoulder_idx = lows[-3]

        head = df["low"].iloc[head_idx]
        l_sh = df["low"].iloc[l_shoulder_idx]
        r_sh = df["low"].iloc[r_shoulder_idx]

        if not (head < l_sh and head < r_sh):
            return None

        if abs(l_sh - r_sh) / l_sh > self.tolerance * 2:
            return None

        strength = (min(l_sh, r_sh) - head) / min(l_sh, r_sh)
        return PatternSignal(
            name="inverse_head_and_shoulders",
            direction="bullish",
            strength=round(min(1.0, strength * 5), 2),
            bar_index=r_shoulder_idx,
            description=f"IH&S: LS={l_sh:.4f} H={head:.4f} RS={r_sh:.4f}",
        )
