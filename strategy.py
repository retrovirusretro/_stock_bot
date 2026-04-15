# -*- coding: utf-8 -*-
"""
strategy.py - Sinyal uretme modulu
Hafta 1: SMA Crossover sinyali
Hafta 2: Backtrader entegrasyonu gelecek
"""

import pandas as pd


def sma_crossover_signals(df, fast=20, slow=50):
    """
    SMA Crossover sinyali uretir.

    Kural:
        fast SMA, slow SMA'nin USTUNE cikarsa -> BUY  (+1)
        fast SMA, slow SMA'nin ALTINA inerse  -> SELL (-1)
        Diger                                 -> HOLD  (0)

    Args:
        df:   SMA kolonlari eklenmi OHLCV DataFrame
        fast: Hizli SMA periyodu (varsayilan: 20)
        slow: Yavas SMA periyodu (varsayilan: 50)

    Returns:
        DataFrame: 'signal' ve 'position' kolonlari eklenmi
    """
    fast_col = f"sma{fast}"
    slow_col = f"sma{slow}"

    if fast_col not in df.columns or slow_col not in df.columns:
        raise ValueError(
            f"DataFrame'de {fast_col} veya {slow_col} kolonu yok. "
            f"Once add_sma() calistir."
        )

    df = df.copy()
    df["signal"] = 0
    df.loc[df[fast_col] > df[slow_col], "signal"] = 1
    df.loc[df[fast_col] < df[slow_col], "signal"] = -1

    # Sadece gecis anlari (crossover)
    # position = +2 -> BUY,  position = -2 -> SELL
    df["position"] = df["signal"].diff()

    buy_count  = (df["position"] == 2).sum()
    sell_count = (df["position"] == -2).sum()
    print(f"[STRATEGY] SMA{fast}/SMA{slow} Crossover -> {buy_count} BUY, {sell_count} SELL")

    return df


def filtered_signals(df, fast=20, slow=50):
    """
    Gelismis sinyal uretici — coklu filtre katmanlariyla yanlis sinyalleri eler.

    Filtreler:
        BUY icin (HEPSI saglanmali):
            1. SMA{fast} > SMA{slow}           — trend yukari
            2. Fiyat > SMA200                  — uzun vadeli trend yukari
            3. RSI < 65                        — asiri alimda degil
            4. MACD > MACD Signal              — momentum yukari
            5. bb_pct < 0.8                    — Bollinger ust bantta degil

        SELL icin (HERHANGI BIRI yeterli):
            1. SMA{fast} < SMA{slow}           — trend asagi
            2. RSI > 70                        — asiri alim cikisi
            3. Fiyat < SMA200                  — uzun vadeli trend kirildı

    Returns:
        DataFrame: 'signal_raw' (orijinal crossover), 'signal' (filtreli) kolonlari
    """
    df = sma_crossover_signals(df, fast=fast, slow=slow)
    df = df.rename(columns={"signal": "signal_raw", "position": "position_raw"})

    fast_col = f"sma{fast}"
    slow_col = f"sma{slow}"

    # --- BUY kosullari ---
    cond_trend_up   = df[fast_col] > df[slow_col]

    # SMA200 varsa kullan
    if "sma200" in df.columns:
        cond_sma200 = df["close"] > df["sma200"]
    else:
        cond_sma200 = pd.Series(True, index=df.index)

    # RSI varsa kullan
    if "rsi" in df.columns:
        cond_rsi_buy  = df["rsi"] < 65
        cond_rsi_sell = df["rsi"] > 70
    else:
        cond_rsi_buy  = pd.Series(True, index=df.index)
        cond_rsi_sell = pd.Series(False, index=df.index)

    # MACD varsa kullan
    if "macd" in df.columns and "macd_signal" in df.columns:
        cond_macd = df["macd"] > df["macd_signal"]
    else:
        cond_macd = pd.Series(True, index=df.index)

    # Bollinger Bands varsa kullan
    if "bb_pct" in df.columns:
        cond_bb_buy = df["bb_pct"] < 0.8   # ust banda cok yakin degil
    else:
        cond_bb_buy = pd.Series(True, index=df.index)

    # --- Sinyal uret ---
    buy_qualified  = cond_trend_up & cond_sma200 & cond_rsi_buy & cond_macd & cond_bb_buy
    sell_qualified = (~cond_trend_up) | cond_rsi_sell | (~cond_sma200)

    df["signal"] = 0
    df.loc[buy_qualified,  "signal"] =  1
    df.loc[sell_qualified, "signal"] = -1

    df["position"] = df["signal"].diff()

    # Kac sinyal filtrelendi?
    raw_buys      = (df["signal_raw"] ==  1).sum()
    raw_sells     = (df["signal_raw"] == -1).sum()
    filt_buys     = (df["signal"]     ==  1).sum()
    filt_sells    = (df["signal"]     == -1).sum()
    buy_cross     = (df["position"]   ==  2).sum()
    sell_cross    = (df["position"]   == -2).sum()

    print(
        f"[STRATEGY] Filtreli SMA{fast}/SMA{slow} | "
        f"Ham: {raw_buys}BUY/{raw_sells}SELL -> "
        f"Filtreli: {filt_buys}BUY/{filt_sells}SELL | "
        f"Crossover: {buy_cross}BUY, {sell_cross}SELL"
    )
    return df


def print_signals(df, last_n=10):
    """Son N sinyali ekrana yazdirir."""
    signals = df[df["position"].abs() == 2].copy()
    signals["type"] = signals["position"].map({2: "BUY", -2: "SELL"})

    print(f"\nSon {last_n} sinyal:")
    print(signals[["close", "sma20", "sma50", "type"]].tail(last_n).to_string())


# ---------------------------------------------------------------------------
# Dogrudan calistirilirsa test et
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    from data import get_price_data, add_sma, add_rsi

    sym = "AAPL"
    df = get_price_data(sym, "2020-01-01", "2024-12-31")
    df = add_sma(df, [20, 50])
    df = add_rsi(df, 14)
    df = sma_crossover_signals(df, fast=20, slow=50)
    print_signals(df, last_n=10)
