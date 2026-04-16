# -*- coding: utf-8 -*-
"""
paper_trader.py - Ana paper trading dongusu
Sinyal uretir, loglar. SEND_ORDERS=False iken emir GONDERMEZ (guvenli mod).
"""

import time
import pandas as pd
from datetime import datetime, timedelta

from data     import get_price_data, add_indicators, add_supertrend
from strategy import filtered_signals, supertrend_signals
from logger   import log_signal, log_info, log_error
from risk     import RiskManager
import broker

# ---------------------------------------------------------------------------
# Ayarlar
# ---------------------------------------------------------------------------

# Guvenli mod: False = sadece sinyal logla, emir GONDERME
# Emir gondermek icin True yap (Hafta 3 sonu)
SEND_ORDERS = True

# Islem yapilacak semboller
SYMBOLS = [
    # Emtia ETF — trend takipte kanıtlanmıs
    "GLD", "SLV", "USO", "GDX", "GDXJ", "XME", "COPX",
    # Sektor ETF
    "XLE", "XLB", "XLI",
    # Genis piyasa ETF
    "QQQ", "DIA", "IWM",
    # Bireysel hisseler
    "AAPL", "MSFT",
]

# Grup A: Kriz varliklari — SMA crossover, SMA200 filtresi YOK
# En buyuk hareketleri uzun vade ortalamasinin altindan basliyor
# (enflasyon, kriz, USD dusus periodlari)
CRISIS_ASSETS = {"GLD", "SLV", "USO"}

# Grup B: Madencilik/emtia ETF — SMA crossover, SMA200 filtresi VAR
# Backtest: SMA bu grupta Supertrend'i geciyor (GDX +35.7% vs +23.9%)
MINING_ASSETS = {"GDX", "GDXJ"}

# Grup C: Sektor ETF, genis piyasa, hisseler — Supertrend
# Backtest: Supertrend bu grupta SMA'yi belirgin sekilde geciyor
# (XLE +47% vs -11.5%, XLI +51% vs +0.1%, QQQ +66.9% vs +20.8%)
SUPERTREND_ASSETS = {"XME", "COPX", "XLE", "XLB", "XLI", "QQQ", "DIA", "IWM", "AAPL", "MSFT"}

# Dongu aralik suresi (saniye)
LOOP_INTERVAL = 60

# SMA periyotlari
SMA_FAST = 20
SMA_SLOW = 50

# Veri penceresi: son N gun (SMA50 icin en az 60 gun lazim)
DATA_DAYS = 300  # SMA200 icin en az 250 is gunu gerekli

# ---------------------------------------------------------------------------
# Risk Yoneticisi
# ---------------------------------------------------------------------------

risk = RiskManager(capital=100000)

# Gunluk kayip takibi (basit, in-memory; her calistirildiginda sifirlanir)
_daily_loss = 0.0
_open_positions_count = 0


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
        df = add_indicators(df, sma_periods=[SMA_FAST, SMA_SLOW, 200])

        # --- Strateji grubuna gore sinyal uret ---
        if symbol in SUPERTREND_ASSETS:
            df = add_supertrend(df)
            df = supertrend_signals(df)
            strategy_type = "ST"
        else:
            # CRISIS_ASSETS: SMA200 filtresi YOK
            # MINING_ASSETS + diger SMA grubu: SMA200 filtresi VAR
            use_sma200 = symbol not in CRISIS_ASSETS
            df = filtered_signals(df, fast=SMA_FAST, slow=SMA_SLOW, use_sma200=use_sma200)
            strategy_type = "SMA"

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

        atr = float(last["atr"]) if "atr" in last and not pd.isna(last["atr"]) else None

        return {
            "symbol":        symbol,
            "action":        action,
            "price":         price,
            "sma20":         sma20,
            "sma50":         sma50,
            "rsi":           rsi,
            "atr":           atr,
            "strategy_type": strategy_type,
        }

    except Exception as e:
        log_error(f"analyze_symbol({symbol}) hatasi: {e}")
        return None


