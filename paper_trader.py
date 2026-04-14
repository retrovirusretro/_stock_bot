# -*- coding: utf-8 -*-
"""
paper_trader.py - Ana paper trading dongusu
Sinyal uretir, loglar. SEND_ORDERS=False iken emir GONDERMEZ (guvenli mod).
"""

import time
from datetime import datetime, timedelta

from data     import get_price_data, add_sma, add_rsi
from strategy import sma_crossover_signals
from logger   import log_signal, log_info, log_error
import broker

# ---------------------------------------------------------------------------
# Ayarlar
# ---------------------------------------------------------------------------

# Guvenli mod: False = sadece sinyal logla, emir GONDERME
# Emir gondermek icin True yap (Hafta 3 sonu)
SEND_ORDERS = False

# Islem yapilacak semboller
SYMBOLS = ["AAPL", "MSFT", "GLD", "USO"]

# Dongu aralik suresi (saniye)
LOOP_INTERVAL = 60

# SMA periyotlari
SMA_FAST = 20
SMA_SLOW = 50

# Veri penceresi: son N gun (SMA50 icin en az 60 gun lazim)
DATA_DAYS = 120


# ---------------------------------------------------------------------------
# Yardimci fonksiyonlar
# ---------------------------------------------------------------------------

def get_date_range():
    """Bugun'e kadar son DATA_DAYS gunluk tarih araligini dondur."""
    end   = datetime.today().strftime("%Y-%m-%d")
    start = (datetime.today() - timedelta(days=DATA_DAYS)).strftime("%Y-%m-%d")
    return start, end


def analyze_symbol(symbol):
    """
    Tek sembol icin veri cek, indikatör hesapla, sinyal uret.

    Returns:
        dict: {symbol, action, price, sma20, sma50, rsi}
        veya None (veri alinamazsa)
    """
    try:
        start, end = get_date_range()
        df = get_price_data(symbol, start, end)
        df = add_sma(df, [SMA_FAST, SMA_SLOW])
        df = add_rsi(df)
        df = sma_crossover_signals(df, fast=SMA_FAST, slow=SMA_SLOW)

        last = df.iloc[-1]

        # Son kapanistaki indikatörler
        price = float(last["close"])
        sma20 = float(last[f"sma{SMA_FAST}"])
        sma50 = float(last[f"sma{SMA_SLOW}"])
        rsi   = float(last["rsi"])

        # Son crossover sinyali (butun history'e bakiyoruz)
        buy_rows  = df[df["position"] ==  2]
        sell_rows = df[df["position"] == -2]

        last_buy_date  = buy_rows.index[-1]  if not buy_rows.empty  else None
        last_sell_date = sell_rows.index[-1] if not sell_rows.empty else None

        # En son crossover hangisi?
        action = "HOLD"
        if last_buy_date and last_sell_date:
            action = "BUY" if last_buy_date > last_sell_date else "SELL"
        elif last_buy_date:
            action = "BUY"
        elif last_sell_date:
            action = "SELL"

        return {
            "symbol": symbol,
            "action": action,
            "price":  price,
            "sma20":  sma20,
            "sma50":  sma50,
            "rsi":    rsi,
        }

    except Exception as e:
        log_error(f"analyze_symbol({symbol}) hatasi: {e}")
        return None


def handle_signal(result):
    """
    Sinyal logla; SEND_ORDERS=True ise emir gonder.
    Duplicate BUY onleme: zaten pozisyon varsa BUY gonderme.
    """
    symbol = result["symbol"]
    action = result["action"]
    price  = result["price"]
    sma20  = result["sma20"]
    sma50  = result["sma50"]
    rsi    = result["rsi"]

    # Her durumda logla
    log_signal(symbol, action, price, sma20, sma50, rsi)

    if not SEND_ORDERS:
        return  # Guvenli mod — burada dur

    # --- Asagisi sadece SEND_ORDERS=True oldugunda calisir ---

    if action == "BUY":
        pos = broker.get_position(symbol)
        if pos is not None:
            log_info(f"{symbol} icin zaten pozisyon var ({pos.qty} adet). BUY atlanadi.")
            return

        # Basit lot hesabi: buying power'in %5'i ile al (max 10 adet)
        account = broker.get_account()
        if account is None:
            log_error(f"{symbol} BUY: hesap bilgisi alinamadi.")
            return

        max_spend = account["buying_power"] * 0.05
        qty = max(1, min(10, int(max_spend / price)))
        broker.place_buy_order(symbol, qty)

    elif action == "SELL":
        pos = broker.get_position(symbol)
        if pos is None:
            log_info(f"{symbol} icin acik pozisyon yok. SELL atlanadi.")
            return
        broker.place_sell_order(symbol, int(float(pos.qty)))


# ---------------------------------------------------------------------------
# Ana dongu
# ---------------------------------------------------------------------------

def run():
    """Paper trading ana dongusu."""
    log_info("=" * 60)
    log_info("Paper trader basliyor.")
    log_info(f"Semboller  : {', '.join(SYMBOLS)}")
    log_info(f"Emir modu  : {'AKTIF' if SEND_ORDERS else 'KAPALI (guvenli mod)'}")
    log_info(f"Aralik     : {LOOP_INTERVAL} saniye")
    log_info("=" * 60)

    # Ilk baglanti kontrolu
    account = broker.connect()
    if account is None:
        log_error("Alpaca baglantisi kurulamadi. Cikiliyor.")
        return

    iteration = 0

    while True:
        iteration += 1
        log_info(f"--- Iterasyon {iteration} | {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} ---")

        # Market acik mi?
        if not broker.is_market_open():
            log_info("Market kapali. Bekleniyor...")
            time.sleep(LOOP_INTERVAL)
            continue

        # Her sembol icin analiz
        for symbol in SYMBOLS:
            result = analyze_symbol(symbol)
            if result:
                handle_signal(result)
            else:
                log_error(f"{symbol} analiz edilemedi, atlaniyor.")

        log_info(f"Tum semboller islendi. {LOOP_INTERVAL}s bekleniyor...")
        time.sleep(LOOP_INTERVAL)


# ---------------------------------------------------------------------------
# Tek iterasyon modu (test icin)
# ---------------------------------------------------------------------------

def run_once():
    """Sadece bir iterasyon calistir (test/debug icin)."""
    log_info("=" * 60)
    log_info("Paper trader SINGLE-RUN modu.")
    log_info(f"Semboller  : {', '.join(SYMBOLS)}")
    log_info(f"Emir modu  : {'AKTIF' if SEND_ORDERS else 'KAPALI (guvenli mod)'}")
    log_info("=" * 60)

    account = broker.connect()
    if account is None:
        log_error("Alpaca baglantisi kurulamadi.")
        return False

    market_open = broker.is_market_open()
    log_info(f"Market durumu: {'ACIK' if market_open else 'KAPALI'}")

    for symbol in SYMBOLS:
        result = analyze_symbol(symbol)
        if result:
            handle_signal(result)
        else:
            log_error(f"{symbol} analiz edilemedi, atlaniyor.")

    log_info("Single-run tamamlandi.")
    return True


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import sys

    # python paper_trader.py --once   → tek iterasyon
    # python paper_trader.py          → surekli dongu
    if "--once" in sys.argv:
        run_once()
    else:
        try:
            run()
        except KeyboardInterrupt:
            log_info("Kullanici tarafindan durduruldu (Ctrl+C).")
