"""Walk-Forward-Testing.

Teilt den Datensatz in In-Sample (Training) und Out-of-Sample (Test)
Fenster auf und prueft ob die optimierten Parameter generalisieren.
"""

from __future__ import annotations

import logging
from copy import deepcopy
from dataclasses import dataclass, field

import pandas as pd

from .backtester import Backtester, BacktestResult
from .optimizer import GridSearchOptimizer


@dataclass
class WalkForwardWindow:
    window_nr: int
    train_start: str
    train_end: str
    test_start: str
    test_end: str
    best_params: dict
    train_result: BacktestResult
    test_result: BacktestResult


@dataclass
class WalkForwardResult:
    windows: list[WalkForwardWindow] = field(default_factory=list)

    def summary(self) -> str:
        lines = [
            "=" * 60,
            "  WALK-FORWARD ERGEBNISSE",
            "=" * 60,
            f"  {'Fenster':<8} {'Train-Sharpe':>14} {'Test-Sharpe':>12} {'Test-Return':>12} {'Test-WR':>10}",
            "-" * 60,
        ]
        for w in self.windows:
            lines.append(
                f"  {w.window_nr:<8} "
                f"{w.train_result.sharpe_ratio:>14.3f} "
                f"{w.test_result.sharpe_ratio:>12.3f} "
                f"{w.test_result.total_return:>+11.2%} "
                f"{w.test_result.win_rate:>10.1%}"
            )
        if self.windows:
            avg_test_sharpe = sum(w.test_result.sharpe_ratio for w in self.windows) / len(self.windows)
            avg_test_return = sum(w.test_result.total_return for w in self.windows) / len(self.windows)
            lines += [
                "-" * 60,
                f"  {'Durchschnitt':<8} {'':>14} {avg_test_sharpe:>12.3f} {avg_test_return:>+11.2%}",
            ]
        lines.append("=" * 60)
        return "\n".join(lines)


class WalkForwardTester:
    """Walk-Forward-Analyse: optimiert auf Training, validiert auf Test.

    Beispiel::

        wf = WalkForwardTester(
            strategy_factory=factory_fn,
            base_config=config,
            param_grid={"fibonacci.confluence_tolerance": [0.002, 0.003, 0.005]},
            df=df,
            train_periods=1000,
            test_periods=250,
        )
        result = wf.run()
        print(result.summary())
    """

    def __init__(
        self,
        strategy_factory,
        base_config: dict,
        param_grid: dict,
        df: pd.DataFrame,
        train_periods: int = 1000,
        test_periods: int = 250,
        step_periods: int | None = None,
        initial_capital: float = 10_000.0,
        commission: float = 0.001,
        slippage: float = 0.0005,
    ) -> None:
        self.strategy_factory = strategy_factory
        self.base_config = base_config
        self.param_grid = param_grid
        self.df = df
        self.train_periods = train_periods
        self.test_periods = test_periods
        self.step_periods = step_periods or test_periods
        self.initial_capital = initial_capital
        self.commission = commission
        self.slippage = slippage
        self._logger = logging.getLogger(self.__class__.__name__)

    def run(self) -> WalkForwardResult:
        result = WalkForwardResult()
        window_nr = 1
        total = len(self.df)
        start = 0

        while start + self.train_periods + self.test_periods <= total:
            train_df = self.df.iloc[start: start + self.train_periods]
            test_df  = self.df.iloc[start + self.train_periods: start + self.train_periods + self.test_periods]

            self._logger.info(
                f"Fenster {window_nr}: Train [{train_df.index[0].date()} – "
                f"{train_df.index[-1].date()}], "
                f"Test [{test_df.index[0].date()} – {test_df.index[-1].date()}]"
            )

            # Optimierung auf Train-Daten
            optimizer = GridSearchOptimizer(
                strategy_factory=self.strategy_factory,
                base_config=deepcopy(self.base_config),
                param_grid=self.param_grid,
                df=train_df,
                initial_capital=self.initial_capital,
                commission=self.commission,
                slippage=self.slippage,
            )
            opt_result = optimizer.run()

            # Validierung auf Test-Daten mit besten Parametern
            test_config = deepcopy(self.base_config)
            for path, val in opt_result.best_params.items():
                keys = path.split(".")
                d = test_config
                for k in keys[:-1]:
                    d = d.setdefault(k, {})
                d[keys[-1]] = val

            test_strategy = self.strategy_factory(test_config)
            bt = Backtester(
                strategy=test_strategy,
                initial_capital=self.initial_capital,
                commission=self.commission,
                slippage=self.slippage,
            )
            test_bt_result = bt.run(test_df)

            result.windows.append(WalkForwardWindow(
                window_nr=window_nr,
                train_start=str(train_df.index[0].date()),
                train_end=str(train_df.index[-1].date()),
                test_start=str(test_df.index[0].date()),
                test_end=str(test_df.index[-1].date()),
                best_params=opt_result.best_params,
                train_result=opt_result.best_result,
                test_result=test_bt_result,
            ))

            start += self.step_periods
            window_nr += 1

        return result
