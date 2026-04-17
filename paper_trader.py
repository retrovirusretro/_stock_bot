# -*- coding: utf-8 -*-
"""
paper_trader.py - Ana paper trading dongusu
Sinyal uretir, loglar. SEND_ORDERS=False iken emir GONDERMEZ (guvenli mod).
"""

import time
import pandas as pd
from datetime import datetime, timedelta

from data      import get_price_data, add_indicators, add_supertrend
from strategy  import filtered_signals, supertrend_signals, rsi_bounce_signals
from logger    import log_signal, log_info, log_error
from risk      import RiskManager
import broker
import reporter
import sentiment

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

# Drawdown + ardisik kayip takibi
_peak_equity         = 0.0   # Bot basladigindan beri gorulmus en yuksek equity
_consecutive_losses  = 0     # Arka arkaya kac gun kayip
_last_pnl_date       = ""    # Son PnL hesaplama tarihi (gun basi reset icin)


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
            rsi_bounce_active = False
        else:
            # CRISIS_ASSETS: SMA200 filtresi YOK
            # MINING_ASSETS + diger SMA grubu: SMA200 filtresi VAR
            use_sma200 = symbol not in CRISIS_ASSETS
            df = filtered_signals(df, fast=SMA_FAST, slow=SMA_SLOW, use_sma200=use_sma200)
            # RSI Bounce ek katmanı — SMA grubu için
            df = rsi_bounce_signals(df, rsi_low=35, rsi_high=50)
            strategy_type = "SMA"
            rsi_bounce_active = True

        last = df.iloc[-1]

        # Son kapanistaki indikatörler
        price = float(last["close"])
        sma20 = float(last[f"sma{SMA_FAST}"])
        sma50 = float(last[f"sma{SMA_SLOW}"])
        rsi   = float(last["rsi"])

        # --- SMA crossover son sinyali ---
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

        # --- RSI Bounce ek sinyali (SMA grubu) ---
        # Eğer SMA crossover HOLD ise ve RSI bounce yeni bir BUY ürettiyse → BUY'a yükselt
        if rsi_bounce_active and action == "HOLD":
            rsi_buy_rows  = df[df["rsi_position"] ==  2]
            rsi_sell_rows = df[df["rsi_position"] == -2]
            last_rsi_buy  = rsi_buy_rows.index[-1]  if not rsi_buy_rows.empty  else None
            last_rsi_sell = rsi_sell_rows.index[-1] if not rsi_sell_rows.empty else None

            if last_rsi_buy and (not last_rsi_sell or last_rsi_buy > last_rsi_sell):
                action       = "BUY"
                strategy_type = "RSI_BOUNCE"
                log_info(f"[STRATEJI] {symbol}: RSI Bounce BUY sinyali ({last_rsi_buy.date()})")

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


