# -*- coding: utf-8 -*-
"""
backtest.py - Backtrader ile SMA Crossover Backtest
Strateji 1: Sade SMA Crossover (eski)
Strateji 2: Filtreli SMA Crossover — RSI + SMA200 + MACD + BB (yeni)
Komisyon: %0.1 | Sermaye: $10,000
"""

import sys
import math
import datetime

import yfinance as yf
import pandas as pd
import backtrader as bt


# ---------------------------------------------------------------------------
# Yardimci: yfinance'dan temiz DataFrame al
# ---------------------------------------------------------------------------

def fetch_data(symbol, start, end):
    df = yf.download(symbol, start=start, end=end, auto_adjust=True, progress=False)
    if df.empty:
        raise ValueError(f"{symbol} icin veri bulunamadi.")

    if isinstance(df.columns, pd.MultiIndex):
        df = df.xs(symbol, axis=1, level=1) if symbol in df.columns.get_level_values(1) else df
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.droplevel(1)

    df.columns = [c.lower() for c in df.columns]
    df = df.drop(columns=["adj close"], errors="ignore")
    needed = ["open", "high", "low", "close", "volume"]
    df = df[[c for c in needed if c in df.columns]]
    df = df.dropna()
    return df


def make_feed(df):
    return bt.feeds.PandasData(
        dataname=df,
        datetime=None,
        open="open", high="high", low="low", close="close", volume="volume",
        openinterest=-1,
    )


# ---------------------------------------------------------------------------
# Strateji 1: Sade SMA Crossover (eski)
# ---------------------------------------------------------------------------

class SmaCrossoverStrategy(bt.Strategy):
    params = dict(
        fast=20, slow=50,
        stop_pct=0.03, tp_pct=0.06,
        stake_pct=0.95,
    )

    def __init__(self):
        self.sma_fast  = bt.indicators.SMA(self.data.close, period=self.p.fast)
        self.sma_slow  = bt.indicators.SMA(self.data.close, period=self.p.slow)
        self.crossover = bt.indicators.CrossOver(self.sma_fast, self.sma_slow)
        self.order     = None
        self.buy_price = None

    def notify_order(self, order):
        if order.status == order.Completed and order.isbuy():
            self.buy_price = order.executed.price
        if order.status not in [order.Submitted, order.Accepted]:
            self.order = None

    def next(self):
        if self.order:
            return
        if not self.position:
            if self.crossover > 0:
                size = math.floor((self.broker.getcash() * self.p.stake_pct) / self.data.close[0])
                if size > 0:
                    self.order = self.buy(size=size)
        else:
            price = self.data.close[0]
            if price <= self.buy_price * (1 - self.p.stop_pct):
                self.order = self.sell(size=self.position.size)
            elif price >= self.buy_price * (1 + self.p.tp_pct):
                self.order = self.sell(size=self.position.size)
            elif self.crossover < 0:
                self.order = self.sell(size=self.position.size)


# ---------------------------------------------------------------------------
# Strateji 2: Filtreli SMA Crossover (yeni)
# Genel kabul gormüs filtreler: SMA200 + ADX + RSI momentum zonu
# ---------------------------------------------------------------------------

class FilteredSmaCrossoverStrategy(bt.Strategy):
    """
    Minimal filtre seti — AQR/Turtle Traders konsensüsü:
    Giriş: SMA crossover + SMA200 (tek filtre)
    Çıkış: crossover asagi VEYA RSI>75 VEYA fiyat < SMA200
    Stop: ATR tabanli dinamik (sabit %3 yerine)
    """
    params = dict(
        fast=20, slow=50,
        stop_atr_mult=2.0,
        tp_atr_mult=4.0,
        stake_pct=0.95,
        rsi_exit=75,
    )

    def __init__(self):
        self.sma_fast  = bt.indicators.SMA(self.data.close, period=self.p.fast)
        self.sma_slow  = bt.indicators.SMA(self.data.close, period=self.p.slow)
        self.sma200    = bt.indicators.SMA(self.data.close, period=200)
        self.crossover = bt.indicators.CrossOver(self.sma_fast, self.sma_slow)
        self.rsi       = bt.indicators.RSI(self.data.close, period=14)
        self.atr       = bt.indicators.ATR(self.data, period=14)
        self.order      = None
        self.buy_price  = None
        self.stop_price = None
        self.tp_price   = None

    def notify_order(self, order):
        if order.status == order.Completed and order.isbuy():
            self.buy_price  = order.executed.price
            self.stop_price = self.buy_price - (self.atr[0] * self.p.stop_atr_mult)
            self.tp_price   = self.buy_price + (self.atr[0] * self.p.tp_atr_mult)
        if order.status not in [order.Submitted, order.Accepted]:
            self.order = None

    def next(self):
        if self.order:
            return

        price = self.data.close[0]

        if not self.position:
            # BUY: SMA crossover + fiyat SMA200 üstünde
            trend_up  = self.crossover > 0
            above_200 = price > self.sma200[0]
            if trend_up and above_200:
                size = math.floor((self.broker.getcash() * self.p.stake_pct) / price)
                if size > 0:
                    self.order = self.buy(size=size)
        else:
            # CIKIS: crossover asagi VEYA RSI asiri alim VEYA SMA200 kirildı VEYA stop/TP
            exit_cross  = self.crossover < 0
            exit_rsi    = self.rsi[0] > self.p.rsi_exit
            exit_sma200 = price < self.sma200[0]
            exit_stop   = self.stop_price is not None and price <= self.stop_price
            exit_tp     = self.tp_price   is not None and price >= self.tp_price

            if exit_cross or exit_rsi or exit_sma200 or exit_stop or exit_tp:
                self.order = self.sell(size=self.position.size)


