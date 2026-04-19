"""Alpaca-Connector fuer US-Aktien (Paper + Live Trading)."""

from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta
from typing import Optional

import pandas as pd

try:
    from alpaca.trading.client import TradingClient
    from alpaca.trading.requests import MarketOrderRequest, LimitOrderRequest
    from alpaca.trading.enums import OrderSide, TimeInForce
    from alpaca.data.historical import StockHistoricalDataClient
    from alpaca.data.requests import StockBarsRequest
    from alpaca.data.timeframe import TimeFrame, TimeFrameUnit
    ALPACA_AVAILABLE = True
except ImportError:
    ALPACA_AVAILABLE = False


class AlpacaConnector:
    """Verbindet den Bot mit Alpaca (Paper oder Live)."""

    def __init__(self, config: dict) -> None:
        self._logger = logging.getLogger(self.__class__.__name__)

        if not ALPACA_AVAILABLE:
            self._logger.warning("alpaca-py nicht installiert: pip install alpaca-py")
            self._trading = None
            self._data = None
            return

        api_key = config.get("api_key") or os.getenv("ALPACA_API_KEY", "")
        secret  = config.get("secret")  or os.getenv("ALPACA_SECRET_KEY", "")
        self.paper: bool = config.get("sandbox", True)

        if not api_key or not secret:
            self._logger.error("ALPACA_API_KEY oder ALPACA_SECRET_KEY fehlt.")
            self._trading = None
            self._data = None
            return

        self._trading = TradingClient(api_key=api_key, secret_key=secret, paper=self.paper)
        self._data    = StockHistoricalDataClient(api_key=api_key, secret_key=secret)
        self._logger.info(f"Alpaca verbunden [{'PAPER' if self.paper else 'LIVE'}]")

    # ------------------------------------------------------------------
    # Konto
    # ------------------------------------------------------------------

    def get_account(self) -> dict:
        if not self._trading:
            return {}
        try:
            acc = self._trading.get_account()
            return {
                "equity":       float(acc.equity),
                "cash":         float(acc.cash),
                "buying_power": float(acc.buying_power),
                "pnl_today":    float(acc.equity) - float(acc.last_equity),
                "paper":        self.paper,
            }
        except Exception as exc:
            self._logger.error(f"get_account: {exc}")
            return {}

    # ------------------------------------------------------------------
    # Positionen
    # ------------------------------------------------------------------

    def get_positions(self) -> list[dict]:
        if not self._trading:
            return []
        try:
            return [
                {
                    "symbol":    p.symbol,
                    "qty":       float(p.qty),
                    "side":      p.side.value,
                    "avg_entry": float(p.avg_entry_price),
                    "current":   float(p.current_price),
                    "pnl":       float(p.unrealized_pl),
                    "pnl_pct":   float(p.unrealized_plpc) * 100,
                }
                for p in self._trading.get_all_positions()
            ]
        except Exception as exc:
            self._logger.error(f"get_positions: {exc}")
            return []

    def close_position(self, symbol: str) -> bool:
        if not self._trading:
            return False
        try:
            self._trading.close_position(symbol)
            self._logger.info(f"Position geschlossen: {symbol}")
            return True
        except Exception as exc:
            self._logger.error(f"close_position {symbol}: {exc}")
            return False

    def close_all_positions(self) -> bool:
        if not self._trading:
            return False
        try:
            self._trading.close_all_positions(cancel_orders=True)
            self._logger.info("Alle Positionen geschlossen.")
            return True
        except Exception as exc:
            self._logger.error(f"close_all_positions: {exc}")
            return False

    # ------------------------------------------------------------------
    # Orders
    # ------------------------------------------------------------------

    def buy_market(self, symbol: str, qty: float) -> Optional[dict]:
        return self._place_market(symbol, qty, OrderSide.BUY)

    def sell_market(self, symbol: str, qty: float) -> Optional[dict]:
        return self._place_market(symbol, qty, OrderSide.SELL)

    def buy_limit(self, symbol: str, qty: float, limit_price: float) -> Optional[dict]:
        return self._place_limit(symbol, qty, limit_price, OrderSide.BUY)

    def sell_limit(self, symbol: str, qty: float, limit_price: float) -> Optional[dict]:
        return self._place_limit(symbol, qty, limit_price, OrderSide.SELL)

    def _place_market(self, symbol: str, qty: float, side) -> Optional[dict]:
        if not self._trading:
            self._logger.info(f"[DUMMY] Market {side.value} {qty}x {symbol}")
            return {"status": "dummy", "symbol": symbol}
        try:
            req = MarketOrderRequest(symbol=symbol, qty=qty, side=side,
                                     time_in_force=TimeInForce.DAY)
            order = self._trading.submit_order(req)
            self._logger.info(f"{side.value.upper()} {qty}x {symbol} [Market] {order.id}")
            return {"id": str(order.id), "symbol": symbol, "qty": qty,
                    "side": side.value, "status": order.status.value}
        except Exception as exc:
            self._logger.error(f"Order {symbol}: {exc}")
            return None

    def _place_limit(self, symbol: str, qty: float, price: float, side) -> Optional[dict]:
        if not self._trading:
            self._logger.info(f"[DUMMY] Limit {side.value} {qty}x {symbol} @ {price}")
            return {"status": "dummy", "symbol": symbol, "price": price}
        try:
            req = LimitOrderRequest(symbol=symbol, qty=qty, side=side,
                                    limit_price=round(price, 2),
                                    time_in_force=TimeInForce.DAY)
            order = self._trading.submit_order(req)
            self._logger.info(f"{side.value.upper()} {qty}x {symbol} @ ${price:.2f} {order.id}")
            return {"id": str(order.id), "symbol": symbol, "qty": qty,
                    "side": side.value, "price": price, "status": order.status.value}
        except Exception as exc:
            self._logger.error(f"Limit-Order {symbol}: {exc}")
            return None

    def cancel_all_orders(self) -> bool:
        if not self._trading:
            return False
        try:
            self._trading.cancel_orders()
            return True
        except Exception as exc:
            self._logger.error(f"cancel_all_orders: {exc}")
            return False

    # ------------------------------------------------------------------
    # Marktdaten
    # ------------------------------------------------------------------

    def fetch_ohlcv(
        self,
        symbol: str,
        timeframe: str = "1Day",
        limit: int = 100,
    ) -> Optional[pd.DataFrame]:
        if not self._data:
            return self._dummy_ohlcv(limit)
        try:
            tf = self._parse_timeframe(timeframe)
            start = datetime.utcnow() - timedelta(days=limit + 5)
            req = StockBarsRequest(symbol_or_symbols=symbol, timeframe=tf,
                                   start=start, limit=limit)
            bars = self._data.get_stock_bars(req)
            df = bars.df
            if isinstance(df.index, pd.MultiIndex):
                df = df.xs(symbol, level=0)
            return df[["open", "high", "low", "close", "volume"]].tail(limit)
        except Exception as exc:
            self._logger.error(f"fetch_ohlcv {symbol}: {exc}")
            return None

    def get_latest_price(self, symbol: str) -> Optional[float]:
        df = self.fetch_ohlcv(symbol, timeframe="1Min", limit=1)
        if df is not None and not df.empty:
            return float(df["close"].iloc[-1])
        return None

    @staticmethod
    def _parse_timeframe(tf: str):
        mapping = {
            "1Min":  TimeFrame(1,  TimeFrameUnit.Minute),
            "5Min":  TimeFrame(5,  TimeFrameUnit.Minute),
            "15Min": TimeFrame(15, TimeFrameUnit.Minute),
            "1Hour": TimeFrame(1,  TimeFrameUnit.Hour),
            "1Day":  TimeFrame(1,  TimeFrameUnit.Day),
        }
        return mapping.get(tf, TimeFrame(1, TimeFrameUnit.Day))

    @staticmethod
    def _dummy_ohlcv(n: int = 100) -> pd.DataFrame:
        import numpy as np
        dates = pd.date_range(end=pd.Timestamp.now(), periods=n, freq="1D")
        close = 200 + np.cumsum(np.random.randn(n) * 2)
        return pd.DataFrame({
            "open":   close - abs(np.random.randn(n)),
            "high":   close + abs(np.random.randn(n) * 2),
            "low":    close - abs(np.random.randn(n) * 2),
            "close":  close,
            "volume": abs(np.random.randn(n) * 1e6 + 5e6),
        }, index=dates)

    # ------------------------------------------------------------------
    # Markt-Status
    # ------------------------------------------------------------------

    def is_market_open(self) -> bool:
        if not self._trading:
            return False
        try:
            return self._trading.get_clock().is_open
        except Exception:
            return False

    def time_to_open(self) -> Optional[int]:
        if not self._trading:
            return None
        try:
            clock = self._trading.get_clock()
            if clock.is_open:
                return 0
            return int((clock.next_open - clock.timestamp).total_seconds())
        except Exception:
            return None
