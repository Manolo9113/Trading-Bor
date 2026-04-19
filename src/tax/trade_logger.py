"""German tax-compliant trade history logger (Abgeltungssteuer / Kapitalertragsteuer).

Implements:
  - FIFO (First-In, First-Out) cost basis calculation
  - Abgeltungssteuer 25% on realized gains
  - Solidaritaetszuschlag 5.5% of Abgeltungssteuer
  - Freistellungsauftrag 1.000 EUR (ab 2023)
  - CSV export compatible with WISO Steuer / Elster

Usage:
    logger = TaxTradeLogger(output_dir="data/tax")
    logger.record_buy("TSLA", qty=10, price=245.50, commission=1.00,
                      fx_rate=0.92, isin="US88160R1014")
    logger.record_sell("TSLA", qty=10, price=280.00, commission=1.00,
                       fx_rate=0.91)
    logger.export_csv()
    logger.print_jahresabschluss()
"""

from __future__ import annotations

import csv
import logging
from collections import deque
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional


ABGELTUNGSSTEUER = 0.25
SOLI = 0.055
FREISTELLUNGSAUFTRAG = 1000.0  # EUR per year since 2023


@dataclass
class TaxTrade:
    """Einzelner Trade fuer die Steuerdokumentation."""
    datum: str
    symbol: str
    isin: str
    name: str
    transaktionstyp: str       # Kauf / Verkauf
    anzahl: float
    kurs: float
    kurswert: float            # anzahl * kurs (Originalwaehrung)
    waehrung: str
    wechselkurs_eur: float     # Multiplikator zu EUR (z.B. 0.92 fuer USD->EUR)
    provision: float
    nettobetrag: float         # kurswert +/- provision (Originalwaehrung)
    nettobetrag_eur: float
    realisierter_gv_eur: float
    steuer_kapitalertrag: float
    steuer_soli: float
    steuer_gesamt: float
    order_id: str
    notiz: str


@dataclass
class _Lot:
    qty: float
    cost_per_share_eur: float


