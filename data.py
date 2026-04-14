# -*- coding: utf-8 -*-
"""
data.py - Fiyat verisi cekme modulu
Hafta 1: yfinance ile OHLCV verisi, SMA, RSI hesaplama
"""

import yfinance as yf
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.dates as mdates


def get_price_data(symbol, start, end):
    """
    yfinance ile OHLCV verisi ceker.

    Args:
        symbol: Hisse sembolü (orn: "AAPL")
        start:  Baslangic tarihi "YYYY-MM-DD"
        end:    Bitis tarihi    "YYYY-MM-DD"

    Returns:
        DataFrame: open, high, low, close, volume kolonlari
    """
    print(f"[DATA] {symbol} verisi cekiliyor: {start} -> {end}")
    df = yf.download(symbol, start=start, end=end, auto_adjust=True, progress=False)

    if df.empty:
        raise ValueError(f"{symbol} icin veri bulunamadi.")

    # yfinance 1.x MultiIndex kolonlarini duzlestir
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = [c[0].lower() for c in df.columns]
    else:
        df.columns = [c.lower() for c in df.columns]

    # Adj Close varsa kaldır, close yeterli (auto_adjust=True ile zaten düzeltilmis)
    df = df.drop(columns=["adj close"], errors="ignore")

    print(f"[DATA] {len(df)} gunluk veri alindi. Kolonlar: {list(df.columns)}")
    return df


def add_sma(df, periods):
    """
    DataFrame'e SMA (Simple Moving Average) kolonlari ekler.

    Args:
        df:      OHLCV DataFrame
        periods: SMA periyotlari listesi (orn: [20, 50])
    """
    for p in periods:
        df[f"sma{p}"] = df["close"].rolling(window=p).mean()
        print(f"[DATA] SMA{p} hesaplandi.")
    return df


def add_rsi(df, period=14):
    """
    DataFrame'e RSI (Relative Strength Index) kolonu ekler.

    Args:
        df:     OHLCV DataFrame
        period: RSI periyodu (varsayilan: 14)
    """
    delta    = df["close"].diff()
    gain     = delta.clip(lower=0)
    loss     = -delta.clip(upper=0)
    avg_gain = gain.rolling(window=period).mean()
    avg_loss = loss.rolling(window=period).mean()
    rs       = avg_gain / avg_loss
    df["rsi"] = 100 - (100 / (1 + rs))
    print(f"[DATA] RSI{period} hesaplandi.")
    return df


def plot_chart(df, symbol):
    """
    Kapanis fiyati + SMA'lar + RSI grafigi cizer.
    """
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(14, 8), sharex=True,
                                    gridspec_kw={"height_ratios": [3, 1]})
    fig.suptitle(f"{symbol} - Fiyat, SMA ve RSI", fontsize=14, fontweight="bold")

    # Ust grafik: Fiyat + SMA
    ax1.plot(df.index, df["close"], label="Close", linewidth=1.5, color="#2196F3")

    sma_colors = {"sma20": "#FF9800", "sma50": "#E91E63", "sma200": "#9C27B0"}
    for col, color in sma_colors.items():
        if col in df.columns:
            ax1.plot(df.index, df[col], label=col.upper(),
                     linewidth=1.2, linestyle="--", color=color)

    ax1.set_ylabel("Price (USD)")
    ax1.legend(loc="upper left")
    ax1.grid(True, alpha=0.3)

    # Alt grafik: RSI
    if "rsi" in df.columns:
        ax2.plot(df.index, df["rsi"], label="RSI(14)", color="#607D8B", linewidth=1.2)
        ax2.axhline(70, color="red",   linestyle="--", linewidth=0.8, alpha=0.7)
        ax2.axhline(30, color="green", linestyle="--", linewidth=0.8, alpha=0.7)
        ax2.fill_between(df.index, df["rsi"], 70,
                         where=(df["rsi"] >= 70), alpha=0.2, color="red",   label="Overbought")
        ax2.fill_between(df.index, df["rsi"], 30,
                         where=(df["rsi"] <= 30), alpha=0.2, color="green", label="Oversold")
        ax2.set_ylabel("RSI")
        ax2.set_ylim(0, 100)
        ax2.legend(loc="upper left")
        ax2.grid(True, alpha=0.3)

    ax2.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m"))
    plt.xticks(rotation=45)
    plt.tight_layout()
    plt.show()


# ---------------------------------------------------------------------------
# Dogrudan calistirilirsa test et
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    SYMBOLS = ["AAPL", "MSFT", "SPY"]
    START   = "2020-01-01"
    END     = "2024-12-31"

    for sym in SYMBOLS:
        print(f"\n{'='*50}")
        print(f"  {sym}")
        print(f"{'='*50}")

        df = get_price_data(sym, START, END)
        df = add_sma(df, [20, 50, 200])
        df = add_rsi(df, 14)

        print(f"\nSon 5 gun:")
        print(df[["close", "sma20", "sma50", "rsi"]].tail())

        plot_chart(df, sym)
