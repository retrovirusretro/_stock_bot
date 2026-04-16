# -*- coding: utf-8 -*-
"""
dashboard.py - Flask web dashboard (port 5000)
Trading bot durumunu tarayicidan goruntulemeye yarar.
"""

import sys
import os
from datetime import datetime, date, timedelta
from flask import Flask, render_template, jsonify
import pandas as pd

# Proje klasorunu path'e ekle
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from data import get_price_data, add_indicators, add_supertrend
from strategy import sma_crossover_signals, filtered_signals, supertrend_signals
from broker import get_account, is_market_open
import reporter
import screener

# Paper trader ile birebir aynı grup tanımları
CRISIS_ASSETS     = {"GLD", "SLV", "USO"}
MINING_ASSETS     = {"GDX", "GDXJ"}
SUPERTREND_ASSETS = {"XME", "COPX", "XLE", "XLB", "XLI", "QQQ", "DIA", "IWM", "AAPL", "MSFT"}

app = Flask(__name__)
app.config["SEND_FILE_MAX_AGE_DEFAULT"] = 0
app.jinja_env.auto_reload = True
app.config["TEMPLATES_AUTO_RELOAD"] = True

@app.after_request
def no_cache(response):
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response

SYMBOLS = [
    "GLD", "SLV", "USO", "GDX", "GDXJ", "XME", "COPX",
    "XLE", "XLB", "XLI",
    "QQQ", "DIA", "IWM",
    "AAPL", "MSFT",
]


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
    start = (date.today() - timedelta(days=300)).strftime("%Y-%m-%d")

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
    # Sayfa aninda yuklenir — sembol verileri JS ile async cekılir
    # Sadece hesap + market durumu senkron (hizli)
    account   = None
    acct_err  = None
    try:
        account = get_account()
    except Exception as exc:
        acct_err = str(exc)

    market_open = False
    market_err  = None
    try:
        market_open = is_market_open()
    except Exception as exc:
        market_err = str(exc)

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    return render_template(
        "index.html",
        symbols=SYMBOLS,
        account=account,
        acct_err=acct_err,
        market_open=market_open,
        market_err=market_err,
        now=now,
    )


@app.route("/api/symbol/<symbol>")
def api_symbol(symbol):
    """Tek sembol icin metrik JSON dondurur (async tablo yukleme icin)."""
    import time
    symbol = symbol.upper()
    last_exc = None
    for attempt in range(3):
        try:
            end   = date.today().strftime("%Y-%m-%d")
            start = (date.today() - timedelta(days=300)).strftime("%Y-%m-%d")
            df = get_price_data(symbol, start, end)
            df = add_indicators(df, sma_periods=[20, 50, 200])

            if symbol in SUPERTREND_ASSETS:
                df = add_supertrend(df)
                df = supertrend_signals(df)
                strategy_type = "ST"
            else:
                use_sma200 = symbol not in CRISIS_ASSETS
                df = filtered_signals(df, fast=20, slow=50, use_sma200=use_sma200)
                strategy_type = "SMA"

            last   = df.iloc[-1]
            signal = get_signal_label(df["position"])

            def fmt(val, d=2):
                try:
                    return f"{float(val):.{d}f}"
                except Exception:
                    return "N/A"

            return jsonify({
                "symbol":        symbol,
                "price":         fmt(last["close"]),
                "sma20":         fmt(last.get("sma20", float("nan"))),
                "sma50":         fmt(last.get("sma50", float("nan"))),
                "rsi":           fmt(last.get("rsi",   float("nan")), 1),
                "atr":           fmt(last.get("atr",   float("nan")), 3),
                "signal":        signal,
                "strategy_type": strategy_type,
                "error":         None,
            })
        except Exception as exc:
            last_exc = exc
            if attempt < 2:
                time.sleep(1)
    return jsonify({"symbol": symbol, "error": str(last_exc)}), 500


@app.route("/api/chart/<symbol>")
def api_chart_data(symbol):
    """Son 60 gunluk fiyat + SMA20 + SMA50 verisini Chart.js formatinda dondurur."""
    import time
    symbol = symbol.upper()
    last_exc = None
    for attempt in range(3):
        try:
            end   = datetime.now().strftime("%Y-%m-%d")
            start = (datetime.now() - timedelta(days=300)).strftime("%Y-%m-%d")
            df = get_price_data(symbol, start, end)
            df = add_indicators(df, sma_periods=[20, 50])
            df = df.tail(60).copy()
            df.index = df.index.strftime("%Y-%m-%d")

            prices = []
            sma20  = []
            sma50  = []

            for t, row in df.iterrows():
                v = row["close"]
                if pd.notna(v):
                    prices.append({"time": t, "value": round(float(v), 2)})
                v20 = row.get("sma20", float("nan"))
                if pd.notna(v20):
                    sma20.append({"time": t, "value": round(float(v20), 2)})
                v50 = row.get("sma50", float("nan"))
                if pd.notna(v50):
                    sma50.append({"time": t, "value": round(float(v50), 2)})

            return jsonify({"prices": prices, "sma20": sma20, "sma50": sma50, "symbol": symbol})
        except Exception as exc:
            last_exc = exc
            if attempt < 2:
                time.sleep(1)
    return jsonify({"error": str(last_exc), "symbol": symbol}), 500


