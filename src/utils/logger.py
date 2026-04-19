"""Strukturiertes Logging fuer den Trading Bot."""

from __future__ import annotations

import logging
import logging.handlers
from pathlib import Path


def setup_logger(config: dict) -> logging.Logger:
    """Konfiguriert Root-Logger mit File- und Console-Handler.

    Args:
        config: Logging-Abschnitt aus config.yaml.

    Returns:
        Konfigurierter Logger.
    """
    level_str = config.get("level", "INFO").upper()
    level = getattr(logging, level_str, logging.INFO)

    log_file = config.get("file", "logs/trading_bot.log")
    max_bytes = config.get("max_bytes", 10 * 1024 * 1024)
    backup_count = config.get("backup_count", 5)

    Path(log_file).parent.mkdir(parents=True, exist_ok=True)

    fmt = logging.Formatter(
        fmt="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    root = logging.getLogger()
    root.setLevel(level)

    # Console
    if not any(isinstance(h, logging.StreamHandler) for h in root.handlers):
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(fmt)
        console_handler.setLevel(level)
        root.addHandler(console_handler)

    # Rotating File
    file_handler = logging.handlers.RotatingFileHandler(
        log_file,
        maxBytes=max_bytes,
        backupCount=backup_count,
        encoding="utf-8",
    )
    file_handler.setFormatter(fmt)
    file_handler.setLevel(level)
    root.addHandler(file_handler)

    return logging.getLogger("trading_bot")
