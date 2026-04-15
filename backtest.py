# -*- coding: utf-8 -*-
"""
backtest.py - Backtrader ile SMA Crossover Backtest
Strateji: SMA20/SMA50 crossover, Stop-Loss %3, Take-Profit %6
Komisyon: %0.1, Pozisyon: sermayenin %95'i
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
    """yfinance'dan OHLCV verisi ceker, MultiIndex varsa duzlestirir."""
    df = yf.download(symbol, start=start, end=end, auto_adjust=True, progress=False)
    if df.empty:
        raise ValueError(f"{symbol} icin veri bulunamadi.")

    # yfinance 1.x MultiIndex kolonlarini duzlestir
    if isinstance(df.columns, pd.MultiIndex):
        df = df.xs(symbol, axis=1, level=1) if symbol in df.columns.get_level_values(1) else df
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.droplevel(1)

    df.columns = [c.lower() for c in df.columns]
    df = df.drop(columns=["adj close"], errors="ignore")

    # Backtrader zorunlu kolonlar: open, high, low, close, volume
    needed = ["open", "high", "low", "close", "volume"]
    df = df[[c for c in needed if c in df.columns]]

    # NaN satirlarini temizle
    df = df.dropna()
    return df


# ---------------------------------------------------------------------------
# Backtrader Data Feed
# ---------------------------------------------------------------------------

def make_feed(df):
    """DataFrame'i bt.feeds.PandasData'ya donusturur."""
    data = bt.feeds.PandasData(
        dataname=df,
        datetime=None,   # index kullan
        open="open",
        high="high",
        low="low",
        close="close",
        volume="volume",
        openinterest=-1,
    )
    return data


# ---------------------------------------------------------------------------
# Backtrader Stratejisi
# ---------------------------------------------------------------------------

class SmaCrossoverStrategy(bt.Strategy):
    params = dict(
        fast=20,
        slow=50,
        stop_pct=0.03,    # %3 stop-loss
        tp_pct=0.06,      # %6 take-profit
        stake_pct=0.95,   # sermayenin %95'i
    )

    def __init__(self):
        self.sma_fast = bt.indicators.SMA(self.data.close, period=self.p.fast)
        self.sma_slow = bt.indicators.SMA(self.data.close, period=self.p.slow)
        self.crossover = bt.indicators.CrossOver(self.sma_fast, self.sma_slow)

        # Trade takibi icin
        self.order = None
        self.buy_price = None

        # Istatistik icin
        self.trades = []

    def log(self, msg):
        pass  # Sessiz mod

    def notify_order(self, order):
        if order.status in [order.Submitted, order.Accepted]:
            return
        if order.status == order.Completed:
            if order.isbuy():
                self.buy_price = order.executed.price
        elif order.status in [order.Canceled, order.Margin, order.Rejected]:
            pass
        self.order = None

    def notify_trade(self, trade):
        if trade.isclosed:
            self.trades.append({
                "pnl": trade.pnl,
                "pnlcomm": trade.pnlcomm,
            })

    def next(self):
        if self.order:
            return

        # Pozisyon yok -> giris sinyali ara
        if not self.position:
            if self.crossover > 0:  # SMA20, SMA50'nin ustune cikti -> BUY
                cash = self.broker.getcash()
                price = self.data.close[0]
                size = math.floor((cash * self.p.stake_pct) / price)
                if size > 0:
                    self.order = self.buy(size=size)
                    self.buy_price = price
        else:
            price = self.data.close[0]

            # Stop-loss
            if price <= self.buy_price * (1 - self.p.stop_pct):
                self.order = self.sell(size=self.position.size)
                return

            # Take-profit
            if price >= self.buy_price * (1 + self.p.tp_pct):
                self.order = self.sell(size=self.position.size)
                return

            # Crossover asagi -> SELL
            if self.crossover < 0:
                self.order = self.sell(size=self.position.size)


# ---------------------------------------------------------------------------
# Backtest Calistirici
# ---------------------------------------------------------------------------