@app.route("/chart/<symbol>")
def chart_data(symbol):
    """Son 60 gunluk fiyat + SMA20 + SMA50 + RSI + BUY/SELL sinyalleri JSON dondurur."""
    import time
    symbol = symbol.upper()
    last_exc = None
    for attempt in range(3):
      try:
        end   = datetime.now().strftime("%Y-%m-%d")
        start = (datetime.now() - timedelta(days=300)).strftime("%Y-%m-%d")
        df = get_price_data(symbol, start, end)
        df = add_indicators(df, sma_periods=[20, 50, 200])

        if symbol in SUPERTREND_ASSETS:
            df = add_supertrend(df)
            df = supertrend_signals(df)
            strategy_type = "ST"
        else:
            use_sma200 = symbol not in CRISIS_ASSETS
            df = filtered_signals(df, fast=20, slow=50, use_sma200=use_sma200)
            strategy_type = "SMA"

        df = df.tail(60).copy()
        df.index = df.index.strftime("%Y-%m-%d")

        buy_signals  = []
        sell_signals = []
        for t, row in df.iterrows():
            pos = row.get("position", 0)
            if pd.notna(pos):
                if pos == 2.0:
                    buy_signals.append({"x": t, "y": round(float(row["close"]), 2)})
                elif pos == -2.0:
                    sell_signals.append({"x": t, "y": round(float(row["close"]), 2)})

        def safe(col):
            if col not in df.columns:
                return [None] * len(df)
            return [round(float(x), 4) if not pd.isna(x) else None for x in df[col]]

        # ATR stop/TP seviyeleri: son kapanisa gore hesapla
        last_close = float(df["close"].iloc[-1])
        last_atr   = float(df["atr"].iloc[-1]) if "atr" in df.columns and not pd.isna(df["atr"].iloc[-1]) else None
        atr_stop = round(last_close - 2 * last_atr, 2) if last_atr else None
        atr_tp   = round(last_close + 4 * last_atr, 2) if last_atr else None

        return jsonify({
            "labels":        list(df.index),
            "close":         [round(float(x), 2) for x in df["close"]],
            "sma20":         safe("sma20"),
            "sma50":         safe("sma50"),
            "bb_upper":      safe("bb_upper"),
            "bb_lower":      safe("bb_lower"),
            "rsi":           safe("rsi"),
            "adx":           safe("adx"),
            "bb_pct":        safe("bb_pct"),
            "buy_signals":   buy_signals,
            "sell_signals":  sell_signals,
            "atr_stop":      atr_stop,
            "atr_tp":        atr_tp,
            "supertrend":    safe("supertrend"),
            "strategy_type": strategy_type,
            "symbol":        symbol,
        })
      except Exception as exc:
        last_exc = exc
        if attempt < 2:
            time.sleep(1)
    return jsonify({"error": str(last_exc), "symbol": symbol}), 500


@app.route("/api/screener")
def api_screener():
    """S&P500 screener sonuclarini dondurur. Cache yoksa arka planda baslatir."""
    try:
        cache, is_running = screener.get_or_trigger()
        return jsonify({
            "results":       cache["results"]       if cache else [],
            "timestamp":     cache["timestamp"]     if cache else None,
            "total_scanned": cache.get("total_scanned", 0) if cache else 0,
            "total_buy":     cache.get("total_buy",     0) if cache else 0,
            "is_running":    is_running,
            "error":         None,
        })
    except Exception as exc:
        return jsonify({"results": [], "is_running": False, "error": str(exc)}), 500


@app.route("/api/screener/refresh", methods=["POST"])
def api_screener_refresh():
    """Zorla yeni tarama baslatir (force=True)."""
    try:
        _, is_running = screener.get_or_trigger(force=True)
        return jsonify({"is_running": is_running, "error": None})
    except Exception as exc:
        return jsonify({"is_running": False, "error": str(exc)}), 500


@app.route("/api/pnl")
def api_pnl():
    """Son 30 gunun PnL gecmisini JSON olarak dondurur."""
    try:
        history = reporter.get_history(30)
        today   = reporter.get_today()
        return jsonify({"history": history, "today": today, "error": None})
    except Exception as exc:
        return jsonify({"history": [], "today": None, "error": str(exc)}), 500


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False)
