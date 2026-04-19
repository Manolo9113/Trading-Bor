"""Client fuer die MB-AktienScreener-API.

Holt morgens die Daytrading-Watchlist und bereitet sie
als strukturierte WatchlistEntry-Objekte auf.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Optional

import requests


@dataclass
class WatchlistEntry:
    """Ein Eintrag aus der Daytrading-Watchlist."""
    ticker: str
    name: str
    price: float
    score: float
    atr_pct: float
    volume_m: float
    beta: float
    rel_volume: Optional[float] = None
    mktcap_b: float = 0.0
    sector: str = ""
    typ: str = "Aktie"  # "Aktie" | "ETF" | "ETF (Leveraged)"

    def __str__(self) -> str:
        rv = f"RelVol={self.rel_volume:.2f}x" if self.rel_volume else ""
        return (
            f"{self.ticker:<6} | Score={self.score:>3} "
            f"| ATR={self.atr_pct:.1f}% "
            f"| Vol={self.volume_m:.1f}M "
            f"| Beta={self.beta:.2f} "
            f"| ${self.price:.2f} {rv}"
        )


class ScreenerClient:
    """Verbindet den Trading-Bot mit der MB-AktienScreener-API."""

    def __init__(self, base_url: str, api_key: str = "", timeout: int = 30) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.timeout = timeout
        self._logger = logging.getLogger(self.__class__.__name__)
        self._session = requests.Session()
        if api_key:
            self._session.headers["X-API-Key"] = api_key

    # ------------------------------------------------------------------
    # Health
    # ------------------------------------------------------------------

    def is_online(self) -> bool:
        """Prueft ob die API erreichbar ist."""
        try:
            r = self._session.get(f"{self.base_url}/health", timeout=5)
            return r.status_code == 200
        except Exception:
            return False

    # ------------------------------------------------------------------
    # Daytrading-Watchlist
    # ------------------------------------------------------------------

    def get_daytrading_watchlist(
        self,
        top_n: int = 15,
        min_score: int = 50,
        min_atr_pct: float = 1.5,
        min_volume_m: float = 5.0,
    ) -> list[WatchlistEntry]:
        """Holt die Daytrading-Watchlist vom Screener.

        Args:
            top_n:         Anzahl Ergebnisse (max 40).
            min_score:     Mindest-Daytrading-Score (0-100).
            min_atr_pct:   Mindest-ATR% (taegl. Bewegung).
            min_volume_m:  Mindest-Volumen in Millionen/Tag.

        Returns:
            Liste von WatchlistEntry, sortiert nach Score.
        """
        url = f"{self.base_url}/screener/daytrading"
        params = {
            "top_n": top_n,
            "min_score": min_score,
            "min_atr_pct": min_atr_pct,
            "min_volume_m": min_volume_m,
        }
        try:
            resp = self._session.get(url, params=params, timeout=self.timeout)
            resp.raise_for_status()
            data = resp.json()
        except requests.RequestException as exc:
            self._logger.error(f"Screener-API nicht erreichbar: {exc}")
            return []
        except Exception as exc:
            self._logger.error(f"Unerwarteter Fehler: {exc}")
            return []

        entries = []
        for pick in data.get("picks", []):
            try:
                entries.append(WatchlistEntry(
                    ticker=pick["ticker"],
                    name=pick.get("name", pick["ticker"]),
                    price=float(pick.get("price", 0)),
                    score=float(pick.get("score", 0)),
                    atr_pct=float(pick.get("atr_pct") or 0),
                    volume_m=float(pick.get("volume_m", 0)),
                    beta=float(pick.get("beta", 1.0)),
                    rel_volume=pick.get("rel_volume"),
                    mktcap_b=float(pick.get("mktcap_b", 0)),
                    sector=pick.get("sector", ""),
                    typ=pick.get("typ", "Aktie"),
                ))
            except (KeyError, TypeError, ValueError) as exc:
                self._logger.warning(f"Eintrag uebersprungen ({pick.get('ticker', '?')}): {exc}")

        self._logger.info(
            f"Watchlist geladen: {len(entries)} Titel "
            f"(min_score={min_score}, min_atr={min_atr_pct}%)"
        )
        return entries

    # ------------------------------------------------------------------
    # Makro-Signale
    # ------------------------------------------------------------------

    def get_signals(self) -> dict:
        """Holt das kombinierte Makro-Signal (Regime + Top-Picks)."""
        try:
            resp = self._session.get(f"{self.base_url}/signals", timeout=self.timeout)
            resp.raise_for_status()
            return resp.json()
        except Exception as exc:
            self._logger.error(f"Signals-Abruf fehlgeschlagen: {exc}")
            return {}

    # ------------------------------------------------------------------
    # Einzel-Score
    # ------------------------------------------------------------------

    def get_score(self, ticker: str) -> dict:
        """Holt alle Scores fuer einen einzelnen Ticker."""
        try:
            resp = self._session.get(
                f"{self.base_url}/score/{ticker.upper()}",
                timeout=self.timeout,
            )
            resp.raise_for_status()
            return resp.json()
        except Exception as exc:
            self._logger.error(f"Score fuer {ticker} fehlgeschlagen: {exc}")
            return {}

    # ------------------------------------------------------------------
    # Formatierte Ausgabe
    # ------------------------------------------------------------------

    def print_watchlist(self, entries: list[WatchlistEntry]) -> None:
        """Gibt die Watchlist formatiert in der Konsole aus."""
        if not entries:
            print("  [leer] Keine Titel gefunden.")
            return
        print(f"\n{'='*65}")
        print(f"  DAYTRADING WATCHLIST  ({len(entries)} Titel)")
        print(f"{'='*65}")
        for i, e in enumerate(entries, 1):
            tag = f"[{e.typ[:3].upper()}]" if e.typ != "Aktie" else "     "
            print(f"  {i:>2}. {tag} {e}")
        print(f"{'='*65}\n")
