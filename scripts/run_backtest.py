#!/usr/bin/env python3
"""Hilfsskript: Schneller Backtest ohne main.py.

Verwendung:
    python scripts/run_backtest.py --strategy fibonacci_confluence
    python scripts/run_backtest.py --strategy rsi_macd
    python scripts/run_backtest.py --strategy multi
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import yaml

from src.exchange.connector import ExchangeConnector
from src.data.data_manager import DataManager
from src.indicators.fibonacci import FibonacciCalculator
from src.indicators.patterns import PatternDetector
from src.strategies.fibonacci_confluence import FibonacciConfluenceStrategy
from src.strategies.rsi_macd_strategy import RsiMacdStrategy
from src.strategies.multi_strategy import MultiStrategy
from src.risk.risk_manager import RiskManager
from src.backtest.backtester import Backtester
from src.utils.logger import setup_logger


def main() -> None:
    parser = argparse.ArgumentParser(description="Schneller Backtest")
    parser.add_argument("--strategy", default="fibonacci_confluence",
                        choices=["fibonacci_confluence", "rsi_macd", "multi"])
    parser.add_argument("--config", default="config/config.yaml")
    args = parser.parse_args()

    with open(args.config, "r") as f:
        config = yaml.safe_load(f)

    logger = setup_logger(config.get("logging", {}))
    connector = ExchangeConnector(config["exchange"])
    data_mgr  = DataManager()
    bt_cfg    = config["backtest"]

    df = data_mgr.load(
        connector=connector,
        symbol=config["trading"]["symbol"],
        timeframe=config["trading"]["timeframe"],
        start=bt_cfg["start_date"],
        end=bt_cfg["end_date"],
    )
    if df is None or df.empty:
        logger.error("Keine Daten.")
        sys.exit(1)

    fib  = FibonacciConfluenceStrategy(
        FibonacciCalculator(config["fibonacci"]),
        PatternDetector(config["patterns"]),
        RiskManager(config["risk"]),
        config,
    )
    rsi_macd = RsiMacdStrategy(config)

    strategies = {
        "fibonacci_confluence": fib,
        "rsi_macd": rsi_macd,
        "multi": MultiStrategy([fib, rsi_macd], config, min_votes=2),
    }
    strategy = strategies[args.strategy]
    logger.info(f"Strategie: {args.strategy}")

    bt = Backtester(
        strategy=strategy,
        initial_capital=bt_cfg["initial_capital"],
        commission=bt_cfg["commission"],
        slippage=bt_cfg["slippage"],
    )
    result = bt.run(df)
    bt.print_results(result)


if __name__ == "__main__":
    main()
