"""Dash Live-Dashboard mit Fibonacci-Linien und Trade-Signalen."""

from __future__ import annotations

import logging

import pandas as pd

try:
    import dash
    from dash import dcc, html
    from dash.dependencies import Input, Output
    import plotly.graph_objects as go
    import dash_bootstrap_components as dbc
    DASH_AVAILABLE = True
except ImportError:
    DASH_AVAILABLE = False

_logger = logging.getLogger(__name__)


def create_app(config: dict):
    """Erstellt und konfiguriert die Dash-App."""
    if not DASH_AVAILABLE:
        raise ImportError(
            "dash und plotly sind erforderlich: "
            "pip install dash plotly dash-bootstrap-components"
        )

    from ..exchange.connector import ExchangeConnector
    from ..indicators.fibonacci import FibonacciCalculator
    from ..indicators.patterns import PatternDetector
    from ..strategies.fibonacci_confluence import FibonacciConfluenceStrategy
    from ..risk.risk_manager import RiskManager

    connector = ExchangeConnector(config["exchange"])
    fib_calc = FibonacciCalculator(config["fibonacci"])
    pattern_det = PatternDetector(config["patterns"])
    risk_mgr = RiskManager(config["risk"])
    strategy = FibonacciConfluenceStrategy(fib_calc, pattern_det, risk_mgr, config)

    symbol = config["trading"]["symbol"]
    timeframe = config["trading"]["timeframe"]

    app = dash.Dash(
        __name__,
        external_stylesheets=[dbc.themes.DARKLY],
        title="Trading Bot Dashboard",
    )

    app.layout = dbc.Container([
        dbc.Row([
            dbc.Col(
                html.H2(f"Trading Bot - {symbol} {timeframe}", className="text-light mt-3"),
                width=8,
            ),
            dbc.Col(
                dbc.Badge(id="signal-badge", color="secondary", className="mt-4 fs-6"),
                width=4,
                className="text-end",
            ),
        ]),
        dbc.Row([
            dbc.Col(dcc.Graph(id="price-chart", style={"height": "500px"}), width=12),
        ]),
        dbc.Row([
            dbc.Col([
                html.H5("Letzte Signale", className="text-light mt-3"),
                html.Div(id="signal-log", className="text-light"),
            ], width=12),
        ]),
        dcc.Interval(id="interval", interval=60_000, n_intervals=0),
    ], fluid=True, className="bg-dark min-vh-100")

    @app.callback(
        Output("price-chart", "figure"),
        Output("signal-badge", "children"),
        Output("signal-badge", "color"),
        Output("signal-log", "children"),
        Input("interval", "n_intervals"),
    )
    def update_chart(_n):
        df = connector.fetch_ohlcv(symbol, timeframe, limit=100)
        if df is None or df.empty:
            empty_fig = go.Figure()
            empty_fig.update_layout(template="plotly_dark", title="Keine Daten")
            return empty_fig, "KEIN SIGNAL", "secondary", ""

        fig = _build_chart(df, fib_calc, symbol)
        signal = strategy.generate_signal(df)

        if signal and signal.is_entry:
            badge_text = f"{signal.signal_type.value} | Conf: {signal.confidence:.0%}"
            badge_color = "success" if signal.signal_type.value == "BUY" else "danger"
            log_text = html.Ul([
                html.Li(f"{signal.signal_type.value} @ {signal.price:.4f}"),
                html.Li(f"Stop-Loss: {signal.stop_loss:.4f}"),
                html.Li(f"Take-Profit: {signal.take_profit:.4f}"),
                html.Li(f"R:R = {signal.risk_reward:.2f}"),
                html.Li(f"Grund: {signal.reason}"),
            ])
        else:
            badge_text = "KEIN SIGNAL"
            badge_color = "secondary"
            log_text = html.P("Warte auf Confluence-Signal...")

        return fig, badge_text, badge_color, log_text

    return app


def _build_chart(
    df: pd.DataFrame,
    fib_calc,
    symbol: str,
):
    """Baut Candlestick-Chart mit Fibonacci-Linien."""
    fig = go.Figure()

    fig.add_trace(go.Candlestick(
        x=df.index,
        open=df["open"],
        high=df["high"],
        low=df["low"],
        close=df["close"],
        name=symbol,
        increasing_line_color="#26a69a",
        decreasing_line_color="#ef5350",
    ))

    fib_colors = {
        0.0: "#ffffff", 0.236: "#90caf9", 0.382: "#42a5f5",
        0.5: "#ffeb3b", 0.618: "#ff9800", 0.786: "#ef5350", 1.0: "#ffffff",
    }
    for zone in fib_calc.calculate(df, n_recent=1):
        for lvl in zone.retracement_levels:
            fig.add_hline(
                y=lvl.price,
                line_dash="dot",
                line_color=fib_colors.get(lvl.ratio, "#aaaaaa"),
                line_width=1,
                annotation_text=f"Fib {lvl.label} ({lvl.price:.2f})",
                annotation_font_color=fib_colors.get(lvl.ratio, "#aaaaaa"),
            )

    fig.update_layout(
        template="plotly_dark",
        xaxis_rangeslider_visible=False,
        margin=dict(l=10, r=10, t=30, b=10),
        showlegend=False,
    )
    return fig