# ---------------------------------------------------------------------------
# Backtest Calistirici
# ---------------------------------------------------------------------------

def run_backtest(symbol, start, end, strategy_class, initial_cash=10000.0):
    df = fetch_data(symbol, start, end)

    cerebro = bt.Cerebro()
    cerebro.addstrategy(strategy_class)
    cerebro.adddata(make_feed(df))
    cerebro.broker.setcash(initial_cash)
    cerebro.broker.setcommission(commission=0.001)
    cerebro.addanalyzer(bt.analyzers.DrawDown,   _name="drawdown")
    cerebro.addanalyzer(bt.analyzers.SharpeRatio, _name="sharpe",
                        riskfreerate=0.02, annualize=True,
                        timeframe=bt.TimeFrame.Days)
    cerebro.addanalyzer(bt.analyzers.TradeAnalyzer, _name="trades")

    results   = cerebro.run()
    strat     = results[0]
    final     = cerebro.broker.getvalue()
    ret       = (final - initial_cash) / initial_cash * 100

    dd        = strat.analyzers.drawdown.get_analysis()
    max_dd    = dd.get("max", {}).get("drawdown", 0.0)

    sharpe_d  = strat.analyzers.sharpe.get_analysis()
    sharpe    = sharpe_d.get("sharperatio") or 0.0

    ta        = strat.analyzers.trades.get_analysis()
    total_t   = ta.get("total", {}).get("closed", 0)
    won       = ta.get("won", {})
    lost      = ta.get("lost", {})
    won_n     = won.get("total", 0)
    win_rate  = (won_n / total_t * 100) if total_t > 0 else 0.0
    avg_win   = won.get("pnl",  {}).get("average", 0.0) or 0.0
    avg_loss  = lost.get("pnl", {}).get("average", 0.0) or 0.0

    return {
        "symbol": symbol, "start": start, "end": end,
        "initial_cash": initial_cash, "final_cash": final,
        "total_return": ret, "max_drawdown": max_dd,
        "total_trades": total_t, "win_rate": win_rate,
        "avg_win": avg_win, "avg_loss": avg_loss, "sharpe": sharpe,
    }


# ---------------------------------------------------------------------------
# Karsilastirma tablosu yazici
# ---------------------------------------------------------------------------

def print_comparison_table(results_old, results_new, period_label):
    """Eski vs Yeni strateji karsilastirma tablosu."""
    print(f"\n{'='*90}")
    print(f"  {period_label} — ESKI vs YENi STRATEJI KARSILASTIRMASI")
    print(f"{'='*90}")
    header = f"  {'Sembol':<6} | {'Getiri(Eski)':>12} {'Getiri(Yeni)':>12} | {'Sharpe(Eski)':>12} {'Sharpe(Yeni)':>12} | {'MaxDD(Eski)':>11} {'MaxDD(Yeni)':>11} | {'Islem(E)':>8} {'Islem(Y)':>8}"
    print(header)
    print(f"  {'-'*84}")

    for sym in results_old:
        if sym not in results_new:
            continue
        o = results_old[sym]
        n = results_new[sym]
        ret_diff  = n["total_return"] - o["total_return"]
        sign      = "+" if ret_diff >= 0 else ""
        diff_str  = f"({sign}{ret_diff:.1f}%)"
        o_ret     = f"%{o['total_return']:+.1f}"
        n_ret     = f"%{n['total_return']:+.1f}"
        o_dd      = f"%{o['max_drawdown']:.1f}"
        n_dd      = f"%{n['max_drawdown']:.1f}"
        print(
            f"  {sym:<6} | "
            f"{o_ret:>12} {n_ret:>12} {diff_str:>8} | "
            f"{o['sharpe']:>12.2f} {n['sharpe']:>12.2f} | "
            f"{o_dd:>11} {n_dd:>11} | "
            f"{o['total_trades']:>8} {n['total_trades']:>8}"
        )
    print(f"{'='*90}")


# ---------------------------------------------------------------------------
# Ana Giris
# ---------------------------------------------------------------------------

if __name__ == "__main__":

    # Genisletilmis sembol evreni
    SYMBOLS = [
        # Emtia ETF (trend takipte iyi)
        "GLD", "SLV", "USO", "GDX", "GDXJ", "XME", "COPX",
        # Sektor ETF
        "XLE", "XLB", "XLI",
        # Genis piyasa
        "QQQ", "DIA", "IWM", "SPY",
        # Mevcut hisseler
        "AAPL", "MSFT",
    ]

    INITIAL_CASH = 10_000.0
    FULL_START   = "2019-01-01"
    FULL_END     = "2024-12-31"
    TRAIN_START  = "2019-01-01"
    TRAIN_END    = "2022-12-31"
    TEST_START   = "2023-01-01"
    TEST_END     = "2024-12-31"

    periods = [
        ("TAM DONEM  (2019-2024)", FULL_START,  FULL_END),
        ("TRAIN      (2019-2022)", TRAIN_START, TRAIN_END),
        ("TEST       (2023-2024)", TEST_START,  TEST_END),
    ]

    for label, start, end in periods:
        results_old = {}
        results_new = {}

        print(f"\nHesaplaniyor: {label} ...")
        for sym in SYMBOLS:
            try:
                results_old[sym] = run_backtest(sym, start, end, SmaCrossoverStrategy, INITIAL_CASH)
            except Exception as e:
                print(f"  [HATA] {sym} eski strateji: {e}")
            try:
                results_new[sym] = run_backtest(sym, start, end, FilteredSmaCrossoverStrategy, INITIAL_CASH)
            except Exception as e:
                print(f"  [HATA] {sym} yeni strateji: {e}")

        print_comparison_table(results_old, results_new, label)

    print("\n\nBacktest tamamlandi.")
