"""Hyperparameter-Optimierung via Grid Search.

Testet alle Kombinationen aus einem Parameter-Grid und gibt
die besten Einstellungen nach Sharpe Ratio zurueck.
"""

from __future__ import annotations

import itertools
import logging
from copy import deepcopy
from dataclasses import dataclass
from typing import Any

import pandas as pd

from .backtester import Backtester, BacktestResult


@dataclass
class OptimizationResult:
    best_params: dict
    best_result: BacktestResult
    all_results: list[dict]

    def summary(self) -> str:
        lines = [
            "=" * 55,
            "  OPTIMIERUNGS-ERGEBNIS",
            "=" * 55,
            f"  Beste Parameter: {self.best_params}",
            f"  Sharpe Ratio   : {self.best_result.sharpe_ratio:.3f}",
            f"  Gesamtrendite  : {self.best_result.total_return:+.2%}",
            f"  Win-Rate       : {self.best_result.win_rate:.1%}",
            f"  Max. Drawdown  : {self.best_result.max_drawdown:.2%}",
            f"  Trades         : {self.best_result.total_trades}",
            "=" * 55,
            f"  Getestete Kombinationen: {len(self.all_results)}",
        ]
        return "\n".join(lines)


class GridSearchOptimizer:
    """Brute-Force Grid Search ueber Strategie-Parameter.

    Beispiel::

        optimizer = GridSearchOptimizer(
            strategy_class=FibonacciConfluenceStrategy,
            base_config=config,
            param_grid={
                "fibonacci.confluence_tolerance": [0.002, 0.003, 0.005],
                "risk.stop_loss_atr_mult": [1.5, 2.0, 2.5],
            },
            df=df,
        )
        result = optimizer.run()
        print(result.summary())
    """

    def __init__(
        self,
        strategy_factory,
        base_config: dict,
        param_grid: dict[str, list[Any]],
        df: pd.DataFrame,
        initial_capital: float = 10_000.0,
        commission: float = 0.001,
        slippage: float = 0.0005,
        metric: str = "sharpe_ratio",
    ) -> None:
        self.strategy_factory = strategy_factory
        self.base_config = base_config
        self.param_grid = param_grid
        self.df = df
        self.initial_capital = initial_capital
        self.commission = commission
        self.slippage = slippage
        self.metric = metric
        self._logger = logging.getLogger(self.__class__.__name__)

    def _set_nested(self, config: dict, key_path: str, value: Any) -> dict:
        """Setzt einen verschachtelten Wert via Punkt-Notation."""
        keys = key_path.split(".")
        d = config
        for k in keys[:-1]:
            d = d.setdefault(k, {})
        d[keys[-1]] = value
        return config

    def run(self) -> OptimizationResult:
        """Fuehrt Grid Search durch und gibt bestes Ergebnis zurueck."""
        keys = list(self.param_grid.keys())
        values = list(self.param_grid.values())
        combinations = list(itertools.product(*values))

        self._logger.info(
            f"Grid Search: {len(combinations)} Kombinationen fuer {keys}"
        )

        all_results: list[dict] = []
        best_score = float("-inf")
        best_params: dict = {}
        best_result: BacktestResult | None = None

        for i, combo in enumerate(combinations):
            params = dict(zip(keys, combo))
            config = deepcopy(self.base_config)
            for path, val in params.items():
                self._set_nested(config, path, val)

            try:
                strategy = self.strategy_factory(config)
                backtester = Backtester(
                    strategy=strategy,
                    initial_capital=self.initial_capital,
                    commission=self.commission,
                    slippage=self.slippage,
                )
                result = backtester.run(self.df)
                score = getattr(result, self.metric, float("-inf"))

                all_results.append({"params": params, "score": score, "result": result})

                if score > best_score:
                    best_score = score
                    best_params = params
                    best_result = result
                    self._logger.info(
                        f"[{i+1}/{len(combinations)}] Neues Bestes: "
                        f"{self.metric}={score:.3f} | {params}"
                    )
                else:
                    self._logger.debug(
                        f"[{i+1}/{len(combinations)}] {self.metric}={score:.3f} | {params}"
                    )
            except Exception as exc:
                self._logger.warning(f"Kombination {params} fehlgeschlagen: {exc}")

        if best_result is None:
            raise RuntimeError("Keine einzige Kombination erfolgreich optimiert.")

        return OptimizationResult(
            best_params=best_params,
            best_result=best_result,
            all_results=all_results,
        )
