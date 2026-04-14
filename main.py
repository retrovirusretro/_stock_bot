# -*- coding: utf-8 -*-
"""
main.py - Ana calistirici
Hafta 1: Veri + Sinyal testi
Hafta 2: Backtest eklenecek
Hafta 3: Paper trading eklenecek
Hafta 4: Risk modulu + Railway deploy
"""

from data import get_price_data, add_sma, add_rsi, plot_chart
from strategy import sma_crossover_signals, print_signals

# Ayarlar
SYMBOLS = ["AAPL", "MSFT", "SPY", "GLD", "USO"]
START   = "2020-01-01"
END     = "2024-12-31"


def run():
    print("=" * 60)
    print("  Trading Bot - Hafta 1: Veri & Sinyal Analizi")
    print("=" * 60)

    for sym in SYMBOLS:
        print(f"\n{'--'*25}")
        print(f"  {sym}")
        print(f"{'--'*25}")

        df = get_price_data(sym, START, END)
        df = add_sma(df, [20, 50, 200])
        df = add_rsi(df, 14)
        df = sma_crossover_signals(df, fast=20, slow=50)
        print_signals(df, last_n=5)
        plot_chart(df, sym)

    print("\n[OK] Hafta 1 tamamlandi!")


if __name__ == "__main__":
    run()
