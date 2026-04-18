#!/usr/bin/env python3
"""Trading Bot – Einstiegspunkt.

Verwendung:
    python main.py --mode backtest
    python main.py --mode live
    python main.py --mode optimize
    python main.py --mode dashboard
"""

import argparse
import sys
from pathlib import Path

import yaml

from src.utils.logger import setup_logger
from src.exchange.connector import ExchangeConnector
from src.data.data_manager import DataManager
from src.indicators.fibonacci import FibonacciCalculator
from src.indicators.patterns import PatternDetector
from src.strategies.fibonacci_confluence import FibonacciConfluenceStrategy
from src.strategies.rsi_macd_strategy import RsiMacdStrategy
from src.risk.risk_manager import RiskManager
from src.backtest.backtester import Backtester
from src.notifications.telegram_notifier import TelegramNotifier


def load_config(path: str = "config/config.yaml") -> dict:
    config_path = Path(path)
    if not config_path.exists():
        example = Path("config/config.example.yaml")
        if example.exists():
            print(
                f"[WARN] {path} nicht gefunden. "
                "Kopiere config/config.example.yaml nach config/config.yaml "
                "und trage deine Einstellungen ein."
            )
        sys.exit(1)
    with open(config_path, "r") as f:
        return yaml.safe_load(f)


def _build_strategy(config: dict):
    """Waehlt Strategie basierend auf config.trading.strategy."""
    name = config.get("trading", {}).get("strategy", "fibonacci_confluence")
    if name == "rsi_macd":
        return RsiMacdStrategy(config)
    # Default: Fibonacci Confluence
    fib_calc = FibonacciCalculator(config["fibonacci"])
    pattern_det = PatternDetector(config["patterns"])
    risk_mgr = RiskManager(config["risk"])
    return FibonacciConfluenceStrategy(fib_calc, pattern_det, risk_mgr, config)


def run_backtest(config: dict, logger) -> None:
    logger.info("Starte Backtest-Modus")
    connector = ExchangeConnector(config["exchange"])
    data_mgr = DataManager()
    bt_cfg = config["backtest"]
    df = data_mgr.load(
        connector=connector,
        symbol=config["trading"]["symbol"],
        timeframe=config["trading"]["timeframe"],
        start=bt_cfg["start_date"],
        end=bt_cfg["end_date"],
    )
    if df is None or df.empty:
        logger.error("Keine Daten. Backtest abgebrochen.")
        return
    strategy = _build_strategy(config)
    backtester = Backtester(
        strategy=strategy,
        initial_capital=bt_cfg["initial_capital"],
        commission=bt_cfg["commission"],
        slippage=bt_cfg["slippage"],
    )
    results = backtester.run(df)
    backtester.print_results(results)


def run_optimize(config: dict, logger) -> None:
    logger.info("Starte Optimierungs-Modus")
    from src.backtest.optimizer import GridSearchOptimizer
    from src.backtest.walk_forward import WalkForwardTester

    connector = ExchangeConnector(config["exchange"])
    data_mgr = DataManager()
    bt_cfg = config["backtest"]
    opt_cfg = config.get("optimize", {})

    df = data_mgr.load(
        connector=connector,
        symbol=config["trading"]["symbol"],
        timeframe=config["trading"]["timeframe"],
        start=bt_cfg["start_date"],
        end=bt_cfg["end_date"],
    )
    if df is None or df.empty:
        logger.error("Keine Daten. Optimierung abgebrochen.")
        return

    param_grid = opt_cfg.get("param_grid", {
        "fibonacci.confluence_tolerance": [0.002, 0.003, 0.005],
        "risk.stop_loss_atr_mult": [1.5, 2.0, 2.5],
    })
    metric = opt_cfg.get("metric", "sharpe_ratio")
    wf_cfg = opt_cfg.get("walk_forward", {})

    if wf_cfg.get("enabled", False):
        tester = WalkForwardTester(
            strategy_factory=_build_strategy,
            base_config=config,
            param_grid=param_grid,
            df=df,
            train_periods=wf_cfg.get("train_periods", 1000),
            test_periods=wf_cfg.get("test_periods", 250),
            initial_capital=bt_cfg["initial_capital"],
            commission=bt_cfg["commission"],
            slippage=bt_cfg["slippage"],
        )
        wf_result = tester.run()
        print(wf_result.summary())
    else:
        optimizer = GridSearchOptimizer(
            strategy_factory=_build_strategy,
            base_config=config,
            param_grid=param_grid,
            df=df,
            initial_capital=bt_cfg["initial_capital"],
            commission=bt_cfg["commission"],
            slippage=bt_cfg["slippage"],
            metric=metric,
        )
        opt_result = optimizer.run()
        print(opt_result.summary())


def run_live(config: dict, logger) -> None:
    logger.info("Starte Live-Trading-Modus")
    logger.warning(
        "Live-Trading aktiv! Stelle sicher, dass sandbox=true gesetzt ist "
        "oder du weisst was du tust."
    )
    connector = ExchangeConnector(config["exchange"])
    strategy = _build_strategy(config)
    notifier = TelegramNotifier(config)
    symbol = config["trading"]["symbol"]
    timeframe = config["trading"]["timeframe"]
    logger.info(f"Trading {symbol} auf {timeframe}")
    strategy.run_live(connector, symbol, timeframe)


def run_dashboard(config: dict, logger) -> None:
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
        choices=["backtest", "live", "optimize", "dashboard"],
        default="backtest",
        help="Ausfuehrungsmodus (default: backtest)",
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
        "backtest":  run_backtest,
        "live":      run_live,
        "optimize":  run_optimize,
        "dashboard": run_dashboard,
    }
    modes[args.mode](config, logger)


if __name__ == "__main__":
    main()
