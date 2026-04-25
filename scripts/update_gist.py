#!/usr/bin/env python3
"""
update_gist.py  –  Laeuft als Railway Cron (0 * * * *)

Berechnet Daytrading-Picks (ATR, Volumen, Beta) + Quality-Picks
und schreibt das Ergebnis als JSON in ein GitHub Gist.
Trading-Bor liest dieses Gist statt die REST-API direkt aufzurufen.

Env-Variablen (Railway):
  GITHUB_TOKEN  –  PAT mit Gist read+write Scope
  GIST_ID       –  Gist-ID (beim ersten Run leer lassen → wird ausgegeben)

Dieses Skript gehoert in das Repo MB-AktienScreener-Railway.
"""

import json
import os
import sys
import time
from datetime import datetime, timezone

import pandas as pd
import requests
import yfinance as yf

# Bestehende Screener-Logik wiederverwenden
from screener import WATCHLIST, calc_fair_value, calc_score

GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "")
GIST_ID = os.environ.get("GIST_ID", "")
GIST_FILENAME = "stocksmb_picks.json"


# ── ATR-Berechnung ────────────────────────────────────────────

def calc_atr_pct(ticker: str, period: int = 14) -> float:
    """Berechnet ATR% (Average True Range in % des Kurses) ueber 'period' Tage."""
    try:
        df = yf.Ticker(ticker).history(period=f"{period + 5}d")
        if df is None or len(df) < period:
            return 0.0
        df["tr"] = pd.concat([
            df["High"] - df["Low"],
            (df["High"] - df["Close"].shift(1)).abs(),
            (df["Low"] - df["Close"].shift(1)).abs(),
        ], axis=1).max(axis=1)
        atr = df["tr"].tail(period).mean()
        price = df["Close"].iloc[-1]
        return round(atr / price * 100, 2) if price > 0 else 0.0
    except Exception:
        return 0.0


# ── Daytrading-Picks ──────────────────────────────────────────

def calc_daytrading_picks(top_n: int = 20) -> list[dict]:
    """
    Berechnet Daytrading-Picks aus der bestehenden WATCHLIST.
    Score: Kombination aus Volumen, ATR% und Beta.
    """
    results = []

    for tkr in WATCHLIST:
        try:
            info = yf.Ticker(tkr).info
            price = info.get("currentPrice") or info.get("regularMarketPrice", 0)
            if not price or price < 5:
                time.sleep(0.5)
                continue

            avg_vol = info.get("averageVolume", 0) or 0
            volume_m = round(avg_vol * price / 1_000_000, 1)
            beta = float(info.get("beta") or 1.0)
            mktcap_b = round((info.get("marketCap", 0) or 0) / 1e9, 1)

            if volume_m < 5.0 or mktcap_b < 2.0:
                time.sleep(0.5)
                continue

            atr_pct = calc_atr_pct(tkr)
            if atr_pct == 0.0:
                atr_pct = round(beta * 0.9, 2)

            score = min(100, int(
                min(volume_m / 5.0, 40) +
                min(atr_pct * 10, 30) +
                min(beta * 10, 30)
            ))

            results.append({
                "ticker": tkr,
                "name": info.get("shortName", tkr)[:28],
                "price": round(price, 2),
                "score": score,
                "atr_pct": atr_pct,
                "volume_m": volume_m,
                "beta": round(beta, 2),
                "mktcap_b": mktcap_b,
                "sector": info.get("sector", ""),
                "typ": "Aktie",
            })

            print(f"  {tkr:<6} score={score} atr={atr_pct:.1f}% vol={volume_m:.0f}M")
            time.sleep(0.8)

        except Exception as exc:
            print(f"  {tkr}: {exc}")
            time.sleep(1.0)

    results.sort(key=lambda x: x["score"], reverse=True)
    return results[:top_n]


# ── Quality-Picks (bestehende Screener-Logik) ─────────────────

def calc_quality_picks(top_n: int = 5) -> list[dict]:
    """Fundamentale Qualitaets-Picks mit Discount zum Fair Value."""
    results = []

    for tkr in WATCHLIST:
        try:
            info = yf.Ticker(tkr).info
            price = info.get("currentPrice") or info.get("regularMarketPrice", 0)
            if not price:
                time.sleep(1.0)
                continue

            score = calc_score(info)
            fv = calc_fair_value(info)

            if score >= 65 and fv and price < fv * 0.95:
                discount = (fv - price) / fv * 100
                results.append({
                    "ticker": tkr,
                    "name": info.get("shortName", tkr)[:28],
                    "price": round(price, 2),
                    "score": score,
                    "fair_value": fv,
                    "discount_pct": round(discount, 1),
                    "sector": info.get("sector", ""),
                    "mktcap_b": round((info.get("marketCap", 0) or 0) / 1e9, 1),
                })
            time.sleep(1.0)

        except Exception as exc:
            print(f"  {tkr}: {exc}")
            time.sleep(1.0)

    results.sort(key=lambda x: x["score"] * x["discount_pct"], reverse=True)
    return results[:top_n]


# ── GitHub Gist schreiben ─────────────────────────────────────

def write_gist(payload: dict) -> str:
    """Schreibt payload ins Gist. Erstellt ein neues Gist falls GIST_ID leer."""
    if not GITHUB_TOKEN:
        raise RuntimeError("GITHUB_TOKEN Env-Variable fehlt!")

    headers = {
        "Authorization": f"token {GITHUB_TOKEN}",
        "Accept": "application/vnd.github+json",
    }
    body = {
        "description": "StocksMB Picks – auto-updated hourly by Railway Cron",
        "public": False,
        "files": {
            GIST_FILENAME: {
                "content": json.dumps(payload, ensure_ascii=False, indent=2)
            }
        },
    }

    if GIST_ID:
        resp = requests.patch(
            f"https://api.github.com/gists/{GIST_ID}",
            json=body, headers=headers, timeout=15,
        )
    else:
        resp = requests.post(
            "https://api.github.com/gists",
            json=body, headers=headers, timeout=15,
        )

    resp.raise_for_status()
    new_id = resp.json()["id"]

    if not GIST_ID:
        print(f"\n{'='*55}")
        print(f"  GIST ERSTELLT!")
        print(f"  GIST_ID = {new_id}")
        print(f"  Trage diesen Wert als Env-Variable in Railway ein.")
        print(f"{'='*55}\n")

    return new_id


# ── Main ──────────────────────────────────────────────────────

if __name__ == "__main__":
    print("=== StocksMB Gist Updater ===")
    print(f"Start: {datetime.now(timezone.utc).isoformat()}\n")

    print("[1/2] Berechne Daytrading-Picks...")
    dt_picks = calc_daytrading_picks(top_n=20)
    print(f"  -> {len(dt_picks)} Titel\n")

    print("[2/2] Berechne Quality-Picks...")
    q_picks = calc_quality_picks(top_n=5)
    print(f"  -> {len(q_picks)} Titel\n")

    payload = {
        "updated": datetime.now(timezone.utc).isoformat(),
        "daytrading_picks": dt_picks,
        "quality_picks": q_picks,
    }

    gist_id = write_gist(payload)
    print(f"Gist aktualisiert: https://gist.github.com/{gist_id}")
    print("Fertig.")
    sys.exit(0)
