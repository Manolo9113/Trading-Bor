#!/usr/bin/env python3
"""Hilfsskript: Historische OHLCV-Daten herunterladen und cachen.

Verwendung:
    python scripts/download_data.py --symbol BTC/USDT --tf 1h \
        --start 2023-01-01 --end 2024-12-31
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import yaml

from src.exchange.connector import ExchangeConnector
from src.data.data_manager import DataManager
from src.utils.logger import setup_logger


def main() -> None:
    parser = argparse.ArgumentParser(description="OHLCV-Daten herunterladen")
    parser.add_argument("--symbol",  default="BTC/USDT")
    parser.add_argument("--tf",      default="1h",        dest="timeframe")
    parser.add_argument("--start",   default="2023-01-01")
    parser.add_argument("--end",     default="2024-12-31")
    parser.add_argument("--config",  default="config/config.yaml")
    parser.add_argument("--force",   action="store_true",
                        help="Cache ignorieren und neu laden")
    args = parser.parse_args()

    with open(args.config, "r") as f:
        config = yaml.safe_load(f)

    logger = setup_logger(config.get("logging", {}))
    connector = ExchangeConnector(config["exchange"])
    data_mgr  = DataManager()

    logger.info(f"Lade {args.symbol} {args.timeframe} von {args.start} bis {args.end}")
    df = data_mgr.load(
        connector=connector,
        symbol=args.symbol,
        timeframe=args.timeframe,
        start=args.start,
        end=args.end,
        force_reload=args.force,
    )

    if df is None or df.empty:
        logger.error("Download fehlgeschlagen.")
        sys.exit(1)

    logger.info(f"Erfolgreich: {len(df)} Kerzen geladen.")
    print(df.tail())


if __name__ == "__main__":
    main()
