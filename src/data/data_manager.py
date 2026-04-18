"""DataManager: OHLCV-Daten laden, cachen und bereinigen.

Speichert Daten lokal als Parquet (schnell) oder CSV (kompatibel).
Vermeidet wiederholte API-Calls beim Backtesting.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

import pandas as pd


class DataManager:
    """Laedt OHLCV-Daten vom Exchange und cacht sie lokal."""

    def __init__(self, data_dir: str = "data") -> None:
        self._dir = Path(data_dir)
        self._dir.mkdir(parents=True, exist_ok=True)
        self._logger = logging.getLogger(self.__class__.__name__)

    # ------------------------------------------------------------------
    # Oeffentliche Methoden
    # ------------------------------------------------------------------

    def load(
        self,
        connector,
        symbol: str,
        timeframe: str,
        start: str,
        end: str,
        force_reload: bool = False,
    ) -> Optional[pd.DataFrame]:
        """Gibt OHLCV-Daten zurueck – aus Cache oder vom Exchange.

        Args:
            connector: ExchangeConnector-Instanz.
            symbol:    z.B. "BTC/USDT".
            timeframe: z.B. "1h".
            start:     ISO-Datum "2023-01-01".
            end:       ISO-Datum "2024-12-31".
            force_reload: Cache ignorieren und neu laden.

        Returns:
            DataFrame mit DatetimeIndex oder None bei Fehler.
        """
        cache_path = self._cache_path(symbol, timeframe, start, end)

        if not force_reload and cache_path.exists():
            self._logger.info(f"Cache treffer: {cache_path.name}")
            return self._read(cache_path)

        self._logger.info(f"Lade Daten vom Exchange: {symbol} {timeframe} {start}-{end}")
        df = connector.fetch_ohlcv_history(
            symbol=symbol, timeframe=timeframe, start=start, end=end
        )
        if df is None or df.empty:
            self._logger.error("Keine Daten erhalten.")
            return None

        df = self._clean(df)
        self._write(df, cache_path)
        self._logger.info(f"Gespeichert: {cache_path.name} ({len(df)} Kerzen)")
        return df

    def list_cached(self) -> list[str]:
        """Listet alle gecachten Dateien auf."""
        return [p.name for p in self._dir.glob("*.parquet")]

    def delete_cache(self, symbol: str, timeframe: str, start: str, end: str) -> bool:
        path = self._cache_path(symbol, timeframe, start, end)
        if path.exists():
            path.unlink()
            self._logger.info(f"Cache geloescht: {path.name}")
            return True
        return False

    # ------------------------------------------------------------------
    # Interne Hilfsmethoden
    # ------------------------------------------------------------------

    def _cache_path(self, symbol: str, timeframe: str, start: str, end: str) -> Path:
        safe_symbol = symbol.replace("/", "-")
        return self._dir / f"{safe_symbol}_{timeframe}_{start}_{end}.parquet"

    @staticmethod
    def _clean(df: pd.DataFrame) -> pd.DataFrame:
        """Entfernt Duplikate, sortiert und fuellt kleine Luecken."""
        df = df[~df.index.duplicated(keep="last")]
        df = df.sort_index()
        df = df.ffill(limit=3)  # Kleine Luecken (z.B. Wartung) fuellen
        df = df.dropna()
        return df

    @staticmethod
    def _write(df: pd.DataFrame, path: Path) -> None:
        try:
            df.to_parquet(path)
        except Exception:
            df.to_csv(path.with_suffix(".csv"))

    @staticmethod
    def _read(path: Path) -> Optional[pd.DataFrame]:
        try:
            if path.suffix == ".parquet":
                return pd.read_parquet(path)
            return pd.read_csv(path, index_col=0, parse_dates=True)
        except Exception:
            return None
