# -*- coding: utf-8 -*-
"""
test_data.py - data.py modulu icin birim testler
SMA ve RSI hesaplama dogrulugu test edilir.
Gercek API cagrisi yapilmaz; sentetik DataFrame kullanilir.
"""

import sys
import os
import pytest
import pandas as pd
import numpy as np

# Proje kokunu path'e ekle
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from data import add_sma, add_rsi, add_indicators


# ---------------------------------------------------------------------------
# Yardimci: test DataFrame uret
# ---------------------------------------------------------------------------

def make_df(prices, start="2024-01-01"):
    """Verilen fiyat listesinden minimal OHLCV DataFrame olusturur."""
    idx = pd.date_range(start, periods=len(prices), freq="B")
    return pd.DataFrame({
        "open":   prices,
        "high":   [p * 1.01 for p in prices],
        "low":    [p * 0.99 for p in prices],
        "close":  prices,
        "volume": [1_000_000] * len(prices),
    }, index=idx)


# ---------------------------------------------------------------------------
# SMA testleri
# ---------------------------------------------------------------------------

class TestAddSma:

    def test_sma20_column_exists(self):
        df = make_df(list(range(1, 101)))  # 100 gun
        df = add_sma(df, [20])
        assert "sma20" in df.columns

    def test_sma50_column_exists(self):
        df = make_df(list(range(1, 101)))
        df = add_sma(df, [50])
        assert "sma50" in df.columns

    def test_sma_value_accuracy(self):
        """SMA20 son degeri: son 20 gun ortalamasi olmali."""
        prices = list(range(1, 101))  # 1..100
        df = make_df(prices)
        df = add_sma(df, [20])
        expected = np.mean(prices[-20:])  # 81..100 -> 90.5
        assert abs(df["sma20"].iloc[-1] - expected) < 0.01

    def test_sma_nan_at_start(self):
        """SMA20 icin ilk 19 deger NaN olmali."""
        df = make_df(list(range(1, 101)))
        df = add_sma(df, [20])
        assert df["sma20"].iloc[:19].isna().all()

    def test_sma_not_nan_after_period(self):
        """SMA20 icin 20. gun NaN olmamali."""
        df = make_df(list(range(1, 101)))
        df = add_sma(df, [20])
        assert not pd.isna(df["sma20"].iloc[19])

    def test_multiple_sma_periods(self):
        """Birden fazla periyot ayni anda hesaplanabilmeli."""
        df = make_df(list(range(1, 201)))
        df = add_sma(df, [20, 50, 200])
        for col in ["sma20", "sma50", "sma200"]:
            assert col in df.columns

    def test_sma_returns_dataframe(self):
        df = make_df(list(range(1, 101)))
        result = add_sma(df, [20])
        assert isinstance(result, pd.DataFrame)


# ---------------------------------------------------------------------------
# RSI testleri
# ---------------------------------------------------------------------------

class TestAddRsi:

    def test_rsi_column_exists(self):
        df = make_df(list(range(1, 101)))
        df = add_rsi(df, 14)
        assert "rsi" in df.columns

    def test_rsi_range(self):
        """RSI 0-100 araliginda olmali."""
        prices = [100 + 5 * np.sin(i * 0.3) for i in range(200)]
        df = make_df(prices)
        df = add_rsi(df, 14)
        valid = df["rsi"].dropna()
        assert (valid >= 0).all() and (valid <= 100).all()

    def test_rsi_uptrend_high(self):
        """Surekli yukselen fiyatta RSI yuksek olmali (>50)."""
        prices = list(range(50, 150))  # 100 gun surekli artis
        df = make_df(prices)
        df = add_rsi(df, 14)
        # Son deger yuksek olmali
        assert df["rsi"].iloc[-1] > 50

    def test_rsi_downtrend_low(self):
        """Surekli dusen fiyatta RSI dusuk olmali (<50)."""
        prices = list(range(150, 50, -1))  # 100 gun surekli dusus
        df = make_df(prices)
        df = add_rsi(df, 14)
        assert df["rsi"].iloc[-1] < 50

    def test_rsi_returns_dataframe(self):
        df = make_df(list(range(1, 101)))
        result = add_rsi(df, 14)
        assert isinstance(result, pd.DataFrame)


# ---------------------------------------------------------------------------
# add_indicators testleri
# ---------------------------------------------------------------------------

class TestAddIndicators:

    def test_all_columns_present(self):
        """add_indicators SMA, RSI, ATR, MACD kolonlarini eklemeli."""
        df = make_df(list(range(1, 301)))
        df = add_indicators(df, sma_periods=[20, 50], rsi_period=14)
        for col in ["sma20", "sma50", "rsi", "atr", "macd", "macd_signal"]:
            assert col in df.columns, f"{col} kolonu eksik"

    def test_default_sma_periods(self):
        """Varsayilan periyotlar: 20, 50, 200."""
        df = make_df(list(range(1, 301)))
        df = add_indicators(df)
        assert "sma200" in df.columns

    def test_bollinger_bands_columns(self):
        """add_indicators BB kolonlarini eklemeli."""
        df = make_df(list(range(1, 301)))
        df = add_indicators(df)
        for col in ["bb_upper", "bb_mid", "bb_lower", "bb_pct"]:
            assert col in df.columns, f"{col} kolonu eksik"

    def test_bollinger_bands_order(self):
        """Ust bant >= Orta bant >= Alt bant olmali."""
        df = make_df(list(range(1, 301)))
        df = add_indicators(df)
        valid = df.dropna(subset=["bb_upper", "bb_mid", "bb_lower"])
        assert (valid["bb_upper"] >= valid["bb_mid"]).all()
        assert (valid["bb_mid"]   >= valid["bb_lower"]).all()

    def test_bb_pct_range(self):
        """bb_pct genel olarak 0-1 araliginda olmali (spike'lar disinda)."""
        prices = [100 + 5 * __import__("numpy").sin(i * 0.3) for i in range(200)]
        df = make_df(prices)
        df = add_indicators(df, sma_periods=[20, 50])
        valid = df["bb_pct"].dropna()
        # Cogu deger 0-1 araliginda olmali
        in_range = ((valid >= 0) & (valid <= 1)).mean()
        assert in_range > 0.80
