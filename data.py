# -*- coding: utf-8 -*-
"""
data.py - Fiyat verisi cekme modulu
Hafta 1: yfinance ile OHLCV verisi, SMA, RSI hesaplama
Refactor: pandas-ta -> ta (Python 3.11 uyumlu)
"""

import yfinance as yf
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import ta


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
        df[f"sma{p}"] = ta.trend.sma_indicator(df["close"], window=p)
        print(f"[DATA] SMA{p} hesaplandi.")
    return df


def add_rsi(df, period=14):
    """
    DataFrame'e RSI (Relative Strength Index) kolonu ekler.

    Args:
        df:     OHLCV DataFrame
        period: RSI periyodu (varsayilan: 14)
    """
    df["rsi"] = ta.momentum.rsi(df["close"], window=period)
    print(f"[DATA] RSI{period} hesaplandi.")
    return df


def add_bollinger_bands(df, window=20, window_dev=2):
    """
    Bollinger Bands ekler: ust bant, orta (SMA20), alt bant, yuzde konum.

    Args:
        df:         OHLCV DataFrame
        window:     Periyot (varsayilan: 20)
        window_dev: Standart sapma carpani (varsayilan: 2)
    """
    bb = ta.volatility.BollingerBands(df["close"], window=window, window_dev=window_dev)
    df["bb_upper"] = bb.bollinger_hband()
    df["bb_mid"]   = bb.bollinger_mavg()
    df["bb_lower"] = bb.bollinger_lband()
    # 0 = alt bantta, 1 = ust bantta, 0.5 = ortada
    df["bb_pct"]   = bb.bollinger_pband()
    print(f"[DATA] Bollinger Bands({window},{window_dev}) hesaplandi.")
    return df


def add_indicators(df, sma_periods=None, rsi_period=14):
    """
    Tum indiktorleri tek seferde hesaplar.
    SMA, RSI, ATR, ADX, MACD, Bollinger Bands.

    Filtre hiyerarsisi (genel kabul gormüs):
        1. SMA200  — uzun vadeli trend yonu (Stan Weinstein)
        2. ADX>20  — trend gucu, ranging piyasayi eler (Wilder / Van Tharp)
        3. RSI 40-68 — saglikli momentum zonu
        ATR        — dinamik stop/TP icin volatilite olcumu

    MACD ve BB dashboard/grafik icin hesaplanir ama
    filtre olarak kullanilmaz (cift gecikme sorununu onler).

    Args:
        df:          OHLCV DataFrame
        sma_periods: SMA periyotlari listesi (varsayilan: [20, 50, 200])
        rsi_period:  RSI periyodu (varsayilan: 14)
    """
    if sma_periods is None:
        sma_periods = [20, 50, 200]
    df = add_sma(df, sma_periods)
    df = add_rsi(df, rsi_period)

    # ATR - dinamik stop-loss icin
    df["atr"] = ta.volatility.average_true_range(
        df["high"], df["low"], df["close"], window=14
    )
    print("[DATA] ATR14 hesaplandi.")

    # ADX - trend gucu olcumu (en onemli filtre)
    # ADX > 20: trend var, sinyal al | ADX < 20: ranging piyasa, sinyal atlat
    df["adx"] = ta.trend.adx(df["high"], df["low"], df["close"], window=14)
    print("[DATA] ADX14 hesaplandi.")

    # MACD - dashboard/grafik icin (filtre degil)
    df["macd"]        = ta.trend.macd(df["close"])
    df["macd_signal"] = ta.trend.macd_signal(df["close"])
    print("[DATA] MACD hesaplandi.")

    # Bollinger Bands - dashboard/grafik icin (filtre degil)
    df = add_bollinger_bands(df)
    return df


def add_supertrend(df, period=10, multiplier=3.0):
    """
    Supertrend indikatörü hesaplar (ATR tabanlı trend takip).

    Kural:
        Fiyat lower band'in üstünde kalırsa -> yükseliş trendi (+1)
        Fiyat upper band'in altına düşerse  -> düşüş trendi    (-1)

    Args:
        df:         OHLCV DataFrame (high, low, close gerekli)
        period:     ATR periyodu (varsayılan: 10)
        multiplier: ATR çarpanı  (varsayılan: 3.0)

    Returns:
        DataFrame: 'supertrend' (destek/direnç çizgisi) ve
                   'supertrend_dir' (+1 / -1) kolonları eklenmiş
    """
    atr_series = ta.volatility.average_true_range(
        df["high"], df["low"], df["close"], window=period
    )

    hl2         = (df["high"].values + df["low"].values) / 2.0
    atr         = atr_series.values
    close       = df["close"].values
    n           = len(df)

    basic_upper = hl2 + multiplier * atr
    basic_lower = hl2 - multiplier * atr

    final_upper = basic_upper.copy()
    final_lower = basic_lower.copy()
    supertrend  = np.zeros(n)
    direction   = np.zeros(n, dtype=int)

    direction[0]  = 1
    supertrend[0] = final_lower[0]

    for i in range(1, n):
        # Final upper band: yalnızca aşağı kayar; fiyat üstüne çıkarsa sıfırla
        if basic_upper[i] < final_upper[i - 1] or close[i - 1] > final_upper[i - 1]:
            final_upper[i] = basic_upper[i]
        else:
            final_upper[i] = final_upper[i - 1]

        # Final lower band: yalnızca yukarı kayar; fiyat altına inerse sıfırla
        if basic_lower[i] > final_lower[i - 1] or close[i - 1] < final_lower[i - 1]:
            final_lower[i] = basic_lower[i]
        else:
            final_lower[i] = final_lower[i - 1]

        # Yön ve çizgi
        if supertrend[i - 1] == final_upper[i - 1]:
            # Önceki: düşüş (upper band takip)
            if close[i] <= final_upper[i]:
                direction[i] = -1
                supertrend[i] = final_upper[i]
            else:
                direction[i] = 1
                supertrend[i] = final_lower[i]
        else:
            # Önceki: yükseliş (lower band takip)
            if close[i] >= final_lower[i]:
                direction[i] = 1
                supertrend[i] = final_lower[i]
            else:
                direction[i] = -1
                supertrend[i] = final_upper[i]

    df = df.copy()
    df["supertrend"]     = supertrend
    df["supertrend_dir"] = direction

    # ATR henüz hesaplanamayan ilk satırları NaN yap
    df.loc[atr_series.isna(), "supertrend"]     = float("nan")
    df.loc[atr_series.isna(), "supertrend_dir"] = 0

    print(f"[DATA] Supertrend({period},{multiplier}) hesaplandi.")
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
