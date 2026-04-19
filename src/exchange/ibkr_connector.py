"""Interactive Brokers Connector via ib_insync.

Verbindung zu TWS oder IB Gateway:
  - TWS Paper:    Host=127.0.0.1, Port=7497
  - TWS Live:     Host=127.0.0.1, Port=7496
  - Gateway Paper: Host=127.0.0.1, Port=4002
  - Gateway Live:  Host=127.0.0.1, Port=4001

Setup:
  1. TWS oder IB Gateway starten
  2. In TWS: File > Global Configuration > API > Settings
     - Enable ActiveX and Socket Clients
     - Trusted IP: 127.0.0.1
  3. API Keys in config.yaml eintragen (nicht noetig fuer IB)
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Optional

import pandas as pd

try:
    from ib_insync import IB, Stock, MarketOrder, LimitOrder, util
    IBKR_AVAILABLE = True
except ImportError:
    IBKR_AVAILABLE = False


class IBKRConnector:
    """Verbindet den Trading Bot mit Interactive Brokers via ib_insync."""

    TIMEFRAME_MAP = {
        "1m":  ("1 min",  "1 D"),
        "5m":  ("5 mins", "3 D"),
        "15m": ("15 mins", "7 D"),
        "1h":  ("1 hour", "30 D"),
        "4h":  ("4 hours", "60 D"),
        "1d":  ("1 day",  "1 Y"),
    }

    def __init__(self, config: dict) -> None:
        self._logger = logging.getLogger(self.__class__.__name__)
        self.host: str = config.get("host", "127.0.0.1")
        self.port: int = config.get("port", 7497)
        self.client_id: int = config.get("client_id", 1)
        self.paper: bool = config.get("paper", True)
        self.currency: str = config.get("currency", "USD")
        self.exchange: str = config.get("exchange", "SMART")
        self._ib: Optional[IB] = None

        if not IBKR_AVAILABLE:
            self._logger.warning(
                "ib_insync nicht installiert: pip install ib_insync\n"
                "Ausserdem wird TWS oder IB Gateway benoetigt."
            )
            return

        self._connect()

    def _connect(self) -> bool:
        """Verbindung zu TWS/Gateway herstellen."""
        try:
            self._ib = IB()
            self._ib.connect(
                host=self.host,
                port=self.port,
                clientId=self.client_id,
                readonly=False,
                timeout=10,
            )
            mode = "PAPER" if self.paper else "LIVE"
            self._logger.info(
                f"IBKR verbunden [{mode}] "
                f"{self.host}:{self.port} ClientId={self.client_id}"
            )
            return True
        except Exception as exc:
            self._logger.error(f"IBKR Verbindung fehlgeschlagen: {exc}")
            self._ib = None
            return False

    def disconnect(self) -> None:
        if self._ib and self._ib.isConnected():
            self._ib.disconnect()
            self._logger.info("IBKR Verbindung getrennt.")

    # ------------------------------------------------------------------
    # Konto
    # ------------------------------------------------------------------

    def get_account(self) -> dict:
        """Gibt Kontoinformationen zurueck."""
        if not self._ib:
            return {}
        try:
            summary = self._ib.accountSummary()
            result = {}
            for item in summary:
                if item.tag == "NetLiquidation":
                    result["equity"] = float(item.value)
                elif item.tag == "AvailableFunds":
                    result["buying_power"] = float(item.value)
                elif item.tag == "TotalCashValue":
                    result["cash"] = float(item.value)
                elif item.tag == "UnrealizedPnL":
                    result["unrealized_pnl"] = float(item.value)
                elif item.tag == "RealizedPnL":
                    result["realized_pnl"] = float(item.value)
            result["paper"] = self.paper
            return result
        except Exception as exc:
            self._logger.error(f"get_account: {exc}")
            return {}

    # ------------------------------------------------------------------
    # Positionen
    # ------------------------------------------------------------------

    def get_positions(self) -> list[dict]:
        """Gibt alle offenen Positionen zurueck."""
        if not self._ib:
            return []
        try:
            positions = self._ib.positions()
            return [
                {
                    "symbol":    pos.contract.symbol,
                    "qty":       float(pos.position),
                    "avg_cost":  float(pos.avgCost),
                    "pnl":       0.0,
                }
                for pos in positions
                if pos.position != 0
            ]
        except Exception as exc:
            self._logger.error(f"get_positions: {exc}")
            return []

    def close_position(self, symbol: str) -> Optional[dict]:
        """Schliesst eine einzelne Position (Market Order)."""
        if not self._ib:
            return None
        try:
            positions = self._ib.positions()
            for pos in positions:
                if pos.contract.symbol == symbol and pos.position != 0:
                    contract = Stock(symbol, self.exchange, self.currency)
                    self._ib.qualifyContracts(contract)
                    action = "SELL" if pos.position > 0 else "BUY"
                    order = MarketOrder(action, abs(pos.position))
                    trade = self._ib.placeOrder(contract, order)
                    self._ib.sleep(1)
                    self._logger.info(
                        f"Position geschlossen: {symbol} "
                        f"{action} {abs(pos.position)}"
                    )
                    return {"symbol": symbol, "status": str(trade.orderStatus.status)}
        except Exception as exc:
            self._logger.error(f"close_position {symbol}: {exc}")
        return None

    def close_all_positions(self) -> bool:
        """Schliesst alle offenen Positionen."""
        if not self._ib:
            return False
        try:
            positions = self._ib.positions()
            for pos in positions:
                if pos.position != 0:
                    self.close_position(pos.contract.symbol)
            self._logger.info("Alle Positionen geschlossen.")
            return True
        except Exception as exc:
            self._logger.error(f"close_all_positions: {exc}")
            return False

    # ------------------------------------------------------------------
    # Orders
    # ------------------------------------------------------------------

    def buy_market(self, symbol: str, qty: float) -> Optional[dict]:
        return self._place_market(symbol, qty, "BUY")

    def sell_market(self, symbol: str, qty: float) -> Optional[dict]:
        return self._place_market(symbol, qty, "SELL")

    def buy_limit(self, symbol: str, qty: float, limit_price: float) -> Optional[dict]:
        return self._place_limit(symbol, qty, limit_price, "BUY")

    def sell_limit(self, symbol: str, qty: float, limit_price: float) -> Optional[dict]:
        return self._place_limit(symbol, qty, limit_price, "SELL")

    def _place_market(self, symbol: str, qty: float, action: str) -> Optional[dict]:
        if not self._ib:
            self._logger.info(f"[DUMMY] Market {action} {qty}x {symbol}")
            return {"status": "dummy", "symbol": symbol}
        try:
            contract = Stock(symbol, self.exchange, self.currency)
            self._ib.qualifyContracts(contract)
            order = MarketOrder(action, qty)
            trade = self._ib.placeOrder(contract, order)
            self._ib.sleep(1)
            self._logger.info(
                f"{action} {qty}x {symbol} [Market] "
                f"Status: {trade.orderStatus.status}"
            )
            return {
                "id":     str(trade.order.orderId),
                "symbol": symbol,
                "qty":    qty,
                "action": action,
                "status": str(trade.orderStatus.status),
            }
        except Exception as exc:
            self._logger.error(f"Market Order {symbol}: {exc}")
            return None

    def _place_limit(self, symbol: str, qty: float, price: float,
                     action: str) -> Optional[dict]:
        if not self._ib:
            self._logger.info(f"[DUMMY] Limit {action} {qty}x {symbol} @ {price}")
            return {"status": "dummy", "symbol": symbol, "price": price}
        try:
            contract = Stock(symbol, self.exchange, self.currency)
            self._ib.qualifyContracts(contract)
            order = LimitOrder(action, qty, round(price, 2))
            trade = self._ib.placeOrder(contract, order)
            self._ib.sleep(1)
            self._logger.info(
                f"{action} {qty}x {symbol} @ ${price:.2f} [Limit] "
                f"Status: {trade.orderStatus.status}"
            )
            return {
                "id":     str(trade.order.orderId),
                "symbol": symbol,
                "qty":    qty,
                "price":  price,
                "action": action,
                "status": str(trade.orderStatus.status),
            }
        except Exception as exc:
            self._logger.error(f"Limit Order {symbol}: {exc}")
            return None

    # ------------------------------------------------------------------
    # Marktdaten
    # ------------------------------------------------------------------

    def fetch_ohlcv(
        self,
        symbol: str,
        timeframe: str = "1d",
        limit: int = 252,
    ) -> Optional[pd.DataFrame]:
        """Holt historische OHLCV-Daten."""
        if not self._ib:
            return self._dummy_ohlcv(limit)
        try:
            bar_size, duration = self.TIMEFRAME_MAP.get(timeframe, ("1 day", "1 Y"))
            contract = Stock(symbol, self.exchange, self.currency)
            self._ib.qualifyContracts(contract)
            bars = self._ib.reqHistoricalData(
                contract,
                endDateTime="",
                durationStr=duration,
                barSizeSetting=bar_size,
                whatToShow="TRADES",
                useRTH=True,
                formatDate=1,
            )
            if not bars:
                self._logger.warning(f"Keine Daten fuer {symbol}")
                return None
            df = util.df(bars)
            df = df.rename(columns={
                "date": "timestamp",
                "open": "open",
                "high": "high",
                "low": "low",
                "close": "close",
                "volume": "volume",
            })
            df["timestamp"] = pd.to_datetime(df["timestamp"])
            df = df.set_index("timestamp")
            return df[["open", "high", "low", "close", "volume"]].tail(limit)
        except Exception as exc:
            self._logger.error(f"fetch_ohlcv {symbol}: {exc}")
            return None

    def is_market_open(self) -> bool:
        """Prueft ob der Markt gerade offen ist."""
        if not self._ib:
            return False
        try:
            clock = datetime.now()
            # NYSE: Mo-Fr 09:30-16:00 ET (vereinfacht)
            if clock.weekday() >= 5:
                return False
            market_open = clock.replace(hour=9, minute=30, second=0)
            market_close = clock.replace(hour=16, minute=0, second=0)
            return market_open <= clock <= market_close
        except Exception:
            return False

    def time_to_open(self) -> float:
        """Sekunden bis zur Marktoeffnung (0 wenn bereits offen)."""
        now = datetime.now()
        if now.weekday() >= 5:
            days_ahead = 7 - now.weekday()
        else:
            days_ahead = 0
        open_time = (now + timedelta(days=days_ahead)).replace(
            hour=9, minute=30, second=0, microsecond=0
        )
        if open_time <= now:
            return 0.0
        return (open_time - now).total_seconds()

    @staticmethod
    def _dummy_ohlcv(n: int = 252) -> pd.DataFrame:
        import numpy as np
        dates = pd.date_range(end=pd.Timestamp.now(), periods=n, freq="1D")
        close = 150 + np.cumsum(np.random.randn(n) * 2)
        df = pd.DataFrame(index=dates)
        df["open"]   = close - abs(np.random.randn(n))
        df["high"]   = close + abs(np.random.randn(n) * 2)
        df["low"]    = close - abs(np.random.randn(n) * 2)
        df["close"]  = close
        df["volume"] = abs(np.random.randn(n) * 100000 + 500000)
        return df
