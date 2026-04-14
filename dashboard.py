# -*- coding: utf-8 -*-
"""
dashboard.py - Flask web dashboard (port 5000)
Trading bot durumunu tarayicidan goruntulemeye yarar.
"""

import sys
import os
from datetime import datetime, date, timedelta
from flask import Flask, render_template

# Proje klasorunu path'e ekle
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from data import get_price_data, add_indicators
from strategy import sma_crossover_signals
from broker import get_account, is_market_open

app = Flask(__name__)

SYMBOLS = ["AAPL", "MSFT", "GLD", "USO"]


def get_signal_label(position_series):
    """
    Son crossover sinyalini dondurur: BUY, SELL ya da HOLD.
    position kolonunda +2 = BUY crossover, -2 = SELL crossover.
    Son gune kadar hic crossover yoksa HOLD.
    """
    # Son gecerli sinyal
    last_signal = 0
    for val in reversed(position_series.dropna().tolist()):
        if val == 2.0:
            last_signal = 2
            break
        elif val == -2.0:
            last_signal = -2
            break
    if last_signal == 2:
        return "BUY"
    elif last_signal == -2:
        return "SELL"
    return "HOLD"


def build_symbol_data():
    """Her sembol icin metrik sozlugu listesi olusturur."""
    end   = date.today().strftime("%Y-%m-%d")
    start = (date.today() - timedelta(days=120)).strftime("%Y-%m-%d")

    rows = []
    for sym in SYMBOLS:
        try:
            df = get_price_data(sym, start, end)
            df = add_indicators(df, sma_periods=[20, 50])
            df = sma_crossover_signals(df, fast=20, slow=50)

            last = df.iloc[-1]

            def fmt(val, decimals=2):
                try:
                    return f"{float(val):.{decimals}f}"
                except Exception:
                    return "N/A"

            signal = get_signal_label(df["position"])

            rows.append({
                "symbol": sym,
                "price":  fmt(last["close"]),
                "sma20":  fmt(last.get("sma20", float("nan"))),
                "sma50":  fmt(last.get("sma50", float("nan"))),
                "rsi":    fmt(last.get("rsi",   float("nan")), 1),
                "atr":    fmt(last.get("atr",   float("nan")), 3),
                "signal": signal,
                "error":  None,
            })
        except Exception as exc:
            rows.append({
                "symbol": sym,
                "price":  "N/A",
                "sma20":  "N/A",
                "sma50":  "N/A",
                "rsi":    "N/A",
                "atr":    "N/A",
                "signal": "HOLD",
                "error":  str(exc),
            })
    return rows


@app.route("/")
def index():
    # --- Sembol verileri ---
    symbol_rows = build_symbol_data()

    # --- Hesap bilgisi ---
    account   = None
    acct_err  = None
    try:
        account = get_account()
    except Exception as exc:
        acct_err = str(exc)

    # --- Market durumu ---
    market_open = False
    market_err  = None
    try:
        market_open = is_market_open()
    except Exception as exc:
        market_err = str(exc)

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    return render_template(
        "index.html",
        symbol_rows=symbol_rows,
        account=account,
        acct_err=acct_err,
        market_open=market_open,
        market_err=market_err,
        now=now,
    )


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False)
