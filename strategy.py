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


def filtered_signals(df, fast=20, slow=50, use_sma200=True):
    """
    Trend takip icin kanıtlanmıs minimal filtre seti.

    Iki mod:
        use_sma200=True  (varsayilan) — Hisse, ETF, genis piyasa icin
            BUY: SMA crossover VE fiyat > SMA200
            SELL: crossover asagi VEYA RSI>75 VEYA fiyat < SMA200

        use_sma200=False — Kriz varliklari icin (GLD, SLV, USO)
            En buyuk hareketleri SMA200 altından basladigi icin filtre uygulanmaz.
            BUY: sadece SMA crossover
            SELL: crossover asagi VEYA RSI>75

    Args:
        df:         OHLCV + indikatör DataFrame
        fast:       Hizli SMA periyodu (varsayilan: 20)
        slow:       Yavas SMA periyodu (varsayilan: 50)
        use_sma200: True = SMA200 filtresi uygula (hisse/ETF)
                    False = SMA200 filtresi atla (GLD/SLV/USO gibi kriz varliklari)

    Returns:
        DataFrame: signal_raw, signal, position kolonlari
    """
    df = sma_crossover_signals(df, fast=fast, slow=slow)
    df = df.rename(columns={"signal": "signal_raw", "position": "position_raw"})

    fast_col = f"sma{fast}"
    slow_col = f"sma{slow}"

    # 1. Kisa vade trend: SMA crossover
    cond_trend_up = df[fast_col] > df[slow_col]

    # 2. Uzun vade trend yonu: SMA200 filtresi
    # use_sma200=False ise kriz varliklari icin atlanir (GLD/SLV/USO)
    if use_sma200 and "sma200" in df.columns:
        cond_sma200_buy  = df["close"] > df["sma200"]
        cond_sma200_sell = df["close"] < df["sma200"]
    else:
        cond_sma200_buy  = pd.Series(True,  index=df.index)
        cond_sma200_sell = pd.Series(False, index=df.index)

    # Cikis: RSI > 75 (guclu asiri alim — GIRIS filtresi degil, CIKIS filtresi)
    if "rsi" in df.columns:
        cond_rsi_exit = df["rsi"] > 75
    else:
        cond_rsi_exit = pd.Series(False, index=df.index)

    # --- Sinyal uret ---
    buy_ok  = cond_trend_up & cond_sma200_buy
    sell_ok = (~cond_trend_up) | cond_rsi_exit | cond_sma200_sell

    df["signal"] = 0
    df.loc[buy_ok,  "signal"] =  1
    df.loc[sell_ok, "signal"] = -1

    df["position"] = df["signal"].diff()

    raw_buys  = (df["signal_raw"] ==  1).sum()
    raw_sells = (df["signal_raw"] == -1).sum()
    filt_buys = (df["signal"]     ==  1).sum()
    buy_cross = (df["position"]   ==  2).sum()
    sell_cross= (df["position"]   == -2).sum()
    filtered  = raw_buys - filt_buys

    mode = "SMA200+RSI" if use_sma200 else "Kriz(RSI-only)"
    print(
        f"[STRATEGY] {mode} SMA{fast}/{slow} | "
        f"Ham: {raw_buys}BUY -> Filtreli: {filt_buys}BUY ({filtered} engellendi) | "
        f"Crossover: {buy_cross}BUY {sell_cross}SELL"
    )
    return df


def supertrend_signals(df):
    """
    Supertrend tabanlı sinyal üretir.

    Kural:
        supertrend_dir +1'e döndüğünde -> BUY crossover  (position = +2)
        supertrend_dir -1'e döndüğünde -> SELL crossover (position = -2)

    Args:
        df: 'supertrend_dir' kolonu olan DataFrame
            (add_supertrend() ile hazırlanmış olmalı)

    Returns:
        DataFrame: 'signal' (+1/-1) ve 'position' (+2/-2) kolonları eklenmiş
    """
    if "supertrend_dir" not in df.columns:
        raise ValueError(
            "DataFrame'de supertrend_dir kolonu yok. "
            "Once add_supertrend() calistir."
        )

    df = df.copy()
    df["signal"] = df["supertrend_dir"].apply(
        lambda x: 1 if x == 1 else (-1 if x == -1 else 0)
    )
    df["position"] = df["signal"].diff()

    buy_cross  = (df["position"] ==  2).sum()
    sell_cross = (df["position"] == -2).sum()
    print(
        f"[STRATEGY] Supertrend -> "
        f"{buy_cross} BUY crossover, {sell_cross} SELL crossover"
    )
    return df


def rsi_bounce_signals(df, rsi_low=35, rsi_high=50):
    """
    RSI asiri satim bolgesinden cikis sinyali (SMA grubu icin ek katman).

    Kural:
        RSI once rsi_low altina dusmus, sonra rsi_high ustune cikinca -> BUY (+2)
        BUY sonrasinda RSI tekrar rsi_low altina dusunce            -> SELL (-2)

    SMA crossover ile kombine kullanilir: hangi BUY daha yeniyse
    o aksiyon alinir (paper_trader.py karsilastirir).

    Args:
        df      : 'rsi' kolonu olan OHLCV DataFrame
        rsi_low : Asiri satim esigi (varsayilan 35)
        rsi_high: Yukselis onay esigi (varsayilan 50)

    Returns:
        DataFrame: 'rsi_signal' (+1/-1) ve 'rsi_position' (+2/-2) kolonlari eklenmis
    """
    if "rsi" not in df.columns:
        df["rsi_signal"]   = 0
        df["rsi_position"] = 0
        return df

    df = df.copy()
    rsi = df["rsi"].values
    n   = len(df)

    signal = [0] * n
    in_oversold = False   # RSI < rsi_low esigini gercekten gormustuk mu?
    in_buy      = False   # Aktif BUY pozisyonunda miyiz?

    for i in range(1, n):
        if rsi[i] < rsi_low:
            in_oversold = True

        if in_oversold and not in_buy and rsi[i] > rsi_high:
            signal[i]   = 2     # BUY crossover
            in_buy      = True
            in_oversold = False

        elif in_buy and rsi[i] < rsi_low:
            signal[i] = -2      # SELL crossover
            in_buy    = False
            in_oversold = True  # hemen tekrar oversold sayiyor

    df["rsi_signal"]   = [1 if s == 2 else (-1 if s == -2 else 0) for s in signal]
    df["rsi_position"] = signal

    buy_count  = sum(1 for s in signal if s ==  2)
    sell_count = sum(1 for s in signal if s == -2)
    print(
        f"[STRATEGY] RSI Bounce (low={rsi_low}, high={rsi_high}) -> "
        f"{buy_count} BUY, {sell_count} SELL"
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
