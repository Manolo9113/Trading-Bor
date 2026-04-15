# Trading Bot – Fibonacci & Chart-Pattern Confluence

Ein modularer, produktionsreifer Trading Bot für Crypto-Märkte (CCXT-kompatibel).

## Features

- **Fibonacci-Kalkulator** mit WMA-Variante (Retracement + Extension)
- **Chart-Pattern-Erkennung** via `scipy.signal.argrelextrema` (Engulfing, Hammer, Double Top/Bottom, Head & Shoulders)
- **Confluence-Signale** – Trade nur wenn Fib-Level + Pattern zusammentreffen
- **Risk-Manager** – Positionsgröße, Stop-Loss (ATR-basiert), Max-Drawdown
- **Backtesting-Modul** mit Performance-Metriken (Sharpe, Sortino, Win-Rate, Max-DD)
- **Live-Dashboard** mit Dash (Fib-Lines + Trades in Echtzeit)
- **YAML-Config** – alles konfigurierbar ohne Code zu ändern
- **Docker-ready** für 24/7-Betrieb

## Projektstruktur

```
trading-bor/
├── config/
│   └── config.example.yaml    # Konfigurationsvorlage
├── src/
│   ├── indicators/
│   │   ├── fibonacci.py       # FibonacciCalculator (inkl. WMA)
│   │   └── patterns.py        # Chart-Pattern-Erkennung
│   ├── strategies/
│   │   ├── base_strategy.py   # Abstrakte Basis-Klasse
│   │   └── fibonacci_confluence.py  # Fib + Pattern Confluence
│   ├── risk/
│   │   └── risk_manager.py    # Positionsgröße, Stop-Loss, Drawdown
│   ├── backtest/
│   │   └── backtester.py      # Backtesting + Metriken
│   ├── exchange/
│   │   └── connector.py       # CCXT Exchange-Connector
│   ├── dashboard/
│   │   └── app.py             # Dash Live-Dashboard
│   └── utils/
│       └── logger.py          # Strukturiertes Logging
├── tests/
│   ├── test_fibonacci.py
│   └── test_patterns.py
├── main.py                    # Einstiegspunkt
├── requirements.txt
├── Dockerfile
└── docker-compose.yml
```

## Schnellstart

### 1. Installation

```bash
git clone https://github.com/manolo9113/trading-bor.git
cd trading-bor
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 2. Konfiguration

```bash
cp config/config.example.yaml config/config.yaml
# API-Keys und Parameter in config/config.yaml eintragen
```

### 3. Backtest ausführen

```bash
python main.py --mode backtest
```

### 4. Live-Trading (Testnet empfohlen!)

```bash
python main.py --mode live
```

### 5. Dashboard starten

```bash
python main.py --mode dashboard
# Öffne http://localhost:8050
```

### 6. Docker

```bash
docker-compose up -d
```

## Konfigurationsbeispiel

Siehe `config/config.example.yaml` für alle verfügbaren Parameter.

## Tests

```bash
pytest tests/ -v
```

## Disclaimer

> Dieser Bot dient ausschließlich zu Bildungszwecken. Trading birgt erhebliche finanzielle Risiken. Nutze immer zuerst Testnets/Paper-Trading bevor du echtes Kapital einsetzt.
