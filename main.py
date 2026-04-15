#!/usr/bin/env python3
"""Trading Bot – Einstiegspunkt.

Verwendung:
    python main.py --mode backtest
    python main.py --mode live
    python main.py --mode dashboard
"""

import argparse
import sys
from pathlib import Path

import yaml

from src.utils.logger import setup_logger
from src.exchange.connector import ExchangeConnector
from src.indicators.fibonacci import FibonacciCalculator
from src.indicators.patterns import PatternDetector
from src.strategies.fibonacci_confluence import FibonacciConfluenceStrategy
from src.risk.risk_manager import RiskManager
from src.backtest.backtester import Backtester


def load_config(path: str = "config/config.yaml") -> dict:
    """Lade YAML-Konfiguration."""
    config_path = Path(path)
    if not config_path.exists():
        example = Path("config/config.example.yaml")
        if example.exists():
            print(
                f"[WARN] {path} nicht gefunden. "
                "Kopiere config/config.example.yaml nach config/config.yaml "
                "und trage deine API-Keys ein."
            )
        sys.exit(1)
    with open(config_path, "r") as f:
        return yaml.safe_load(f)


def run_backtest(config: dict, logger) -> None:
    """Backtest-Modus: historische Daten laden und Strategie testen."""
    logger.info("Starte Backtest-Modus")
    connector = ExchangeConnector(config["exchange"])
    bt_cfg = config["backtest"]
    df = connector.fetch_ohlcv_history(
        symbol=config["trading"]["symbol"],
        timeframe=config["trading"]["timeframe"],
        start=bt_cfg["start_date"],
        end=bt_cfg["end_date"],
    )
    if df is None or df.empty:
        logger.error("Keine historischen Daten erhalten. Backtest abgebrochen.")
        return

    fib_calc = FibonacciCalculator(config["fibonacci"])
    pattern_det = PatternDetector(config["patterns"])
    risk_mgr = RiskManager(config["risk"])
    strategy = FibonacciConfluenceStrategy(fib_calc, pattern_det, risk_mgr, config)

    backtester = Backtester(
        strategy=strategy,
        initial_capital=bt_cfg["initial_capital"],
        commission=bt_cfg["commission"],
        slippage=bt_cfg["slippage"],
    )
    results = backtester.run(df)
    backtester.print_results(results)


def run_live(config: dict, logger) -> None:
    """Live-Trading-Modus: Echtzeit-Signale und Order-Execution."""
    logger.info("Starte Live-Trading-Modus")
    logger.warning(
        "Live-Trading aktiv! Stelle sicher, dass du sandbox=true in der Config hast "
        "oder weißt, was du tust."
    )
    connector = ExchangeConnector(config["exchange"])
    fib_calc = FibonacciCalculator(config["fibonacci"])
    pattern_det = PatternDetector(config["patterns"])
    risk_mgr = RiskManager(config["risk"])
    strategy = FibonacciConfluenceStrategy(fib_calc, pattern_det, risk_mgr, config)

    symbol = config["trading"]["symbol"]
    timeframe = config["trading"]["timeframe"]

    logger.info(f"Trading {symbol} auf {timeframe}-Chart")
    strategy.run_live(connector, symbol, timeframe)


def run_dashboard(config: dict, logger) -> None:
    """Dashboard-Modus: Dash-App starten."""
    logger.info("Starte Dashboard")
    from src.dashboard.app import create_app
    dash_cfg = config.get("dashboard", {})
    app = create_app(config)
    app.run(
        host=dash_cfg.get("host", "0.0.0.0"),
        port=dash_cfg.get("port", 8050),
        debug=dash_cfg.get("debug", False),
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Fibonacci Confluence Trading Bot")
    parser.add_argument(
        "--mode",
        choices=["backtest", "live", "dashboard"],
        default="backtest",
        help="Ausführungsmodus (default: backtest)",
    )
    parser.add_argument(
        "--config",
        default="config/config.yaml",
        help="Pfad zur Konfigurationsdatei",
    )
    args = parser.parse_args()

    config = load_config(args.config)
    logger = setup_logger(config.get("logging", {}))

    modes = {
        "backtest": run_backtest,
        "live": run_live,
        "dashboard": run_dashboard,
    }
    modes[args.mode](config, logger)


if __name__ == "__main__":
    main()
