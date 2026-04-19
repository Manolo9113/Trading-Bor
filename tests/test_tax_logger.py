"""Tests fuer TaxTradeLogger (Abgeltungssteuer, FIFO)."""

import csv

from src.tax.trade_logger import TaxTradeLogger, ABGELTUNGSSTEUER, SOLI


class TestBuy:
    def setup_method(self):
        self.log = TaxTradeLogger(output_dir="/tmp/test_tax_buy")

    def test_creates_kauf_trade(self):
        t = self.log.record_buy("TSLA", qty=10, price=245.50)
        assert t.transaktionstyp == "Kauf"
        assert t.symbol == "TSLA"
        assert t.anzahl == 10

    def test_kurswert(self):
        t = self.log.record_buy("AAPL", qty=5, price=200.0)
        assert abs(t.kurswert - 1000.0) < 0.01

    def test_no_tax_on_buy(self):
        t = self.log.record_buy("NVDA", qty=2, price=500.0)
        assert t.steuer_gesamt == 0.0
        assert t.realisierter_gv_eur == 0.0

    def test_nettobetrag_includes_commission(self):
        t = self.log.record_buy("META", qty=10, price=100.0, commission=5.0)
        assert abs(t.nettobetrag - 1005.0) < 0.01

    def test_fx_rate_applied(self):
        t = self.log.record_buy("TSLA", qty=10, price=250.0, fx_rate=0.92)
        assert abs(t.nettobetrag_eur - 2500.0 * 0.92) < 0.01


class TestSell:
    def setup_method(self):
        self.log = TaxTradeLogger(output_dir="/tmp/test_tax_sell")

    def test_basic_gain(self):
        self.log.record_buy("TSLA", qty=10, price=200.0, fx_rate=1.0)
        t = self.log.record_sell("TSLA", qty=10, price=250.0, fx_rate=1.0)
        assert abs(t.realisierter_gv_eur - 500.0) < 0.01

    def test_tax_calculated_on_gain(self):
        self.log.record_buy("AAPL", qty=5, price=100.0, fx_rate=1.0)
        t = self.log.record_sell("AAPL", qty=5, price=200.0, fx_rate=1.0)
        gain = 500.0
        assert abs(t.steuer_kapitalertrag - gain * ABGELTUNGSSTEUER) < 0.01
        assert abs(t.steuer_soli - gain * ABGELTUNGSSTEUER * SOLI) < 0.01

    def test_loss_no_tax(self):
        self.log.record_buy("AMD", qty=10, price=300.0, fx_rate=1.0)
        t = self.log.record_sell("AMD", qty=10, price=200.0, fx_rate=1.0)
        assert t.realisierter_gv_eur < 0
        assert t.steuer_gesamt == 0.0

    def test_fifo_uses_oldest_lot_first(self):
        self.log.record_buy("NVDA", qty=5, price=100.0, fx_rate=1.0)
        self.log.record_buy("NVDA", qty=5, price=200.0, fx_rate=1.0)
        t = self.log.record_sell("NVDA", qty=5, price=150.0, fx_rate=1.0)
        # FIFO: oldest lot cost 5*100=500, proceeds 5*150=750, gain=250
        assert abs(t.realisierter_gv_eur - 250.0) < 0.01

    def test_no_lot_zero_gv(self):
        t = self.log.record_sell("UNKNOWN", qty=1, price=100.0)
        assert t.realisierter_gv_eur == 0.0

    def test_fx_rate_on_sell(self):
        self.log.record_buy("MSFT", qty=2, price=100.0, fx_rate=0.90)
        t = self.log.record_sell("MSFT", qty=2, price=200.0, fx_rate=0.92)
        proceeds_eur = 2 * 200.0 * 0.92
        cost_eur = 2 * 100.0 * 0.90
        assert abs(t.realisierter_gv_eur - (proceeds_eur - cost_eur)) < 0.01


class TestCsvExport:
    def setup_method(self):
        self.log = TaxTradeLogger(output_dir="/tmp/test_tax_csv")

    def test_creates_file(self):
        self.log.record_buy("TSLA", qty=1, price=200.0)
        path = self.log.export_csv("/tmp/test_tax_csv/export_test.csv")
        assert path.exists()

    def test_header_contains_required_columns(self):
        self.log.record_buy("TSLA", qty=1, price=200.0)
        path = self.log.export_csv("/tmp/test_tax_csv/header_test.csv")
        with open(path, encoding="utf-8-sig") as f:
            fields = csv.DictReader(f, delimiter=";").fieldnames
        assert "Handelsdatum" in fields
        assert "Realisierter_GV_EUR" in fields
        assert "Steuer_Gesamt" in fields
        assert "ISIN" in fields

    def test_row_count_matches_trades(self):
        self.log.record_buy("TSLA", qty=5, price=200.0)
        self.log.record_sell("TSLA", qty=5, price=250.0, fx_rate=1.0)
        path = self.log.export_csv("/tmp/test_tax_csv/rows_test.csv")
        with open(path, encoding="utf-8-sig") as f:
            rows = list(csv.DictReader(f, delimiter=";"))
        assert len(rows) == 2

    def test_default_filename_contains_year(self, tmp_path):
        lg = TaxTradeLogger(output_dir=str(tmp_path))
        lg.record_buy("AAPL", qty=1, price=100.0)
        path = lg.export_csv()
        assert "steuer_trades_" in path.name
        assert path.exists()


class TestJahresabschluss:
    def setup_method(self):
        self.log = TaxTradeLogger(output_dir="/tmp/test_tax_jahr")

    def test_counts(self):
        self.log.record_buy("TSLA", qty=10, price=200.0)
        self.log.record_buy("AAPL", qty=5, price=100.0)
        self.log.record_sell("TSLA", qty=10, price=250.0, fx_rate=1.0)
        s = self.log.jahresabschluss()
        assert s["anzahl_kaeufe"] == 2
        assert s["anzahl_verkaeufe"] == 1

    def test_gains_summed(self):
        self.log.record_buy("NVDA", qty=2, price=100.0, fx_rate=1.0)
        self.log.record_sell("NVDA", qty=2, price=200.0, fx_rate=1.0)
        s = self.log.jahresabschluss()
        assert abs(s["gewinne_eur"] - 200.0) < 0.01

    def test_below_freistellung_no_tax(self):
        self.log.record_buy("AAPL", qty=10, price=100.0, fx_rate=1.0)
        # Gain = 500 EUR < 1000 EUR Freistellungsauftrag
        self.log.record_sell("AAPL", qty=10, price=150.0, fx_rate=1.0)
        s = self.log.jahresabschluss()
        assert s["steuerpflichtiger_gewinn_eur"] == 0.0
        assert s["steuer_gesamt_eur"] == 0.0

    def test_above_freistellung_correct_tax(self):
        self.log.record_buy("TSLA", qty=10, price=100.0, fx_rate=1.0)
        # Gain = 2000 EUR, steuerpflichtig = 2000 - 1000 = 1000 EUR
        self.log.record_sell("TSLA", qty=10, price=300.0, fx_rate=1.0)
        s = self.log.jahresabschluss()
        assert abs(s["steuerpflichtiger_gewinn_eur"] - 1000.0) < 0.01
        expected = 1000.0 * ABGELTUNGSSTEUER * (1 + SOLI)
        assert abs(s["steuer_gesamt_eur"] - expected) < 0.01

    def test_print_no_crash(self, capsys):
        self.log.record_buy("X", qty=1, price=100.0)
        self.log.print_jahresabschluss()
        assert "EUR" in capsys.readouterr().out
