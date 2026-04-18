"""Telegram-Benachrichtigungen fuer Trade-Signale und Alerts.

Setup:
  1. Bot bei @BotFather erstellen -> TELEGRAM_BOT_TOKEN
  2. Chat-ID ermitteln: https://api.telegram.org/bot<TOKEN>/getUpdates
  3. In config.yaml oder .env eintragen.
"""

from __future__ import annotations

import logging
import os
from typing import Optional

try:
    import requests
    REQUESTS_AVAILABLE = True
except ImportError:
    REQUESTS_AVAILABLE = False

from ..strategies.base_strategy import Signal, SignalType


class TelegramNotifier:
    """Sendet Nachrichten via Telegram Bot API."""

    API_URL = "https://api.telegram.org/bot{token}/sendMessage"

    def __init__(self, config: dict) -> None:
        cfg = config.get("telegram", {})
        self.token: str = cfg.get("bot_token") or os.getenv("TELEGRAM_BOT_TOKEN", "")
        self.chat_id: str = str(cfg.get("chat_id") or os.getenv("TELEGRAM_CHAT_ID", ""))
        self.enabled: bool = bool(self.token and self.chat_id)
        self._logger = logging.getLogger(self.__class__.__name__)

        if not self.enabled:
            self._logger.info("Telegram nicht konfiguriert – Benachrichtigungen deaktiviert.")

    def send_signal(self, signal: Signal, symbol: str) -> bool:
        """Sendet ein Handelssignal als formatierte Telegram-Nachricht."""
        emoji = "📈" if signal.signal_type == SignalType.BUY else "📉"
        direction = "LONG" if signal.signal_type == SignalType.BUY else "SHORT"
        msg = (
            f"{emoji} *{direction} Signal* – {symbol}\n"
            f"Entry:       `{signal.price:.4f}`\n"
            f"Stop-Loss:   `{signal.stop_loss:.4f}`\n"
            f"Take-Profit: `{signal.take_profit:.4f}`\n"
            f"R:R Ratio:   `{signal.risk_reward:.2f}`\n"
            f"Confidence:  `{signal.confidence:.0%}`\n"
            f"Grund: _{signal.reason}_"
        )
        return self._send(msg)

    def send_alert(self, text: str) -> bool:
        """Sendet eine freie Textnachricht."""
        return self._send(f"⚠️ *Alert*\n{text}")

    def send_trade_closed(self, symbol: str, pnl: float, reason: str) -> bool:
        """Benachrichtigung wenn ein Trade geschlossen wird."""
        emoji = "✅" if pnl >= 0 else "❌"
        msg = (
            f"{emoji} *Trade geschlossen* – {symbol}\n"
            f"PnL:   `{pnl:+.4f}`\n"
            f"Grund: _{reason}_"
        )
        return self._send(msg)

    def _send(self, text: str) -> bool:
        if not self.enabled:
            return False
        if not REQUESTS_AVAILABLE:
            self._logger.warning("requests nicht installiert.")
            return False
        try:
            url = self.API_URL.format(token=self.token)
            resp = requests.post(
                url,
                json={"chat_id": self.chat_id, "text": text, "parse_mode": "Markdown"},
                timeout=10,
            )
            resp.raise_for_status()
            return True
        except Exception as exc:
            self._logger.error(f"Telegram-Nachricht fehlgeschlagen: {exc}")
            return False