class TaxTradeLogger:
    """
    Verfolgt alle Kaeufe und Verkaeufe, berechnet Steuern (FIFO)
    und exportiert eine CSV fuer die deutsche Steuererklarung.
    """

    CSV_FIELDS = [
        "Handelsdatum",
        "Symbol",
        "ISIN",
        "Wertpapier",
        "Transaktionstyp",
        "Anzahl",
        "Kurs",
        "Kurswert",
        "Waehrung",
        "Wechselkurs_EUR",
        "Provision",
        "Nettobetrag",
        "Nettobetrag_EUR",
        "Realisierter_GV_EUR",
        "Steuer_Kapitalertrag",
        "Steuer_Soli",
        "Steuer_Gesamt",
        "Order_ID",
        "Notiz",
    ]

    def __init__(self, output_dir: str = "data/tax", base_currency: str = "USD") -> None:
        self._log = logging.getLogger(self.__class__.__name__)
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.base_currency = base_currency
        self._lots: dict[str, deque[_Lot]] = {}
        self._trades: list[TaxTrade] = []

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def record_buy(
        self,
        symbol: str,
        qty: float,
        price: float,
        commission: float = 0.0,
        timestamp: Optional[datetime] = None,
        isin: str = "",
        name: str = "",
        currency: str = "",
        fx_rate: float = 1.0,
        order_id: str = "",
        note: str = "",
    ) -> TaxTrade:
        """Kauf erfassen und FIFO-Lot anlegen."""
        ts = timestamp or datetime.now()
        ccy = currency or self.base_currency
        kurswert = qty * price
        netto = kurswert + commission
        netto_eur = netto * fx_rate
        cost_per_share_eur = netto_eur / qty if qty else 0.0

        if symbol not in self._lots:
            self._lots[symbol] = deque()
        self._lots[symbol].append(_Lot(qty=qty, cost_per_share_eur=cost_per_share_eur))

        trade = TaxTrade(
            datum=ts.strftime("%Y-%m-%d %H:%M:%S"),
            symbol=symbol, isin=isin, name=name or symbol,
            transaktionstyp="Kauf",
            anzahl=qty, kurs=price, kurswert=kurswert,
            waehrung=ccy, wechselkurs_eur=fx_rate,
            provision=commission,
            nettobetrag=netto, nettobetrag_eur=netto_eur,
            realisierter_gv_eur=0.0,
            steuer_kapitalertrag=0.0, steuer_soli=0.0, steuer_gesamt=0.0,
            order_id=order_id, notiz=note,
        )
        self._trades.append(trade)
        self._log.info(
            f"Kauf: {qty}x {symbol} @ {price:.2f} {ccy} "
            f"(Einstand {cost_per_share_eur:.4f} EUR/Stk)"
        )
        return trade

    def record_sell(
        self,
        symbol: str,
        qty: float,
        price: float,
        commission: float = 0.0,
        timestamp: Optional[datetime] = None,
        isin: str = "",
        name: str = "",
        currency: str = "",
        fx_rate: float = 1.0,
        order_id: str = "",
        note: str = "",
    ) -> TaxTrade:
        """Verkauf erfassen, G/V (FIFO) und Steuern berechnen."""
        ts = timestamp or datetime.now()
        ccy = currency or self.base_currency
        kurswert = qty * price
        netto = kurswert - commission
        netto_eur = netto * fx_rate

        gv_eur = self._fifo_pnl(symbol, qty, netto_eur)
        steuerpflichtig = max(0.0, gv_eur)
        steuer_k = round(steuerpflichtig * ABGELTUNGSSTEUER, 2)
        steuer_s = round(steuer_k * SOLI, 2)

        trade = TaxTrade(
            datum=ts.strftime("%Y-%m-%d %H:%M:%S"),
            symbol=symbol, isin=isin, name=name or symbol,
            transaktionstyp="Verkauf",
            anzahl=qty, kurs=price, kurswert=kurswert,
            waehrung=ccy, wechselkurs_eur=fx_rate,
            provision=commission,
            nettobetrag=netto, nettobetrag_eur=netto_eur,
            realisierter_gv_eur=round(gv_eur, 2),
            steuer_kapitalertrag=steuer_k,
            steuer_soli=steuer_s,
            steuer_gesamt=round(steuer_k + steuer_s, 2),
            order_id=order_id, notiz=note,
        )
        self._trades.append(trade)
        self._log.info(
            f"Verkauf: {qty}x {symbol} @ {price:.2f} {ccy} | "
            f"G/V {gv_eur:+.2f} EUR | Steuer {trade.steuer_gesamt:.2f} EUR"
        )
        return trade

    def export_csv(self, filepath: Optional[str] = None) -> Path:
        """Exportiert alle Trades als Semikolon-CSV (UTF-8 BOM fuer Excel)."""
        if filepath:
            path = Path(filepath)
        else:
            year = datetime.now().year
            path = self.output_dir / f"steuer_trades_{year}.csv"
        path.parent.mkdir(parents=True, exist_ok=True)

        with open(path, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.DictWriter(f, fieldnames=self.CSV_FIELDS, delimiter=";")
            w.writeheader()
            for t in self._trades:
                w.writerow({
                    "Handelsdatum":         t.datum,
                    "Symbol":               t.symbol,
                    "ISIN":                 t.isin,
                    "Wertpapier":           t.name,
                    "Transaktionstyp":      t.transaktionstyp,
                    "Anzahl":               f"{t.anzahl:.4f}",
                    "Kurs":                 f"{t.kurs:.4f}",
                    "Kurswert":             f"{t.kurswert:.2f}",
                    "Waehrung":             t.waehrung,
                    "Wechselkurs_EUR":      f"{t.wechselkurs_eur:.4f}",
                    "Provision":            f"{t.provision:.2f}",
                    "Nettobetrag":          f"{t.nettobetrag:.2f}",
                    "Nettobetrag_EUR":      f"{t.nettobetrag_eur:.2f}",
                    "Realisierter_GV_EUR":  f"{t.realisierter_gv_eur:.2f}",
                    "Steuer_Kapitalertrag": f"{t.steuer_kapitalertrag:.2f}",
                    "Steuer_Soli":          f"{t.steuer_soli:.2f}",
                    "Steuer_Gesamt":        f"{t.steuer_gesamt:.2f}",
                    "Order_ID":             t.order_id,
                    "Notiz":                t.notiz,
                })

        self._log.info(f"CSV exportiert: {path} ({len(self._trades)} Trades)")
        return path

    def jahresabschluss(self, year: Optional[int] = None) -> dict:
        """Jahresuebersicht fuer Anlage KAP der Steuererklarung."""
        yr = year or datetime.now().year
        yr_str = str(yr)
        verkaeufe = [
            t for t in self._trades
            if t.transaktionstyp == "Verkauf" and t.datum.startswith(yr_str)
        ]
        kaeufe = [
            t for t in self._trades
            if t.transaktionstyp == "Kauf" and t.datum.startswith(yr_str)
        ]
        gewinne = sum(t.realisierter_gv_eur for t in verkaeufe if t.realisierter_gv_eur > 0)
        verluste = sum(t.realisierter_gv_eur for t in verkaeufe if t.realisierter_gv_eur < 0)
        netto_gv = gewinne + verluste
        steuerpflichtig = max(0.0, netto_gv - FREISTELLUNGSAUFTRAG)
        steuer_k = steuerpflichtig * ABGELTUNGSSTEUER
        steuer_s = steuer_k * SOLI
        return {
            "jahr":                        yr,
            "anzahl_kaeufe":               len(kaeufe),
            "anzahl_verkaeufe":            len(verkaeufe),
            "gewinne_eur":                 round(gewinne, 2),
            "verluste_eur":                round(verluste, 2),
            "netto_gv_eur":                round(netto_gv, 2),
            "freistellungsauftrag_eur":    FREISTELLUNGSAUFTRAG,
            "steuerpflichtiger_gewinn_eur": round(steuerpflichtig, 2),
            "abgeltungssteuer_eur":        round(steuer_k, 2),
            "soli_eur":                    round(steuer_s, 2),
            "steuer_gesamt_eur":           round(steuer_k + steuer_s, 2),
        }

    def print_jahresabschluss(self, year: Optional[int] = None) -> None:
        s = self.jahresabschluss(year)
        sep = "=" * 52
        print(f"\n{sep}")
        print(f"  Jahresabschluss {s['jahr']}  –  Anlage KAP")
        print(sep)
        print(f"  Kaeufe:                   {s['anzahl_kaeufe']}")
        print(f"  Verkaeufe:                {s['anzahl_verkaeufe']}")
        print(f"  Gewinne:               {s['gewinne_eur']:>10.2f} EUR")
        print(f"  Verluste:              {s['verluste_eur']:>10.2f} EUR")
        print(f"  Netto G/V:             {s['netto_gv_eur']:>+10.2f} EUR")
        print(f"  Freistellungsauftrag:  {s['freistellungsauftrag_eur']:>10.2f} EUR")
        print(f"  Steuerpflichtiger Gew: {s['steuerpflichtiger_gewinn_eur']:>10.2f} EUR")
        print(f"  Abgeltungssteuer 25%:  {s['abgeltungssteuer_eur']:>10.2f} EUR")
        print(f"  Solidaritaetszuschlag: {s['soli_eur']:>10.2f} EUR")
        print(f"  Steuer gesamt:         {s['steuer_gesamt_eur']:>10.2f} EUR")
        print(f"{sep}\n")

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _fifo_pnl(self, symbol: str, qty_sold: float, net_proceeds_eur: float) -> float:
        """Berechnet realisierten Gewinn/Verlust nach FIFO."""
        lots = self._lots.get(symbol)
        if not lots:
            self._log.warning(
                f"FIFO: Keine Kauflots fuer {symbol}. "
                "Einstandspreis unbekannt – G/V wird als 0 berechnet."
            )
            return 0.0

        remaining = qty_sold
        total_cost_eur = 0.0
        while remaining > 1e-9 and lots:
            lot = lots[0]
            if lot.qty <= remaining:
                total_cost_eur += lot.qty * lot.cost_per_share_eur
                remaining -= lot.qty
                lots.popleft()
            else:
                total_cost_eur += remaining * lot.cost_per_share_eur
                lot.qty -= remaining
                remaining = 0.0

        if remaining > 1e-9:
            self._log.warning(
                f"FIFO: {remaining:.4f} Stueck {symbol} ohne Kauflot "
                "(Leerverkauf oder fehlende Kaufdaten)."
            )

        return net_proceeds_eur - total_cost_eur
