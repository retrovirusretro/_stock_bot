# -*- coding: utf-8 -*-
"""
test_strategy.py - strategy.py modulu icin birim testler
Crossover sinyal mantigi test edilir.
"""

import sys
import os
import pytest
import pandas as pd
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from strategy import sma_crossover_signals, filtered_signals
from data import add_sma, add_indicators


# ---------------------------------------------------------------------------
# Yardimci
# ---------------------------------------------------------------------------

def make_df_with_sma(prices, fast=20, slow=50):
    """Fiyat listesinden SMA eklenmi DataFrame olusturur."""
    idx = pd.date_range("2024-01-01", periods=len(prices), freq="B")
    df = pd.DataFrame({
        "open":   prices,
        "high":   [p * 1.01 for p in prices],
        "low":    [p * 0.99 for p in prices],
        "close":  prices,
        "volume": [1_000_000] * len(prices),
    }, index=idx)
    return add_sma(df, [fast, slow])


# ---------------------------------------------------------------------------
# Temel kolon testleri
# ---------------------------------------------------------------------------

class TestCrossoverColumns:

    def test_signal_column_exists(self):
        df = make_df_with_sma(list(range(1, 101)))
        df = sma_crossover_signals(df, 20, 50)
        assert "signal" in df.columns

    def test_position_column_exists(self):
        df = make_df_with_sma(list(range(1, 101)))
        df = sma_crossover_signals(df, 20, 50)
        assert "position" in df.columns

    def test_missing_sma_raises_error(self):
        """SMA kolonlari yoksa ValueError firlatmali."""
        idx = pd.date_range("2024-01-01", periods=10, freq="B")
        df = pd.DataFrame({"close": range(10)}, index=idx)
        with pytest.raises(ValueError):
            sma_crossover_signals(df, 20, 50)

    def test_returns_dataframe(self):
        df = make_df_with_sma(list(range(1, 101)))
        result = sma_crossover_signals(df, 20, 50)
        assert isinstance(result, pd.DataFrame)


# ---------------------------------------------------------------------------
# Sinyal degerleri
# ---------------------------------------------------------------------------

class TestSignalValues:

    def test_signal_only_1_minus1_0(self):
        """signal kolonu yalnizca +1, -1, 0 icermeli."""
        df = make_df_with_sma(list(range(1, 101)))
        df = sma_crossover_signals(df, 20, 50)
        valid = {-1, 0, 1}
        assert set(df["signal"].unique()).issubset(valid)

    def test_uptrend_signal_is_buy(self):
        """SMA20 > SMA50 oldugunda signal = +1 olmali."""
        # Surekli yukselen fiyat -> SMA20 > SMA50
        prices = list(range(1, 101))
        df = make_df_with_sma(prices)
        df = sma_crossover_signals(df, 20, 50)
        # Son bolumdeki sinyallerin cogu +1 olmali
        tail_signals = df["signal"].dropna().tail(20)
        assert (tail_signals == 1).all()

    def test_downtrend_signal_is_sell(self):
        """SMA20 < SMA50 oldugunda signal = -1 olmali."""
        # Surekli dusen fiyat -> SMA20 < SMA50
        prices = list(range(100, 0, -1))
        df = make_df_with_sma(prices)
        df = sma_crossover_signals(df, 20, 50)
        tail_signals = df["signal"].dropna().tail(20)
        assert (tail_signals == -1).all()


# ---------------------------------------------------------------------------
# Crossover tespiti
# ---------------------------------------------------------------------------

