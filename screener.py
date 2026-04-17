# -*- coding: utf-8 -*-
"""
screener.py - S&P500 Supertrend Screener

Tum S&P500 sembollerini tarar; en guclu BUY sinyallerini dondurur.

Filtre:
    - Supertrend yonu: +1 (yukselis trendi)
    - ADX >= 20 (trend gucu var, ranging piyasa degil)
    - Vol ratio >= 0.5 (islem gorulmekte)

Siralama: ADX descending (en guclu trend once)
Cache: logs/screener_cache.json — 60 dakika gecerli
"""

import json
import os
import threading
import pandas as pd
import yfinance as yf
import ta
from datetime import datetime, timedelta

from data   import add_supertrend
from logger import log_info, log_error

# ---------------------------------------------------------------------------
# Sabitler
# ---------------------------------------------------------------------------

_BASE_DIR        = os.path.dirname(os.path.abspath(__file__))
CACHE_FILE       = os.path.join(_BASE_DIR, "logs", "screener_cache.json")
SYMBOLS_FILE     = os.path.join(_BASE_DIR, "logs", "sp500_symbols.json")
CACHE_TTL_MIN    = 60      # Tarama sonucu cache suresi (dakika)
SYMBOLS_TTL_HRS  = 24     # Sembol listesi cache suresi (saat)
DATA_DAYS        = 180    # Her sembol icin kac gunluk veri
BATCH_SIZE       = 50     # Tek yfinance cagrisinda kac sembol
TOP_N            = 20     # Kac sonuc dondurulsun
MIN_ADX          = 20     # Minimum ADX deger

_lock      = threading.Lock()
_is_running = False


# ---------------------------------------------------------------------------
# S&P500 sembol listesi
# ---------------------------------------------------------------------------

def get_sp500_symbols():
    """
    S&P500 sembol listesini dondurur.

    Oncelik sirasi:
      1. logs/sp500_symbols.json cache (24 saat gecerli)
      2. Wikipedia'dan cek + cache'e kaydet
      3. Wikipedia basarisizsa eski cache'i kullan (ne kadar eskiyse)

    Bu yaklasim Wikipedia'nin ayni IP'den tekrarlayan isteklere
    verdigi 403 hatasini onler.
    """
    import requests
    from io import StringIO

    os.makedirs(os.path.dirname(SYMBOLS_FILE), exist_ok=True)

    # 1. Taze cache var mi?
    if os.path.exists(SYMBOLS_FILE):
        try:
            with open(SYMBOLS_FILE, "r", encoding="utf-8") as f:
                cached = json.load(f)
            ts = datetime.fromisoformat(cached["timestamp"])
            if datetime.now() - ts < timedelta(hours=SYMBOLS_TTL_HRS):
                log_info(f"[SCREENER] S&P500: cache'den {len(cached['symbols'])} sembol alindi.")
                return cached["symbols"]
        except Exception:
            pass

    # 2. Wikipedia'dan cek
    try:
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            )
        }
        resp = requests.get(
            "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies",
            headers=headers, timeout=15
        )
        resp.raise_for_status()
        tables  = pd.read_html(StringIO(resp.text))
        tbl     = tables[0]
        symbols = [str(s).replace(".", "-") for s in tbl["Symbol"].tolist()]
        # Şirket adlarını da kaydet (Security kolonu)
        names   = tbl["Security"].tolist() if "Security" in tbl.columns else [""] * len(symbols)
        name_map = {sym: str(name) for sym, name in zip(symbols, names)}

        # Cache'e kaydet
        with open(SYMBOLS_FILE, "w", encoding="utf-8") as f:
            json.dump({
                "timestamp": datetime.now().isoformat(),
                "symbols":   symbols,
                "names":     name_map,
            }, f)

        log_info(f"[SCREENER] S&P500: Wikipedia'dan {len(symbols)} sembol alindi ve cache'lendi.")
        return symbols

    except Exception as e:
        log_error(f"[SCREENER] Wikipedia'dan liste alinamadi: {e}")

    # 3. Eski cache'i kullan (ne kadar eskiyse)
    if os.path.exists(SYMBOLS_FILE):
        try:
            with open(SYMBOLS_FILE, "r", encoding="utf-8") as f:
                cached = json.load(f)
            log_info(f"[SCREENER] Eski cache kullaniliyor ({len(cached['symbols'])} sembol).")
            return cached["symbols"]
        except Exception:
            pass

    log_error("[SCREENER] Sembol listesi hic alinamadi.")
    return []


# ---------------------------------------------------------------------------
# Tek sembol analizi
# ---------------------------------------------------------------------------