def _update_risk_state(current_equity):
    """
    Her iterasyon sonunda cagrilir:
    - Peak equity'yi gunceller
    - Ardisik kayip sayacini gunceller (gun basi degisince)
    """
    global _peak_equity, _consecutive_losses, _last_pnl_date

    # Peak equity takibi
    if current_equity > _peak_equity:
        _peak_equity = current_equity
        log_info(f"[RISK] Yeni peak equity: ${_peak_equity:,.2f}")

    # Drawdown kontrolu (loglama amacli)
    dd_pct = risk.drawdown_pct(current_equity, _peak_equity) * 100
    if dd_pct >= 5.0:
        log_info(
            f"[RISK] Drawdown uyarisi: %{dd_pct:.1f} "
            f"(peak=${_peak_equity:,.2f}, guncel=${current_equity:,.2f})"
        )

    # Ardisik kayip: sadece gun degisiminde guncelle
    today = __import__("datetime").date.today().isoformat()
    if today != _last_pnl_date and _last_pnl_date != "":
        # Yeni gun — onceki gun karda miydi yoksa zararli miydi?
        today_data = reporter.get_today()
        if today_data and today_data["change"] < 0:
            _consecutive_losses += 1
            log_info(
                f"[RISK] Ardisik kayip: {_consecutive_losses} gun "
                f"(limit: {risk.consecutive_loss_limit})"
            )
        elif today_data and today_data["change"] >= 0:
            if _consecutive_losses > 0:
                log_info(f"[RISK] Kazancli gun — ardisik kayip sayaci sifirlanıyor.")
            _consecutive_losses = 0

    _last_pnl_date = today


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

    # --- Risk: ardisik kayip devre kesici ---
    if risk.check_consecutive_losses(_consecutive_losses):
        log_info(
            f"[RISK] {symbol} BUY atlanadi: {_consecutive_losses} gun ust uste kayip "
            f"(limit: {risk.consecutive_loss_limit} gun). Islem duraklatildi."
        )
        return

    if action == "BUY":
        # --- Sentiment filtresi ---
        if not sentiment.should_allow_buy(symbol):
            return   # Negatif haber — BUY atla (loglama sentiment.py içinde yapildi)

        # --- Risk: max acik pozisyon kontrolu ---
        if not risk.can_open_position(_open_positions_count):
            log_info(
                f"[RISK] {symbol} BUY atlanadi: max acik pozisyon sayisina ulasildi "
                f"({_open_positions_count}/{risk.max_open_positions})."
            )
            return

        # --- Kelly Criterion pozisyon boyutu ---
        # En az 10 gunluk performans verisi varsa Kelly kullan, yoksa standart
        try:
            perf = reporter.get_performance_stats()
            if perf["trading_days"] >= 10:
                qty = risk.kelly_position_size(
                    price,
                    win_rate     = perf["win_rate"],
                    avg_win_pct  = perf["avg_win_pct"],
                    avg_loss_pct = perf["avg_loss_pct"],
                )
                log_info(
                    f"[KELLY] {symbol}: win_rate={perf['win_rate']:.0%} | "
                    f"avg_win={perf['avg_win_pct']:.3%} | "
                    f"avg_loss={perf['avg_loss_pct']:.3%} | qty={qty}"
                )
            else:
                qty = risk.position_size(price)
                log_info(f"[KELLY] {symbol}: yeterli veri yok ({perf['trading_days']} gun) — standart boyut: qty={qty}")
        except Exception as e:
            qty = risk.position_size(price)
            log_error(f"Kelly hesaplama hatasi: {e} — standart boyuta donuluyor")

        # --- ATR tabanlı stop/TP ---
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

        # API hatasi: pozisyon durumu bilinmiyor -> guvenli tarafta kal, BUY atla
        if pos is broker.POSITION_UNKNOWN:
            log_error(
                f"{symbol} BUY atlanadi: pozisyon sorgulanamadi (API hatasi). "
                f"Duplicate order riski onlendi."
            )
            return

        if pos is not None:
            log_info(f"{symbol} icin zaten pozisyon var ({pos.qty} adet). BUY atlanadi.")
            return

        qty = risk.position_size(price)
        if qty == 0:
            log_info(f"{symbol} BUY atlanadi: hesaplanan lot 0.")
            return

        # Sanity cap: fiyat verisi bozuksa qty patlayabilir (orn: price=5 -> qty=1000)
        QTY_MAX = 200
        if qty > QTY_MAX:
            log_error(
                f"{symbol} BUY atlanadi: anormal lot hesabi "
                f"(qty={qty}, fiyat={price:.2f}). Veri sorunu olmali."
            )
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

    # Alpaca'daki gercek acik pozisyon sayisini al
    # (bot yeniden baslarsa _open_positions_count sifirlanir — senkronize et)
    global _open_positions_count, _peak_equity, _consecutive_losses
    _open_positions_count = broker.get_open_positions_count()

    # Peak equity'yi mevcut bakiyeden baslatiyoruz
    try:
        acct_init = broker.get_account()
        if acct_init:
            _peak_equity = float(acct_init["equity"])
            log_info(f"[RISK] Baslangic equity: ${_peak_equity:,.2f} | Peak: ${_peak_equity:,.2f}")
    except Exception as e:
        log_error(f"Baslangic equity alinamadi: {e}")

    iteration = 0

    while True:
        iteration += 1
        log_info(f"--- Iterasyon {iteration} | {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} ---")

        # Market acik mi?
        if not broker.is_market_open():
            log_info("Market kapali. Bekleniyor...")
            time.sleep(LOOP_INTERVAL)
            continue

        # --- Drawdown devre kesici ---
        # Her iterasyonda equity cek, drawdown limiti asildiysa BUY gonderme
        _drawdown_halt = False
        try:
            acct_chk = broker.get_account()
            if acct_chk and _peak_equity > 0:
                cur_eq = float(acct_chk["equity"])
                if risk.check_drawdown(cur_eq, _peak_equity):
                    dd_pct = risk.drawdown_pct(cur_eq, _peak_equity) * 100
                    log_info(
                        f"[RISK] DRAWDOWN LIMITI ASILDI: %{dd_pct:.1f} "
                        f"(peak=${_peak_equity:,.2f}, guncel=${cur_eq:,.2f}, "
                        f"limit=%{risk.max_drawdown_pct*100:.0f}). "
                        f"Yeni BUY emirleri durduruldu."
                    )
                    _drawdown_halt = True
        except Exception as e:
            log_error(f"Drawdown kontrolu hatasi: {e}")

        # Her sembol icin analiz
        for symbol in SYMBOLS:
            result = analyze_symbol(symbol)
            if result:
                # Drawdown haltinda sadece SELL sinyallerine izin ver
                if _drawdown_halt and result.get("action") == "BUY":
                    log_info(f"[RISK] {symbol} BUY drawdown halti nedeniyle atlandi.")
                    continue
                handle_signal(result)
            else:
                log_error(f"{symbol} analiz edilemedi, atlaniyor.")

        # Gunluk PnL raporu + drawdown/ardisik kayip kontrolleri
        try:
            acct = broker.get_account()
            if acct:
                pos_symbols = broker.get_position_symbols()
                reporter.update(acct["equity"], pos_symbols)
                _update_risk_state(float(acct["equity"]))
        except Exception as e:
            log_error(f"PnL guncelleme hatasi: {e}")

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

    global _open_positions_count
    _open_positions_count = broker.get_open_positions_count()

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