def run_backtest(symbol, start, end, initial_cash=10000.0):
    """Tek sembol icin backtest calistirir, sonuc sozlugunu dondurur."""
    df = fetch_data(symbol, start, end)

    cerebro = bt.Cerebro()
    cerebro.addstrategy(SmaCrossoverStrategy)
    cerebro.adddata(make_feed(df))
    cerebro.broker.setcash(initial_cash)
    cerebro.broker.setcommission(commission=0.001)  # %0.1

    # Drawdown analizi
    cerebro.addanalyzer(bt.analyzers.DrawDown, _name="drawdown")
    cerebro.addanalyzer(bt.analyzers.SharpeRatio, _name="sharpe",
                        riskfreerate=0.02, annualize=True, timeframe=bt.TimeFrame.Days)
    cerebro.addanalyzer(bt.analyzers.TradeAnalyzer, _name="trades")

    results = cerebro.run()
    strat = results[0]

    final_cash = cerebro.broker.getvalue()
    total_return = (final_cash - initial_cash) / initial_cash * 100

    # Drawdown
    dd = strat.analyzers.drawdown.get_analysis()
    max_dd = dd.get("max", {}).get("drawdown", 0.0)

    # Sharpe
    sharpe_data = strat.analyzers.sharpe.get_analysis()
    sharpe = sharpe_data.get("sharperatio", None)
    if sharpe is None:
        sharpe = 0.0

    # Trade analizi
    ta = strat.analyzers.trades.get_analysis()
    total_trades = ta.get("total", {}).get("closed", 0)

    won = ta.get("won", {})
    lost = ta.get("lost", {})
    won_count = won.get("total", 0)
    lost_count = lost.get("total", 0)

    win_rate = (won_count / total_trades * 100) if total_trades > 0 else 0.0

    avg_win = won.get("pnl", {}).get("average", 0.0) or 0.0
    avg_loss = lost.get("pnl", {}).get("average", 0.0) or 0.0

    return {
        "symbol": symbol,
        "start": start,
        "end": end,
        "initial_cash": initial_cash,
        "final_cash": final_cash,
        "total_return": total_return,
        "max_drawdown": max_dd,
        "total_trades": total_trades,
        "win_rate": win_rate,
        "avg_win": avg_win,
        "avg_loss": avg_loss,
        "sharpe": sharpe,
    }


# ---------------------------------------------------------------------------
# Sonuc Yazici
# ---------------------------------------------------------------------------

def print_result(res, label=""):
    sym = res["symbol"]
    title = f"{sym} Backtest Sonucu"
    if label:
        title += f" [{label}]"
    sep = "=" * (len(title) + 8)
    print(f"\n{sep}")
    print(f"==== {title} ====")
    print(f"{sep}")
    print(f"Donem               : {res['start']} -> {res['end']}")
    print(f"Baslangic Sermayesi : ${res['initial_cash']:,.0f}")
    print(f"Final Sermaye       : ${res['final_cash']:,.2f}")
    print(f"Toplam Getiri       : %{res['total_return']:.2f}")
    print(f"Max Drawdown        : %{res['max_drawdown']:.2f}")
    print(f"Toplam Islem        : {res['total_trades']}")
    print(f"Kazanma Orani       : %{res['win_rate']:.2f}")
    print(f"Ortalama Kar        : ${res['avg_win']:.2f}")
    print(f"Ortalama Zarar      : ${res['avg_loss']:.2f}")
    print(f"Sharpe Ratio        : {res['sharpe']:.2f}")


# ---------------------------------------------------------------------------
# Ana Giris
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    SYMBOLS = ["AAPL", "MSFT", "SPY", "GLD", "USO", "SLV", "GDX"]
    INITIAL_CASH = 10000.0

    # Tam donem
    FULL_START = "2019-01-01"
    FULL_END   = "2024-12-31"

    # Train / Test bolumu
    TRAIN_START = "2019-01-01"
    TRAIN_END   = "2022-12-31"
    TEST_START  = "2023-01-01"
    TEST_END    = "2024-12-31"

    print("\n" + "#" * 60)
    print("  TAM DONEM BACKTEST (2019-2024)")
    print("#" * 60)

    for sym in SYMBOLS:
        try:
            res = run_backtest(sym, FULL_START, FULL_END, INITIAL_CASH)
            print_result(res, "TAM DONEM")
        except Exception as e:
            print(f"\n[HATA] {sym} tam donem: {e}")

    print("\n\n" + "#" * 60)
    print("  TRAIN DONEMI BACKTEST (2019-2022)")
    print("#" * 60)

    for sym in SYMBOLS:
        try:
            res = run_backtest(sym, TRAIN_START, TRAIN_END, INITIAL_CASH)
            print_result(res, "TRAIN 2019-2022")
        except Exception as e:
            print(f"\n[HATA] {sym} train: {e}")

    print("\n\n" + "#" * 60)
    print("  TEST DONEMI BACKTEST (2023-2024)")
    print("#" * 60)

    for sym in SYMBOLS:
        try:
            res = run_backtest(sym, TEST_START, TEST_END, INITIAL_CASH)
            print_result(res, "TEST 2023-2024")
        except Exception as e:
            print(f"\n[HATA] {sym} test: {e}")

    print("\n\nBacktest tamamlandi.")
