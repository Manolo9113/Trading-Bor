"""Client fuer die MB-AktienScreener-API (MB-AktienScreener-Railway).

Verfuegbare Endpoints:
  GET /screener/tradeable  -> Daytrading-Watchlist (Volumen, Beta, Score)
  GET /screener/quality    -> Fundamentale Qualitaets-Picks
  GET /screener/value      -> Value-Picks (KGV, KBV, FCF-Yield)
  GET /signals             -> Makro-Regime + kombinierte Top-Picks
  GET /score/{ticker}      -> Einzel-Analyse eines Tickers
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Optional

import requests


@dataclass
class WatchlistEntry:
    """Ein handelbarer Titel aus dem Tradeable-Screener."""
    ticker: str
    name: str
    price: float
    score: float
    volume_m: float
    beta: float
    # ATR% wird aus Beta geschaetzt: atr_pct ≈ beta * 0.9 (Markt-ATR ~0.9%/Tag)
    atr_pct: float = 0.0
    rel_volume: Optional[float] = None
    mktcap_b: float = 0.0
    sector: str = ""
    typ: str = "Aktie"

    def __post_init__(self) -> None:
        if self.atr_pct == 0.0 and self.beta > 0:
            self.atr_pct = round(self.beta * 0.9, 2)

    def __str__(self) -> str:
        rv = f"RelVol={self.rel_volume:.2f}x" if self.rel_volume else ""
        return (
            f"{self.ticker:<6} | Score={self.score:>3} "
            f"| ATR~{self.atr_pct:.1f}% "
            f"| Vol={self.volume_m:.1f}M "
            f"| Beta={self.beta:.2f} "
            f"| ${self.price:.2f} {rv}"
        )


@dataclass
class ScreenerPick:
    """Ein Titel aus dem Quality- oder Value-Screener."""
    ticker: str
    name: str
    price: float
    score: float
    sector: str = ""
    mktcap_b: float = 0.0
    # Quality-Felder
    fair_value: Optional[float] = None
    discount_pct: Optional[float] = None
    # Value-Felder
    pe: Optional[float] = None
    pb: Optional[float] = None
    div_yield: Optional[float] = None
    ev_ebitda: Optional[float] = None
    fcf_yield: Optional[float] = None
    extra: dict = field(default_factory=dict)

    def __str__(self) -> str:
        parts = [f"{self.ticker:<6} | Score={self.score:>3} | ${self.price:.2f}"]
        if self.fair_value:
            parts.append(f"FV=${self.fair_value:.2f} ({self.discount_pct:+.1f}%)")
        if self.pe:
            parts.append(f"KGV={self.pe:.1f}")
        if self.div_yield:
            parts.append(f"Div={self.div_yield:.2f}%")
        return " | ".join(parts)


class ScreenerClient:
    """Verbindet den Trading-Bot mit der MB-AktienScreener-Railway-API."""

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
        """Prueft ob die Railway-API erreichbar ist."""
        try:
            r = self._session.get(f"{self.base_url}/health", timeout=5)
            return r.status_code == 200
        except Exception:
            return False

    # ------------------------------------------------------------------
    # Daytrading-Watchlist  (/screener/tradeable)
    # ------------------------------------------------------------------

    def get_daytrading_watchlist(
        self,
        top_n: int = 15,
        min_score: int = 50,
        min_atr_pct: float = 1.5,
        min_volume_m: float = 5.0,
    ) -> list[WatchlistEntry]:
        """Holt handelbare Aktien vom /screener/tradeable Endpoint.

        Da der Screener kein ATR liefert, wird atr_pct aus Beta geschaetzt
        (atr_pct ≈ beta * 0.9). Filter min_atr_pct wirkt auf diesen Schaetzwert.

        Args:
            top_n:         Anzahl Ergebnisse (max 30).
            min_score:     Mindest-Tradeable-Score (0-100).
            min_atr_pct:   Mindest-ATR% (geschaetzt aus Beta).
            min_volume_m:  Mindest-Volumen in Millionen/Tag.
        """
        url = f"{self.base_url}/screener/tradeable"
        params = {"top_n": min(top_n * 2, 30)}  # mehr holen, dann lokal filtern
        try:
            resp = self._session.get(url, params=params, timeout=self.timeout)
            resp.raise_for_status()
            data = resp.json()
        except requests.RequestException as exc:
            self._logger.error(f"Screener /tradeable nicht erreichbar: {exc}")
            return []
        except Exception as exc:
            self._logger.error(f"Unerwarteter Fehler: {exc}")
            return []

        entries: list[WatchlistEntry] = []
        for pick in data.get("picks", []):
            try:
                entry = WatchlistEntry(
                    ticker=pick["ticker"],
                    name=pick.get("name", pick["ticker"]),
                    price=float(pick["price"]),
                    score=float(pick["score"]),
                    volume_m=float(pick["volume_m"]),
                    beta=float(pick.get("beta", 1.0)),
                    mktcap_b=float(pick.get("mktcap_b", 0)),
                    sector=pick.get("sector", ""),
                )
            except (KeyError, TypeError, ValueError) as exc:
                self._logger.warning(
                    f"Eintrag uebersprungen ({pick.get('ticker', '?')}): {exc}"
                )
                continue

            if entry.score < min_score:
                continue
            if entry.volume_m < min_volume_m:
                continue
            if entry.atr_pct < min_atr_pct:
                continue
            entries.append(entry)

        entries = entries[:top_n]
        self._logger.info(
            f"Tradeable-Watchlist: {len(entries)} Titel "
            f"(min_score={min_score}, min_atr~{min_atr_pct}%, min_vol={min_volume_m}M)"
        )
        return entries

    # ------------------------------------------------------------------
    # Quality-Picks  (/screener/quality)
    # ------------------------------------------------------------------

    def get_quality_picks(
        self,
        top_n: int = 5,
        min_score: int = 65,
    ) -> list[ScreenerPick]:
        """Fundamentale Qualitaets-Aktien mit Discount zum Fair Value."""
        return self._fetch_picks(
            endpoint="/screener/quality",
            params={"top_n": top_n, "min_score": min_score},
            label="Quality",
        )

    # ------------------------------------------------------------------
    # Value-Picks  (/screener/value)
    # ------------------------------------------------------------------

    def get_value_picks(
        self,
        top_n: int = 10,
        min_score: int = 55,
    ) -> list[ScreenerPick]:
        """Value-Aktien nach KGV, KBV, EV/EBITDA, FCF-Yield."""
        return self._fetch_picks(
            endpoint="/screener/value",
            params={"top_n": top_n, "min_score": min_score},
            label="Value",
        )

    def _fetch_picks(
        self, endpoint: str, params: dict, label: str
    ) -> list[ScreenerPick]:
        try:
            resp = self._session.get(
                f"{self.base_url}{endpoint}", params=params, timeout=self.timeout
            )
            resp.raise_for_status()
            data = resp.json()
        except requests.RequestException as exc:
            self._logger.error(f"Screener {endpoint} nicht erreichbar: {exc}")
            return []
        except Exception as exc:
            self._logger.error(f"Unerwarteter Fehler ({endpoint}): {exc}")
            return []

        picks: list[ScreenerPick] = []
        for p in data.get("picks", []):
            try:
                picks.append(ScreenerPick(
                    ticker=p["ticker"],
                    name=p.get("name", p["ticker"]),
                    price=float(p["price"]),
                    score=float(p["score"]),
                    sector=p.get("sector", ""),
                    mktcap_b=float(p.get("mktcap_b", 0)),
                    fair_value=p.get("fair_value"),
                    discount_pct=p.get("discount_pct"),
                    pe=p.get("pe"),
                    pb=p.get("pb"),
                    div_yield=p.get("div_yield"),
                    ev_ebitda=p.get("ev_ebitda"),
                    fcf_yield=p.get("fcf_yield"),
                ))
            except (KeyError, TypeError, ValueError) as exc:
                self._logger.warning(
                    f"{label}-Eintrag uebersprungen ({p.get('ticker', '?')}): {exc}"
                )

        self._logger.info(f"{label}-Picks geladen: {len(picks)} Titel")
        return picks

    # ------------------------------------------------------------------
    # Gist-basierte Watchlist  (Alternative zur REST-API)
    # ------------------------------------------------------------------

    def get_watchlist_from_gist(
        self,
        gist_id: str,
        min_score: int = 50,
        min_atr_pct: float = 1.5,
        min_volume_m: float = 5.0,
        top_n: int = 15,
    ) -> list[WatchlistEntry]:
        """Liest die Daytrading-Watchlist aus einem GitHub Gist.

        Das Gist wird stündlich von update_gist.py (MB-AktienScreener-Railway)
        befüllt und enthält vorberechnete ATR%-Werte.

        Args:
            gist_id:      GitHub Gist-ID (aus GIST_ID Env-Variable).
            min_score:    Mindest-Score (0-100).
            min_atr_pct:  Mindest-ATR%.
            min_volume_m: Mindest-Volumen in Mio./Tag.
            top_n:        Maximale Anzahl Ergebnisse.
        """
        url = f"https://api.github.com/gists/{gist_id}"
        headers = {}
        if self.api_key:
            headers["Authorization"] = f"token {self.api_key}"

        try:
            resp = self._session.get(url, headers=headers, timeout=self.timeout)
            resp.raise_for_status()
            files = resp.json().get("files", {})
            content_file = next(
                (f for f in files.values() if f["filename"].endswith(".json")),
                None,
            )
            if not content_file:
                self._logger.error("Kein JSON-File im Gist gefunden.")
                return []
            raw_url = content_file["raw_url"]
            data = self._session.get(raw_url, timeout=self.timeout).json()
        except requests.RequestException as exc:
            self._logger.error(f"Gist-Abruf fehlgeschlagen: {exc}")
            return []
        except Exception as exc:
            self._logger.error(f"Gist-Parsing Fehler: {exc}")
            return []

        updated = data.get("updated", "unbekannt")
        self._logger.info(f"Gist-Daten vom: {updated}")

        entries: list[WatchlistEntry] = []
        for pick in data.get("daytrading_picks", []):
            try:
                entry = WatchlistEntry(
                    ticker=pick["ticker"],
                    name=pick.get("name", pick["ticker"]),
                    price=float(pick["price"]),
                    score=float(pick["score"]),
                    volume_m=float(pick["volume_m"]),
                    beta=float(pick.get("beta", 1.0)),
                    atr_pct=float(pick.get("atr_pct", 0.0)),
                    mktcap_b=float(pick.get("mktcap_b", 0)),
                    sector=pick.get("sector", ""),
                    typ=pick.get("typ", "Aktie"),
                )
            except (KeyError, TypeError, ValueError) as exc:
                self._logger.warning(
                    f"Gist-Eintrag uebersprungen ({pick.get('ticker', '?')}): {exc}"
                )
                continue

            if entry.score < min_score:
                continue
            if entry.volume_m < min_volume_m:
                continue
            if entry.atr_pct < min_atr_pct:
                continue
            entries.append(entry)

        entries = entries[:top_n]
        self._logger.info(
            f"Gist-Watchlist: {len(entries)} Titel "
            f"(Stand: {updated})"
        )
        return entries

    def get_quality_picks_from_gist(self, gist_id: str) -> list[ScreenerPick]:
        """Liest Quality-Picks aus dem Gist (von update_gist.py befüllt)."""
        url = f"https://api.github.com/gists/{gist_id}"
        headers = {"Authorization": f"token {self.api_key}"} if self.api_key else {}
        try:
            resp = self._session.get(url, headers=headers, timeout=self.timeout)
            resp.raise_for_status()
            files = resp.json().get("files", {})
            content_file = next(
                (f for f in files.values() if f["filename"].endswith(".json")), None
            )
            if not content_file:
                return []
            data = self._session.get(content_file["raw_url"], timeout=self.timeout).json()
        except Exception as exc:
            self._logger.error(f"Gist Quality-Picks Fehler: {exc}")
            return []

        picks: list[ScreenerPick] = []
        for p in data.get("quality_picks", []):
            try:
                picks.append(ScreenerPick(
                    ticker=p["ticker"],
                    name=p.get("name", p["ticker"]),
                    price=float(p["price"]),
                    score=float(p["score"]),
                    sector=p.get("sector", ""),
                    mktcap_b=float(p.get("mktcap_b", 0)),
                    fair_value=p.get("fair_value"),
                    discount_pct=p.get("discount_pct"),
                ))
            except (KeyError, TypeError, ValueError) as exc:
                self._logger.warning(f"Gist Quality-Eintrag uebersprungen: {exc}")
        return picks

    # ------------------------------------------------------------------
    # Makro-Signale  (/signals)
    # ------------------------------------------------------------------

    def get_signals(self) -> dict:
        """Makro-Regime (Risk-On/Off) + kombinierte Top-Picks."""
        try:
            resp = self._session.get(f"{self.base_url}/signals", timeout=self.timeout)
            resp.raise_for_status()
            return resp.json()
        except Exception as exc:
            self._logger.error(f"Signals-Abruf fehlgeschlagen: {exc}")
            return {}

    # ------------------------------------------------------------------
    # Einzel-Score  (/score/{ticker})
    # ------------------------------------------------------------------

    def get_score(self, ticker: str) -> dict:
        """Quality-, Value- und Tradeable-Score fuer einen einzelnen Ticker."""
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
        """Gibt die Tradeable-Watchlist formatiert in der Konsole aus."""
        if not entries:
            print("  [leer] Keine handelbaren Titel gefunden.")
            return
        print(f"\n{'='*65}")
        print(f"  DAYTRADING WATCHLIST  ({len(entries)} Titel)  [via /screener/tradeable]")
        print(f"{'='*65}")
        for i, e in enumerate(entries, 1):
            tag = f"[{e.typ[:3].upper()}]" if e.typ != "Aktie" else "     "
            print(f"  {i:>2}. {tag} {e}")
        print(f"{'='*65}\n")

    def print_picks(self, picks: list[ScreenerPick], title: str = "PICKS") -> None:
        """Gibt Quality- oder Value-Picks formatiert aus."""
        if not picks:
            print(f"  [leer] Keine {title}-Picks gefunden.")
            return
        print(f"\n{'='*65}")
        print(f"  {title}  ({len(picks)} Titel)")
        print(f"{'='*65}")
        for i, p in enumerate(picks, 1):
            print(f"  {i:>2}. {p}")
        print(f"{'='*65}\n")