def get_name_map():
    """Cache'deki sembol→şirket adı sözlüğünü döndürür."""
    if os.path.exists(SYMBOLS_FILE):
        try:
            with open(SYMBOLS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            return data.get("names", {})
        except Exception:
            pass
    return {}


def _analyze_df(symbol, df):
    """
    Ham OHLCV DataFrame'inden sinyal hesaplar.

    Returns:
        dict veya None (veri yetersizse)
    """
    try:
        if len(df) < 30:
            return None

        df = df.copy()
        df.dropna(subset=["close"], inplace=True)
        if len(df) < 30:
            return None

        # ATR + ADX
        df["atr"] = ta.volatility.average_true_range(
            df["high"], df["low"], df["close"], window=14
        )
        df["adx"] = ta.trend.adx(
            df["high"], df["low"], df["close"], window=14
        )
        # RSI
        df["rsi"] = ta.momentum.rsi(df["close"], window=14)

        # Supertrend
        df = add_supertrend(df)

        last    = df.iloc[-1]
        avg_vol = df["volume"].tail(20).mean()
        last_vol= float(last["volume"]) if "volume" in last.index else 0

        def safe_float(val, default=0.0):
            try:
                v = float(val)
                return default if pd.isna(v) else v
            except Exception:
                return default

        return {
            "symbol":        symbol,
            "price":         round(safe_float(last["close"]), 2),
            "adx":           round(safe_float(last["adx"]),   1),
            "rsi":           round(safe_float(last["rsi"]),   1),
            "supertrend_dir": int(safe_float(last["supertrend_dir"])),
            "supertrend":    round(safe_float(last["supertrend"]), 2),
            "vol_ratio":     round(last_vol / avg_vol, 2) if avg_vol > 0 else 0.0,
            "signal":        "BUY" if safe_float(last["supertrend_dir"]) == 1 else "SELL",
        }
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Ana tarama fonksiyonu
# ---------------------------------------------------------------------------

def run_screen(top_n=TOP_N, min_adx=MIN_ADX):
    """
    Tum S&P500'u tarar. Sonuclari cache'e yazar, top_n en guclu sinyali dondurur.
    """
    symbols  = get_sp500_symbols()
    name_map = get_name_map()
    if not symbols:
        return []

    end   = datetime.today().strftime("%Y-%m-%d")
    start = (datetime.today() - timedelta(days=DATA_DAYS)).strftime("%Y-%m-%d")

    batches = [symbols[i:i + BATCH_SIZE] for i in range(0, len(symbols), BATCH_SIZE)]
    results = []

    log_info(f"[SCREENER] Tarama basliyor: {len(symbols)} sembol, {len(batches)} batch...")

    for idx, batch in enumerate(batches):
        try:
            raw = yf.download(
                batch,
                start=start, end=end,
                auto_adjust=True,
                progress=False,
                group_by="ticker",
            )

            for sym in batch:
                try:
                    # Tek sembol: MultiIndex olmuyor
                    if len(batch) == 1:
                        df = raw.copy()
                        if isinstance(df.columns, pd.MultiIndex):
                            df.columns = [c[0].lower() for c in df.columns]
                        else:
                            df.columns = [c.lower() for c in df.columns]
                    else:
                        # Cok sembol: raw[sym] -> tek sembol DataFrame
                        level0 = raw.columns.get_level_values(0).unique().tolist()
                        if sym not in level0:
                            continue
                        df = raw[sym].copy()
                        df.columns = [c.lower() for c in df.columns]

                    df = df.dropna(how="all")
                    result = _analyze_df(sym, df)
                    if result:
                        result["name"] = name_map.get(sym, "")
                        results.append(result)
                except Exception:
                    continue

            log_info(
                f"[SCREENER] Batch {idx + 1}/{len(batches)} tamam "
                f"({len(results)} analiz edildi)"
            )

        except Exception as e:
            log_error(f"[SCREENER] Batch {idx + 1} hatasi: {e}")

    # Filtrele ve sirala
    buy_signals = [
        r for r in results
        if r["signal"] == "BUY"
        and r["adx"] >= min_adx
        and r["vol_ratio"] >= 0.5
    ]
    buy_signals.sort(key=lambda x: x["adx"], reverse=True)
    top = buy_signals[:top_n]

    # Cache'e kaydet
    cache = {
        "timestamp":     datetime.now().isoformat(),
        "total_scanned": len(results),
        "total_buy":     len(buy_signals),
        "results":       top,
    }
    os.makedirs(os.path.dirname(CACHE_FILE), exist_ok=True)
    with open(CACHE_FILE, "w", encoding="utf-8") as f:
        json.dump(cache, f, indent=2, ensure_ascii=False)

    log_info(
        f"[SCREENER] Tamamlandi: {len(results)} tarandı, "
        f"{len(buy_signals)} BUY sinyali, top {len(top)} donduruldu."
    )
    return top


# ---------------------------------------------------------------------------
# Cache yoneticisi
# ---------------------------------------------------------------------------

def _load_cache():
    """Cache dosyasini okur. Gecersizse None dondurur."""
    if not os.path.exists(CACHE_FILE):
        return None
    try:
        with open(CACHE_FILE, "r", encoding="utf-8") as f:
            cache = json.load(f)
        ts = datetime.fromisoformat(cache["timestamp"])
        if datetime.now() - ts > timedelta(minutes=CACHE_TTL_MIN):
            return None  # Suresi dolmus
        return cache
    except Exception:
        return None


def get_or_trigger(force=False):
    """
    Cache tazeyse direkt dondurur.
    Cache yoksa / eskiyse / force=True ise arka planda tarama baslatir.

    Returns:
        (cache_data_or_None, is_running: bool)
    """
    global _is_running

    cached = _load_cache()

    if cached and not force:
        return cached, False

    if _is_running:
        return cached, True

    # Arka planda basla
    def _run():
        global _is_running
        with _lock:
            _is_running = True
            try:
                run_screen()
            finally:
                _is_running = False

    t = threading.Thread(target=_run, daemon=True)
    t.start()

    return cached, True  # Eski cache (veya None) + calisıyor


# ---------------------------------------------------------------------------
# Dogrudan calistirilirsa
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print("S&P500 screener calistiriliyor...")
    results = run_screen(top_n=20, min_adx=20)
    print(f"\nTop {len(results)} BUY sinyali (ADX sirasıyla):")
    print(f"{'Sembol':<8} {'Fiyat':>8} {'ADX':>6} {'RSI':>6} {'ST Dir':>7} {'Vol/Avg':>8}")
    print("-" * 50)
    for r in results:
        print(
            f"{r['symbol']:<8} "
            f"${r['price']:>7.2f} "
            f"{r['adx']:>6.1f} "
            f"{r['rsi']:>6.1f} "
            f"{'+1' if r['supertrend_dir'] == 1 else '-1':>7} "
            f"{r['vol_ratio']:>7.2f}x"
        )
