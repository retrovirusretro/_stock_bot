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
