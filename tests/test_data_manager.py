"""Tests fuer DataManager."""

import pandas as pd
import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch

from src.data.data_manager import DataManager


def _dummy_df(n: int = 50) -> pd.DataFrame:
    import numpy as np
    dates = pd.date_range("2023-01-01", periods=n, freq="1h")
    close = 100 + np.random.randn(n).cumsum()
    return pd.DataFrame({
        "open":   close - 0.1,
        "high":   close + 0.2,
        "low":    close - 0.2,
        "close":  close,
        "volume": abs(np.random.randn(n) * 100 + 1000),
    }, index=dates)


class TestDataManager:
    def setup_method(self, tmp_path_factory):
        self.tmp_dir = str(pytest.tmp_path_factory if hasattr(pytest, 'tmp_path_factory') else Path("/tmp/test_data"))
        self.dm = DataManager(data_dir="/tmp/test_dm_cache")

    def test_list_cached_returns_list(self):
        result = self.dm.list_cached()
        assert isinstance(result, list)

    def test_load_calls_connector_when_no_cache(self):
        connector = MagicMock()
        connector.fetch_ohlcv_history.return_value = _dummy_df()
        df = self.dm.load(
            connector=connector,
            symbol="BTC/USDT",
            timeframe="1h",
            start="2023-06-01",
            end="2023-06-05",
            force_reload=True,
        )
        assert connector.fetch_ohlcv_history.called
        assert df is not None
        assert not df.empty

    def test_load_returns_none_when_connector_fails(self):
        connector = MagicMock()
        connector.fetch_ohlcv_history.return_value = None
        df = self.dm.load(
            connector=connector,
            symbol="ETH/USDT",
            timeframe="1h",
            start="2023-07-01",
            end="2023-07-02",
            force_reload=True,
        )
        assert df is None

    def test_clean_removes_duplicates(self):
        df = _dummy_df(10)
        df_duped = pd.concat([df, df.iloc[:3]])
        cleaned = DataManager._clean(df_duped)
        assert cleaned.index.is_unique

    def test_clean_sorts_index(self):
        df = _dummy_df(20)
        shuffled = df.sample(frac=1, random_state=42)
        cleaned = DataManager._clean(shuffled)
        assert cleaned.index.is_monotonic_increasing

    def test_clean_drops_na(self):
        df = _dummy_df(20)
        df.iloc[5, 0] = float("nan")
        df.iloc[5, 1] = float("nan")
        df.iloc[5, 2] = float("nan")
        df.iloc[5, 3] = float("nan")
        cleaned = DataManager._clean(df)
        assert not cleaned.isna().any().any()

    def test_cache_path_format(self):
        path = self.dm._cache_path("BTC/USDT", "1h", "2023-01-01", "2023-12-31")
        assert "BTC-USDT" in path.name
        assert "1h" in path.name
        assert path.suffix == ".parquet"

    def test_delete_nonexistent_cache_returns_false(self):
        result = self.dm.delete_cache("XYZ/ABC", "5m", "2020-01-01", "2020-01-02")
        assert result is False
