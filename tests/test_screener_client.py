"""Tests fuer ScreenerClient."""

from unittest.mock import MagicMock, patch

from src.screener_client import ScreenerClient, WatchlistEntry


MOCK_DAYTRADING_RESPONSE = {
    "type": "daytrading",
    "date": "2024-01-15",
    "count": 3,
    "picks": [
        {
            "ticker": "TSLA",
            "name": "Tesla Inc",
            "price": 245.50,
            "score": 82,
            "atr_pct": 4.2,
            "volume_m": 95.3,
            "beta": 2.1,
            "rel_volume": 1.4,
            "mktcap_b": 780.0,
            "sector": "Consumer Cyclical",
            "typ": "Aktie",
        },
        {
            "ticker": "NVDA",
            "name": "NVIDIA Corp",
            "price": 495.20,
            "score": 78,
            "atr_pct": 3.8,
            "volume_m": 42.1,
            "beta": 1.7,
            "rel_volume": 1.1,
            "mktcap_b": 1220.0,
            "sector": "Technology",
            "typ": "Aktie",
        },
        {
            "ticker": "TQQQ",
            "name": "ProShares UltraPro QQQ",
            "price": 52.30,
            "score": 71,
            "atr_pct": 5.1,
            "volume_m": 88.0,
            "beta": 3.0,
            "rel_volume": 1.2,
            "mktcap_b": 18.0,
            "sector": "",
            "typ": "ETF (Leveraged)",
        },
    ],
}

MOCK_SIGNALS_RESPONSE = {
    "macro": {"regime": "Risk-On", "note": "Zinskurve normal", "hy_signal": "OK"},
    "bot_action": "BUY",
    "bot_reason": "Makro Risk-On",
    "quality_picks": [],
    "value_picks": [],
}


class TestWatchlistEntry:
    def test_str_contains_ticker(self):
        e = WatchlistEntry(
            ticker="TSLA", name="Tesla", price=245.5,
            score=82, atr_pct=4.2, volume_m=95.3, beta=2.1,
        )
        assert "TSLA" in str(e)

    def test_str_contains_score(self):
        e = WatchlistEntry(
            ticker="NVDA", name="NVIDIA", price=495.2,
            score=78, atr_pct=3.8, volume_m=42.1, beta=1.7,
        )
        assert "78" in str(e)

    def test_default_typ_is_aktie(self):
        e = WatchlistEntry(
            ticker="AAPL", name="Apple", price=180.0,
            score=70, atr_pct=2.0, volume_m=60.0, beta=1.2,
        )
        assert e.typ == "Aktie"


class TestScreenerClient:
    def setup_method(self):
        self.client = ScreenerClient(base_url="http://localhost:8000")

    def test_is_online_true(self):
        with patch.object(self.client._session, "get") as mock_get:
            mock_get.return_value.status_code = 200
            assert self.client.is_online() is True

    def test_is_online_false_on_exception(self):
        with patch.object(self.client._session, "get", side_effect=Exception("timeout")):
            assert self.client.is_online() is False

    def test_get_daytrading_watchlist_returns_entries(self):
        mock_resp = MagicMock()
        mock_resp.json.return_value = MOCK_DAYTRADING_RESPONSE
        mock_resp.raise_for_status = MagicMock()
        with patch.object(self.client._session, "get", return_value=mock_resp):
            entries = self.client.get_daytrading_watchlist()
        assert len(entries) == 3
        assert all(isinstance(e, WatchlistEntry) for e in entries)

    def test_get_daytrading_watchlist_correct_tickers(self):
        mock_resp = MagicMock()
        mock_resp.json.return_value = MOCK_DAYTRADING_RESPONSE
        mock_resp.raise_for_status = MagicMock()
        with patch.object(self.client._session, "get", return_value=mock_resp):
            entries = self.client.get_daytrading_watchlist()
        tickers = [e.ticker for e in entries]
        assert "TSLA" in tickers
        assert "NVDA" in tickers

    def test_get_daytrading_watchlist_empty_on_error(self):
        with patch.object(self.client._session, "get", side_effect=Exception("network error")):
            entries = self.client.get_daytrading_watchlist()
        assert entries == []

    def test_get_daytrading_watchlist_skips_bad_entries(self):
        bad_response = {"picks": [{"ticker": "BAD"}]}  # fehlende Pflichtfelder
        mock_resp = MagicMock()
        mock_resp.json.return_value = bad_response
        mock_resp.raise_for_status = MagicMock()
        with patch.object(self.client._session, "get", return_value=mock_resp):
            entries = self.client.get_daytrading_watchlist()
        assert entries == []

    def test_get_signals_returns_dict(self):
        mock_resp = MagicMock()
        mock_resp.json.return_value = MOCK_SIGNALS_RESPONSE
        mock_resp.raise_for_status = MagicMock()
        with patch.object(self.client._session, "get", return_value=mock_resp):
            signals = self.client.get_signals()
        assert signals["macro"]["regime"] == "Risk-On"
        assert signals["bot_action"] == "BUY"

    def test_get_signals_empty_on_error(self):
        with patch.object(self.client._session, "get", side_effect=Exception()):
            assert self.client.get_signals() == {}

    def test_get_score_returns_dict(self):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"ticker": "TSLA", "scores": {"daytrading": 82}}
        mock_resp.raise_for_status = MagicMock()
        with patch.object(self.client._session, "get", return_value=mock_resp):
            score = self.client.get_score("tsla")  # lowercase -> uppercase
        assert score["ticker"] == "TSLA"

    def test_api_key_in_headers(self):
        client = ScreenerClient(base_url="http://localhost:8000", api_key="secret123")
        assert client._session.headers.get("X-API-Key") == "secret123"

    def test_print_watchlist_no_crash(self, capsys):
        entries = [
            WatchlistEntry(
                ticker="TSLA", name="Tesla", price=245.5,
                score=82, atr_pct=4.2, volume_m=95.3, beta=2.1,
            )
        ]
        self.client.print_watchlist(entries)
        captured = capsys.readouterr()
        assert "TSLA" in captured.out

    def test_print_watchlist_empty(self, capsys):
        self.client.print_watchlist([])
        captured = capsys.readouterr()
        assert "leer" in captured.out