def handle_signal(result):
    """
    Sinyal logla; SEND_ORDERS=True ise emir gonder.
    Duplicate BUY onleme: zaten pozisyon varsa BUY gonderme.
    Risk kontrolleri: pozisyon limiti, gunluk kayip limiti, lot hesabi.
    """
    global _open_positions_count, _daily_loss

    symbol        = result["symbol"]
    action        = result["action"]
    price         = result["price"]
    sma20         = result["sma20"]
    sma50         = result["sma50"]
    rsi           = result["rsi"]
    atr           = result.get("atr")
    strategy_type = result.get("strategy_type", "SMA")

    # Her durumda logla (strateji tipini de ekle)
    log_signal(symbol, action, price, sma20, sma50, rsi)
    log_info(f"[STRATEJI] {symbol}: {strategy_type} modu")

    # --- Risk: gunluk kayip limiti kontrolu ---
    if risk.should_stop_trading(_daily_loss):
        log_info(
            f"[RISK] Gunluk kayip limiti asildi "
            f"(kayip={_daily_loss:.2f}, limit={risk.capital * risk.daily_loss_limit:.2f}). "
            f"Islem durduruldu."
        )
        return

    if action == "BUY":
        # --- Risk: max acik pozisyon kontrolu ---
        if not risk.can_open_position(_open_positions_count):
            log_info(
                f"[RISK] {symbol} BUY atlanadi: max acik pozisyon sayisina ulasildi "
                f"({_open_positions_count}/{risk.max_open_positions})."
            )
            return

        # --- Risk: pozisyon buyutu ve fiyat seviyeleri ---
        qty = risk.position_size(price)
        # ATR varsa dinamik stop/TP, yoksa sabit oran
        if atr:
            sl = risk.atr_stop_loss_price(price, atr, multiplier=2.0)
            tp = risk.atr_take_profit_price(price, atr, multiplier=4.0)
            sl_type = f"ATR({atr:.2f}x2)"
        else:
            sl = risk.stop_loss_price(price)
            tp = risk.take_profit_price(price)
            sl_type = "sabit %3"
        log_info(
            f"[RISK] {symbol} | Lot: {qty} adet | "
            f"Giris: {price:.2f} | SL: {sl:.2f} ({sl_type}) | TP: {tp:.2f} | "
            f"Max harcama: {risk.capital * risk.max_position_pct:.2f}"
        )

        if qty == 0:
            log_info(f"[RISK] {symbol} BUY atlanadi: hesaplanan lot 0 (fiyat cok yuksek).")
            return

    if not SEND_ORDERS:
        return  # Guvenli mod — burada dur

    # --- Asagisi sadece SEND_ORDERS=True oldugunda calisir ---

    if action == "BUY":
        pos = broker.get_position(symbol)
        if pos is not None:
            log_info(f"{symbol} icin zaten pozisyon var ({pos.qty} adet). BUY atlanadi.")
            return

        qty = risk.position_size(price)
        if qty == 0:
            log_info(f"{symbol} BUY atlanadi: hesaplanan lot 0.")
            return

        broker.place_buy_order(symbol, qty)
        _open_positions_count += 1

    elif action == "SELL":
        pos = broker.get_position(symbol)
        if pos is None:
            log_info(f"{symbol} icin acik pozisyon yok. SELL atlanadi.")
            return
        broker.place_sell_order(symbol, int(float(pos.qty)))
        _open_positions_count = max(0, _open_positions_count - 1)


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
    rs = risk.summary()
    log_info(
        f"[RISK] Sermaye: {rs['capital']:.0f} | "
        f"Max pozisyon: %{rs['max_position_pct']*100:.0f} ({rs['max_position_value']:.0f}) | "
        f"SL: %{rs['stop_loss_pct']*100:.0f} | TP: %{rs['take_profit_pct']*100:.0f} | "
        f"Max acik pozisyon: {rs['max_open_positions']} | "
        f"Gunluk kayip limiti: {rs['daily_loss_threshold']:.0f}"
    )
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
    rs = risk.summary()
    log_info(
        f"[RISK] Sermaye: {rs['capital']:.0f} | "
        f"Max pozisyon: %{rs['max_position_pct']*100:.0f} ({rs['max_position_value']:.0f}) | "
        f"SL: %{rs['stop_loss_pct']*100:.0f} | TP: %{rs['take_profit_pct']*100:.0f} | "
        f"Max acik pozisyon: {rs['max_open_positions']}"
    )
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
