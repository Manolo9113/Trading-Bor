#!/usr/bin/env python3
"""Trading Bot – Einstiegspunkt.

Modi:
    python main.py --mode backtest
    python main.py --mode live
    python main.py --mode optimize
    python main.py --mode morning_scan
    python main.py --mode alpaca_paper
    python main.py --mode alpaca_live
    python main.py --mode dashboard
"""

import argparse
import sys
import time
from pathlib import Path

import yaml

from src.utils.logger import setup_logger
from src.exchange.connector import ExchangeConnector
from src.exchange.alpaca_connector import AlpacaConnector
from src.data.data_manager import DataManager
from src.indicators.fibonacci import FibonacciCalculator
from src.indicators.patterns import PatternDetector
from src.strategies.fibonacci_confluence import FibonacciConfluenceStrategy
from src.strategies.rsi_macd_strategy import RsiMacdStrategy
from src.strategies.stock_momentum_strategy import StockMomentumStrategy
from src.risk.risk_manager import RiskManager
from src.backtest.backtester import Backtester
from src.notifications.telegram_notifier import TelegramNotifier
from src.screener_client import ScreenerClient


def load_config(path: str = "config/config.yaml") -> dict:
    config_path = Path(path)
    if not config_path.exists():
        print(f"[WARN] {path} nicht gefunden. Kopiere config/config.example.yaml.")
        sys.exit(1)
    with open(config_path) as f:
        return yaml.safe_load(f)


def _build_strategy(config: dict):
    name = config.get("trading", {}).get("strategy", "fibonacci_confluence")
    if name == "rsi_macd":
        return RsiMacdStrategy(config)
    if name == "stock_momentum":
        return StockMomentumStrategy(config)
    fib = FibonacciCalculator(config["fibonacci"])
    pat = PatternDetector(config["patterns"])
    risk = RiskManager(config["risk"])
    return FibonacciConfluenceStrategy(fib, pat, risk, config)


# ── Modi ──────────────────────────────────────────────────────

def run_backtest(config: dict, logger) -> None:
    logger.info("Starte Backtest")
    connector = ExchangeConnector(config["exchange"])
    data_mgr = DataManager()
    bt = config["backtest"]
    df = data_mgr.load(
        connector=connector,
        symbol=config["trading"]["symbol"],
        timeframe=config["trading"]["timeframe"],
        start=bt["start_date"], end=bt["end_date"],
    )
    if df is None or df.empty:
        logger.error("Keine Daten.")
        return
    backtester = Backtester(
        strategy=_build_strategy(config),
        initial_capital=bt["initial_capital"],
        commission=bt["commission"],
        slippage=bt["slippage"],
    )
    backtester.print_results(backtester.run(df))


def run_alpaca(config: dict, logger, paper: bool) -> None:
    """Alpaca Paper- oder Live-Trading mit Screener-Watchlist."""
    mode_str = "PAPER" if paper else "LIVE"
    logger.info(f"Starte Alpaca {mode_str}-Trading")

    # Alpaca-Config zusammenfuehren
    alp_cfg = dict(config.get("alpaca", {}))
    alp_cfg["sandbox"] = paper
    alpaca = AlpacaConnector(alp_cfg)

    acc = alpaca.get_account()
    if not acc:
        logger.error("Alpaca-Konto nicht erreichbar. Keys pruefen.")
        return
    logger.info(
        f"Konto: ${acc.get('equity', 0):,.2f} | "
        f"Kaufkraft: ${acc.get('buying_power', 0):,.2f}"
    )

    # Watchlist vom Screener laden
    api_cfg = config.get("screener_api", {})
    watchlist_tickers: list[str] = []
    if api_cfg.get("base_url"):
        client = ScreenerClient(
            base_url=api_cfg["base_url"],
            api_key=api_cfg.get("api_key", ""),
        )
        dt_cfg = api_cfg.get("daytrading", {})
        entries = client.get_daytrading_watchlist(
            top_n=dt_cfg.get("top_n", 15),
            min_score=dt_cfg.get("min_score", 55),
            min_atr_pct=dt_cfg.get("min_atr_pct", 2.0),
            min_volume_m=dt_cfg.get("min_volume_m", 10.0),
        )
        if dt_cfg.get("exclude_leveraged_etfs", True):
            entries = [e for e in entries if e.typ != "ETF (Leveraged)"]
        watchlist_tickers = [e.ticker for e in entries]
        client.print_watchlist(entries)
    else:
        # Fallback: feste Liste
        watchlist_tickers = ["TSLA", "NVDA", "AMD", "META", "AMZN"]
        logger.warning("Kein Screener konfiguriert – nutze Fallback-Watchlist.")

    if not watchlist_tickers:
        logger.warning("Watchlist leer. Abbruch.")
        return

    strategy = StockMomentumStrategy(config)
    notifier = TelegramNotifier(config)
    alp_cfg2 = config.get("alpaca", {})
    max_pos = alp_cfg2.get("max_positions", 5)
    pos_pct = alp_cfg2.get("position_size_pct", 0.05)
    tf = alp_cfg2.get("timeframe", "1Day")
    poll_secs = 60

    logger.info(f"Watchlist: {watchlist_tickers}")
    logger.info("Trading-Loop gestartet. Strg+C zum Beenden.")

    try:
        while True:
            if not alpaca.is_market_open():
                wait = alpaca.time_to_open()
                logger.info(
                    f"Markt geschlossen. "
                    f"Oeffnet in {wait // 60} Min." if wait else "Markt geschlossen."
                )
                time.sleep(300)
                continue

            positions = alpaca.get_positions()
            open_symbols = {p["symbol"] for p in positions}
            acc = alpaca.get_account()
            equity = acc.get("equity", 0)

            for ticker in watchlist_tickers:
                if ticker in open_symbols:
                    continue
                if len(open_symbols) >= max_pos:
                    break

                df = alpaca.fetch_ohlcv(ticker, timeframe=tf, limit=250)
                if df is None or len(df) < 210:
                    continue

                signal = strategy.generate_signal(df)
                if not signal or not signal.is_entry:
                    continue

                qty = max(1, int(equity * pos_pct / signal.price))
                order = alpaca.buy_market(ticker, qty)
                if order:
                    open_symbols.add(ticker)
                    msg = (
                        f"BUY {qty}x {ticker} @ ~${signal.price:.2f} "
                        f"| SL ${signal.stop_loss:.2f} "
                        f"| TP ${signal.take_profit:.2f} "
                        f"| {signal.reason}"
                    )
                    logger.info(msg)
                    notifier.send_alert(f"Alpaca {mode_str}\n" + msg)

            time.sleep(poll_secs)

    except KeyboardInterrupt:
        logger.info("Loop beendet.")
        if alp_cfg2.get("close_eod", True):
            logger.info("Schliesse alle Positionen...")
            alpaca.close_all_positions()