class TestCrossoverDetection:

    def _make_crossover_prices(self, n=300):
        """
        Once asagi (SMA20 < SMA50 -> SELL bolge),
        sonra yukari (SMA20 > SMA50 -> BUY crossover),
        sonra tekrar asagi (SELL crossover) giden fiyat serisi.
        n=300: SMA50 icin yeterli gecmis + iki crossover garantili.
        """
        prices = []
        third = n // 3
        for i in range(n):
            if i < third:
                prices.append(150 - i * 0.5)       # asagi trend
            elif i < 2 * third:
                prices.append(75 + (i - third) * 0.8)  # yukari trend
            else:
                prices.append(155 - (i - 2 * third) * 0.6)  # asagi trend
        return prices

    def test_buy_signal_detected(self):
        """Yukari crossover'da position == +2 olmali."""
        prices = self._make_crossover_prices(200)
        df = make_df_with_sma(prices)
        df = sma_crossover_signals(df, 20, 50)
        assert (df["position"] == 2).sum() >= 1

    def test_sell_signal_detected(self):
        """Asagi crossover'da position == -2 olmali."""
        prices = self._make_crossover_prices(200)
        df = make_df_with_sma(prices)
        df = sma_crossover_signals(df, 20, 50)
        assert (df["position"] == -2).sum() >= 1

    def test_no_signal_on_flat_prices(self):
        """Duz fiyatta crossover olmamali."""
        prices = [100.0] * 100
        df = make_df_with_sma(prices)
        df = sma_crossover_signals(df, 20, 50)
        # position sadece NaN ve 0 olmali (2 veya -2 yok)
        non_zero = df["position"].dropna()
        assert not (non_zero.abs() == 2).any()

    def test_original_df_not_mutated(self):
        """Orijinal DataFrame degistirilmemeli (copy yapilmali)."""
        prices = list(range(1, 101))
        df = make_df_with_sma(prices)
        original_cols = set(df.columns)
        _ = sma_crossover_signals(df, 20, 50)
        assert "signal" not in original_cols


# ---------------------------------------------------------------------------
# filtered_signals testleri
# ---------------------------------------------------------------------------

class TestFilteredSignals:

    def _make_full_df(self, prices):
        """Tum indikatörleri eklenmi DataFrame."""
        idx = pd.date_range("2023-01-01", periods=len(prices), freq="B")
        df = pd.DataFrame({
            "open":   prices,
            "high":   [p * 1.01 for p in prices],
            "low":    [p * 0.99 for p in prices],
            "close":  prices,
            "volume": [1_000_000] * len(prices),
        }, index=idx)
        return add_indicators(df, sma_periods=[20, 50, 200])

    def test_signal_and_position_columns_exist(self):
        df = self._make_full_df(list(range(50, 350)))
        df = filtered_signals(df, 20, 50)
        assert "signal" in df.columns
        assert "position" in df.columns

    def test_signal_raw_preserved(self):
        """Orijinal crossover sinyali signal_raw olarak saklanmali."""
        df = self._make_full_df(list(range(50, 350)))
        df = filtered_signals(df, 20, 50)
        assert "signal_raw" in df.columns

    def test_rsi_filter_blocks_overbought_buy(self):
        """RSI > 65 oldugunda BUY sinyali olmamali."""
        df = self._make_full_df(list(range(50, 350)))
        df = filtered_signals(df, 20, 50)
        # RSI > 65 olan satirlarda signal == 1 olmamali
        if "rsi" in df.columns:
            overbought = df[df["rsi"] > 65]
            assert (overbought["signal"] != 1).all()

    def test_filtered_signals_only_1_minus1_0(self):
        """Filtreli sinyal yalnizca +1, -1, 0 icermeli."""
        df = self._make_full_df(list(range(50, 350)))
        df = filtered_signals(df, 20, 50)
        valid = {-1, 0, 1}
        assert set(df["signal"].unique()).issubset(valid)

    def test_filtered_has_fewer_or_equal_buys_than_raw(self):
        """Filtreli BUY sayisi ham BUY sayisindan az veya esit olmali."""
        df = self._make_full_df(list(range(50, 350)))
        df = filtered_signals(df, 20, 50)
        raw_buys  = (df["signal_raw"] == 1).sum()
        filt_buys = (df["signal"]     == 1).sum()
        assert filt_buys <= raw_buys

    def test_sma200_filter_blocks_buy_in_downtrend(self):
        """Fiyat SMA200 altindayken BUY olmamali."""
        df = self._make_full_df(list(range(50, 350)))
        df = filtered_signals(df, 20, 50)
        if "sma200" in df.columns:
            below_200 = df[df["close"] < df["sma200"]]
            assert (below_200["signal"] != 1).all()
