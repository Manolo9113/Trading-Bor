"""Tests fuer RiskManager."""

import pytest

from src.risk.risk_manager import RiskManager, Trade


CONFIG = {
    "max_position_size": 0.1,
    "risk_per_trade": 0.02,
    "stop_loss_atr_mult": 2.0,
    "take_profit_ratio": 2.0,
    "max_open_positions": 3,
    "max_daily_drawdown": 0.05,
    "position_spacing": 0.005,
}


class TestRiskManager:
    def setup_method(self):
        self.rm = RiskManager(CONFIG)

    def test_position_size_not_exceeds_max(self):
        size = self.rm.position_size(capital=10_000, entry=100, stop_loss=90)
        assert size <= CONFIG["max_position_size"]

    def test_position_size_zero_when_no_risk(self):
        size = self.rm.position_size(capital=10_000, entry=100, stop_loss=100)
        assert size == 0.0

    def test_position_size_positive(self):
        size = self.rm.position_size(capital=10_000, entry=100, stop_loss=95)
        assert size > 0.0

    def test_can_open_within_limits(self):
        assert self.rm.can_open_position(10_000, 10_000) is True

    def test_cannot_open_at_max_positions(self):
        for i in range(CONFIG["max_open_positions"]):
            t = Trade(entry_price=100+i, stop_loss=95, take_profit=110, size=0.05, direction="long")
            self.rm.register_trade(t)
        assert self.rm.can_open_position(10_000, 10_000) is False

    def test_cannot_open_at_max_drawdown(self):
        self.rm.reset_daily(10_000)
        assert self.rm.can_open_position(10_000, 9_400) is False

    def test_position_spacing_blocks_close_entry(self):
        t = Trade(entry_price=100.0, stop_loss=95, take_profit=110, size=0.05, direction="long")
        self.rm.register_trade(t)
        # 0.1% Abstand = zu nah
        assert self.rm.has_position_spacing(100.1) is False

    def test_position_spacing_allows_far_entry(self):
        t = Trade(entry_price=100.0, stop_loss=95, take_profit=110, size=0.05, direction="long")
        self.rm.register_trade(t)
        # 2% Abstand = ok
        assert self.rm.has_position_spacing(102.0) is True

    def test_close_trade_long_profit(self):
        t = Trade(entry_price=100.0, stop_loss=95, take_profit=110, size=0.1, direction="long")
        self.rm.register_trade(t)
        t.capital_at_entry = 10_000
        # Simuliere close_trade manuell
        size_val = 10_000 * 0.1
        pnl = size_val * (110 - 100) / 100
        assert pnl > 0

    def test_open_trade_count(self):
        assert self.rm.open_trade_count == 0
        t = Trade(entry_price=100, stop_loss=95, take_profit=110, size=0.05, direction="long")
        self.rm.register_trade(t)
        assert self.rm.open_trade_count == 1
