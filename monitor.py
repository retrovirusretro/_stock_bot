# -*- coding: utf-8 -*-
"""
monitor.py - Canli bot izleme paneli
Terminalde calistir: python monitor.py
Her 60 saniyede ekrani temizler, guncel tablo gosterir.
"""

import os
import time
from datetime import datetime
import sys

# Proje dizinini path'e ekle
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from data import get_price_data, add_sma, add_rsi
from strategy import sma_crossover_signals
from broker import get_account, get_position, is_market_open, get_latest_price

SYMBOLS   = ["AAPL", "MSFT", "GLD", "USO"]
REFRESH   = 60  # saniye


def clear():
    os.system("cls" if os.name == "nt" else "clear")


def signal_icon(signal):
    return {"BUY": ">> BUY", "SELL": "<< SELL", "HOLD": "-- HOLD"}.get(signal, signal)


def rsi_status(rsi):
    if rsi is None:
        return "?"
    if rsi >= 70:
        return f"{rsi:.1f} [ASIRI ALIM]"
    if rsi <= 30:
        return f"{rsi:.1f} [ASIRI SATIM]"
    return f"{rsi:.1f}"


def run_monitor():
    while True:
        clear()
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        print("=" * 65)
        print(f"  TRADING BOT MONITOR          {now}")
        print("=" * 65)

        # Hesap bilgisi
        account = get_account()
        market  = is_market_open()

        if account:
            print(f"  Hesap    : ${account['equity']:>12,.2f}  |  "
                  f"Buying Power: ${account['buying_power']:>12,.2f}")
        print(f"  Market   : {'ACIK  *** ISLEM SAATI ***' if market else 'KAPALI (NYSE 16:30-23:00 TR)'}")
        print("-" * 65)

        # Her sembol icin sinyal
        print(f"  {'SEMBOL':<6} {'FIYAT':>8} {'SMA20':>8} {'SMA50':>8} {'RSI':>12}  SINYAL")
        print("-" * 65)

        end   = datetime.now().strftime("%Y-%m-%d")
        start = "2025-10-01"  # SMA50 icin yeterli gecmis

        for sym in SYMBOLS:
            try:
                df = get_price_data(sym, start, end)
                df = add_sma(df, [20, 50])
                df = add_rsi(df, 14)
                df = sma_crossover_signals(df, 20, 50)

                last     = df.iloc[-1]
                price    = float(last["close"])
                sma20    = float(last["sma20"])
                sma50    = float(last["sma50"])
                rsi      = float(last["rsi"]) if "rsi" in last else None
                signal   = "BUY" if last["signal"] == 1 else ("SELL" if last["signal"] == -1 else "HOLD")

                # Acik pozisyon var mi?
                pos = get_position(sym)
                pos_str = f" [POS: {float(pos.qty):.0f} adet]" if pos else ""

                print(f"  {sym:<6} "
                      f"{price:>8.2f} "
                      f"{sma20:>8.2f} "
                      f"{sma50:>8.2f} "
                      f"{rsi_status(rsi):>12}  "
                      f"{signal_icon(signal)}{pos_str}")

            except Exception as e:
                print(f"  {sym:<6} HATA: {e}")

        print("-" * 65)
        print()
        print("  TERIMLER:")
        print("  SMA20      : Son 20 gun ortalama fiyat (kisa vadeli trend)")
        print("  SMA50      : Son 50 gun ortalama fiyat (orta vadeli trend)")
        print("  RSI        : Guc gostergesi (70+ = asiri alim, 30- = asiri satim)")
        print("  BUY sinyal : SMA20 > SMA50 (yukari crossover)")
        print("  SELL sinyal: SMA20 < SMA50 (asagi crossover)")
        print("  HOLD       : Crossover yok, bekle")
        print()
        print(f"  Sonraki guncelleme: {REFRESH} saniye sonra  |  Cikmak icin CTRL+C")
        print("=" * 65)

        time.sleep(REFRESH)


if __name__ == "__main__":
    print("Monitor basliyor...")
    try:
        run_monitor()
    except KeyboardInterrupt:
        print("\nMonitor durduruldu.")
