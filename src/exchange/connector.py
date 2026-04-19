"""CCXT-basierter Exchange-Connector.

Unterstuetzt Live-Trading und historische Daten fuer Backtests.
API-Keys koennen via config oder Umgebungsvariablen gesetzt werden.
"""

from __future__ import annotations

import logging
import os
from typing import Optional

import pandas as pd

try:
    import ccxt
    CCXT_AVAILABLE = True
except ImportError:
    CCXT_AVAILABLE = False

from ..strategies.base_strategy import Signal, SignalType


class ExchangeConnector:
    """Verbindet den Bot mit einem CCXT-kompatiblen Exchange."""

    OHLCV_COLUMNS = ["timestamp", "open", "high", "low", "close", "volume"]

    def __init__(self, config: dict) -> None:
        self._logger = logging.getLogger(self.__class__.__name__)
        self.sandbox: bool = config.get("sandbox", True)
        self.exchange_name: str = config.get("name", "binance")
        api_key = config.get("api_key") or os.getenv("EXCHANGE_API_KEY", "")
        secret = config.get("secret") or os.getenv("EXCHANGE_SECRET", "")

        if not CCXT_AVAILABLE:
            self._logger.warning("ccxt nicht installiert. Nur Dummy-Modus verfuegbar.")
            self._exchange = None
            return

        exchange_class = getattr(ccxt, self.exchange_name, None)
        if exchange_class is None:
            raise ValueError(f"Unbekannter Exchange: {self.exchange_name}")

        self._exchange = exchange_class({
            "apiKey": api_key,
            "secret": secret,
            "enableRateLimit": True,
        })

        if self.sandbox:
            self._exchange.set_sandbox_mode(True)
            self._logger.info(f"{self.exchange_name} Sandbox-Modus aktiv")
        else:
            self._logger.warning(f"{self.exchange_name} LIVE-Modus aktiv!")

    # ------------------------------------------------------------------
    # Daten
    # ------------------------------------------------------------------

    def fetch_ohlcv(
        self,
        symbol: str,
        timeframe: str = "1h",
        limit: int = 200,
    ) -> Optional[pd.DataFrame]:
        """Holt aktuelle OHLCV-Daten vom Exchange."""
        if self._exchange is None:
            return self._dummy_ohlcv(limit)
        try:
            raw = self._exchange.fetch_ohlcv(symbol, timeframe, limit=limit)
            return self._to_dataframe(raw)
        except Exception as exc:
            self._logger.error(f"fetch_ohlcv fehlgeschlagen: {exc}")
            return None

    def fetch_ohlcv_history(
        self,
        symbol: str,
        timeframe: str,
        start: str,
        end: str,
    ) -> Optional[pd.DataFrame]:
        """Holt historische OHLCV-Daten (fuer Backtests)."""
        if self._exchange is None:
            return self._dummy_ohlcv(5000)
        try:
            since = self._exchange.parse8601(f"{start}T00:00:00Z")
            end_ts = self._exchange.parse8601(f"{end}T23:59:59Z")
            all_candles = []
            while since < end_ts:
                candles = self._exchange.fetch_ohlcv(
                    symbol, timeframe, since=since, limit=1000
                )
                if not candles:
                    break
                all_candles.extend(candles)
                since = candles[-1][0] + 1
                self._logger.debug(f"Geladen bis {candles[-1][0]}")
            df = self._to_dataframe(all_candles)
            return df[df.index <= pd.Timestamp(end)]
        except Exception as exc:
            self._logger.error(f"fetch_ohlcv_history fehlgeschlagen: {exc}")
            return None

    def _to_dataframe(self, raw: list) -> pd.DataFrame:
        df = pd.DataFrame(raw, columns=self.OHLCV_COLUMNS)
        df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
        df.set_index("timestamp", inplace=True)
        return df.astype(float)

    def _dummy_ohlcv(self, n: int = 200) -> pd.DataFrame:
        """Erzeugt synthetische Daten wenn ccxt nicht verfuegbar ist."""
        import numpy as np
        dates = pd.date_range(end=pd.Timestamp.now(), periods=n, freq="1h")
        close = 30000 + np.cumsum(np.random.randn(n) * 100)
        df = pd.DataFrame(index=dates)
        df["open"] = close - np.abs(np.random.randn(n) * 50)
        df["high"] = close + np.abs(np.random.randn(n) * 80)
        df["low"] = close - np.abs(np.random.randn(n) * 80)
        df["close"] = close
        df["volume"] = np.abs(np.random.randn(n) * 1000 + 5000)
        return df

    # ------------------------------------------------------------------
    # Orders
    # ------------------------------------------------------------------

    def place_order(self, symbol: str, signal: Signal) -> Optional[dict]:
        """Sendet eine Order an den Exchange."""
        if self._exchange is None:
            self._logger.info(f"[DUMMY] Order: {signal.signal_type.value} {symbol} @ {signal.price}")
            return {"status": "dummy", "signal": signal.signal_type.value}
        try:
            side = "buy" if signal.signal_type == SignalType.BUY else "sell"
            order = self._exchange.create_market_order(
                symbol=symbol,
                side=side,
                amount=signal.size,
            )
            self._logger.info(f"Order ausgefuehrt: {order['id']} {side} {signal.size} {symbol}")
            return order
        except Exception as exc:
            self._logger.error(f"Order fehlgeschlagen: {exc}")
            return None