def run_optimize(config: dict, logger) -> None:
    from src.backtest.optimizer import GridSearchOptimizer
    from src.backtest.walk_forward import WalkForwardTester
    connector = ExchangeConnector(config["exchange"])
    data_mgr = DataManager()
    bt = config["backtest"]
    opt = config.get("optimize", {})
    df = data_mgr.load(
        connector=connector,
        symbol=config["trading"]["symbol"],
        timeframe=config["trading"]["timeframe"],
        start=bt["start_date"], end=bt["end_date"],
    )
    if df is None or df.empty:
        logger.error("Keine Daten.")
        return
    wf = opt.get("walk_forward", {})
    if wf.get("enabled"):
        tester = WalkForwardTester(
            strategy_factory=_build_strategy,
            base_config=config, param_grid=opt.get("param_grid", {}),
            df=df, train_periods=wf.get("train_periods", 1000),
            test_periods=wf.get("test_periods", 250),
            initial_capital=bt["initial_capital"],
            commission=bt["commission"], slippage=bt["slippage"],
        )
        print(tester.run().summary())
    else:
        optimizer = GridSearchOptimizer(
            strategy_factory=_build_strategy,
            base_config=config, param_grid=opt.get("param_grid", {}),
            df=df, initial_capital=bt["initial_capital"],
            commission=bt["commission"], slippage=bt["slippage"],
            metric=opt.get("metric", "sharpe_ratio"),
        )
        print(optimizer.run().summary())


def run_morning_scan(config: dict, logger) -> None:
    api_cfg = config.get("screener_api", {})
    base_url = api_cfg.get("base_url", "")
    if not base_url:
        logger.error("screener_api.base_url fehlt in config.yaml.")
        return
    client = ScreenerClient(base_url=base_url, api_key=api_cfg.get("api_key", ""))
    if not client.is_online():
        logger.error(f"API nicht erreichbar: {base_url}")
        return
    macro = api_cfg.get("macro_filter", {})
    if macro.get("enabled"):
        regime = client.get_signals().get("macro", {}).get("regime", "Neutral")
        logger.info(f"Makro-Regime: {regime}")
        if macro.get("skip_on_risk_off") and regime == "Risk-Off":
            logger.warning("Risk-Off – Morning-Scan abgebrochen.")
            return
    dt = api_cfg.get("daytrading", {})
    entries = client.get_daytrading_watchlist(
        top_n=dt.get("top_n", 15), min_score=dt.get("min_score", 55),
        min_atr_pct=dt.get("min_atr_pct", 2.0), min_volume_m=dt.get("min_volume_m", 10.0),
    )
    if dt.get("exclude_leveraged_etfs", True):
        entries = [e for e in entries if e.typ != "ETF (Leveraged)"]
    client.print_watchlist(entries)
    scan = config.get("morning_scan", {})
    if scan.get("save_to_file") and entries:
        from datetime import date
        import csv
        fp = scan.get("file_path", "data/watchlist_{date}.csv").format(date=date.today())
        Path(fp).parent.mkdir(parents=True, exist_ok=True)
        with open(fp, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(entries[0].__dict__.keys()))
            w.writeheader()
            for e in entries:
                w.writerow(e.__dict__)
        logger.info(f"Gespeichert: {fp}")
    if scan.get("notify_telegram") and entries:
        notifier = TelegramNotifier(config)
        lines = [f"*Morning Scan – {len(entries)} Titel*"]
        for i, e in enumerate(entries[:5], 1):
            lines.append(f"{i}. *{e.ticker}* Score {e.score} | ATR {e.atr_pct:.1f}%")
        notifier.send_alert("\n".join(lines))


def run_live(config: dict, logger) -> None:
    connector = ExchangeConnector(config["exchange"])
    strategy = _build_strategy(config)
    strategy.run_live(connector, config["trading"]["symbol"], config["trading"]["timeframe"])


def run_dashboard(config: dict, logger) -> None:
    from src.dashboard.app import create_app
    cfg = config.get("dashboard", {})
    create_app(config).run(host=cfg.get("host", "0.0.0.0"), port=cfg.get("port", 8050))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--mode",
        choices=["backtest", "live", "optimize",
                 "morning_scan", "alpaca_paper", "alpaca_live", "dashboard"],
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
        "alpaca_paper": lambda c, l: run_alpaca(c, l, paper=True),
        "alpaca_live":  lambda c, l: run_alpaca(c, l, paper=False),
        "dashboard":    run_dashboard,
    }[args.mode](config, logger)


if __name__ == "__main__":
    main()
