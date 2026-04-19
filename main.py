#!/usr/bin/env python3
"""Trading Bot – Einstiegspunkt.

Verwendung:
    python main.py --mode backtest
    python main.py --mode live
    python main.py --mode optimize
    python main.py --mode morning_scan
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
from src.screener_client import ScreenerClient


def load_config(path: str = "config/config.yaml") -> dict:
    config_path = Path(path)
    if not config_path.exists():
        print(
            f"[WARN] {path} nicht gefunden. "
            "Kopiere config/config.example.yaml nach config/config.yaml."
        )
        sys.exit(1)
    with open(config_path, "r") as f:
        return yaml.safe_load(f)


def _build_strategy(config: dict):
    name = config.get("trading", {}).get("strategy", "fibonacci_confluence")
    if name == "rsi_macd":
        return RsiMacdStrategy(config)
    fib_calc = FibonacciCalculator(config["fibonacci"])
    pattern_det = PatternDetector(config["patterns"])
    risk_mgr = RiskManager(config["risk"])
    return FibonacciConfluenceStrategy(fib_calc, pattern_det, risk_mgr, config)


# ── Modi ─────────────────────────────────────────────────────────────────────

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

    param_grid = opt_cfg.get("param_grid", {})
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
        print(tester.run().summary())
    else:
        optimizer = GridSearchOptimizer(
            strategy_factory=_build_strategy,
            base_config=config,
            param_grid=param_grid,
            df=df,
            initial_capital=bt_cfg["initial_capital"],
            commission=bt_cfg["commission"],
            slippage=bt_cfg["slippage"],
            metric=opt_cfg.get("metric", "sharpe_ratio"),
        )
        print(optimizer.run().summary())


def run_morning_scan(config: dict, logger) -> None:
    """Morgen-Scan: Watchlist vom Screener holen, filtern, loggen und
    optional per Telegram schicken + als CSV speichern."""
    logger.info("Starte Morning-Scan")

    api_cfg = config.get("screener_api", {})
    base_url = api_cfg.get("base_url", "")
    if not base_url:
        logger.error(
            "screener_api.base_url fehlt in config.yaml. "
            "Trage die Railway-URL deines Screener-Services ein."
        )
        return

    client = ScreenerClient(
        base_url=base_url,
        api_key=api_cfg.get("api_key", ""),
        timeout=api_cfg.get("timeout", 30),
    )

    # API-Health pruefen
    if not client.is_online():
        logger.error(f"Screener-API nicht erreichbar: {base_url}")
        return

    # Makro-Regime pruefen (optional)
    macro_cfg = api_cfg.get("macro_filter", {})
    if macro_cfg.get("enabled", True):
        signals = client.get_signals()
        regime = signals.get("macro", {}).get("regime", "Neutral")
        logger.info(f"Makro-Regime: {regime}")
        if macro_cfg.get("skip_on_risk_off", True) and regime == "Risk-Off":
            logger.warning("Makro Risk-Off – kein Trade heute. Morning-Scan abgebrochen.")
            return

    # Watchlist laden
    dt_cfg = api_cfg.get("daytrading", {})
    watchlist = client.get_daytrading_watchlist(
        top_n=dt_cfg.get("top_n", 15),
        min_score=dt_cfg.get("min_score", 55),
        min_atr_pct=dt_cfg.get("min_atr_pct", 2.0),
        min_volume_m=dt_cfg.get("min_volume_m", 10.0),
    )

    # Leveraged ETFs optional ausschliessen
    if dt_cfg.get("exclude_leveraged_etfs", True):
        watchlist = [e for e in watchlist if e.typ != "ETF (Leveraged)"]
        logger.info(f"Nach ETF-Filter: {len(watchlist)} Titel")

    if not watchlist:
        logger.warning("Watchlist leer – keine Titel gefunden.")
        return

    client.print_watchlist(watchlist)

    # CSV speichern
    scan_cfg = config.get("morning_scan", {})
    if scan_cfg.get("save_to_file", True):
        from datetime import date
        import csv
        today = date.today().isoformat()
        filepath = scan_cfg.get("file_path", "data/watchlist_{date}.csv").format(date=today)
        Path(filepath).parent.mkdir(parents=True, exist_ok=True)
        with open(filepath, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=[
                "ticker", "name", "price", "score",
                "atr_pct", "volume_m", "beta", "rel_volume",
                "mktcap_b", "sector", "typ",
            ])
            writer.writeheader()
            for e in watchlist:
                writer.writerow(e.__dict__)
        logger.info(f"Watchlist gespeichert: {filepath}")

    # Telegram-Benachrichtigung
    if scan_cfg.get("notify_telegram", False):
        notifier = TelegramNotifier(config)
        top5 = watchlist[:5]
        lines = [f"*Morning Scan – {len(watchlist)} Titel*\n"]
        for i, e in enumerate(top5, 1):
            lines.append(
                f"{i}. *{e.ticker}* – Score {e.score} "
                f"| ATR {e.atr_pct:.1f}% "
                f"| Vol {e.volume_m:.0f}M"
            )
        if len(watchlist) > 5:
            lines.append(f"_...und {len(watchlist)-5} weitere_")
        notifier.send_alert("\n".join(lines))

    logger.info("Morning-Scan abgeschlossen.")


def run_live(config: dict, logger) -> None:
    logger.info("Starte Live-Trading-Modus")
    logger.warning("Live-Trading aktiv! Sandbox pruefen.")
    connector = ExchangeConnector(config["exchange"])
    strategy = _build_strategy(config)
    symbol = config["trading"]["symbol"]
    timeframe = config["trading"]["timeframe"]
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
        choices=["backtest", "live", "optimize", "morning_scan", "dashboard"],
        default="backtest",
    )
    parser.add_argument("--config", default="config/config.yaml")
    args = parser.parse_args()
    config = load_config(args.config)
    logger = setup_logger(config.get("logging", {}))

    {
        "backtest":     run_backtest,
        "live":         run_live,
        "optimize":     run_optimize,
        "morning_scan": run_morning_scan,
        "dashboard":    run_dashboard,
    }[args.mode](config, logger)


if __name__ == "__main__":
    main()
