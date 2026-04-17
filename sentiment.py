# -*- coding: utf-8 -*-
"""
sentiment.py - Haber/Sentiment filtresi

Alpha Vantage NEWS_SENTIMENT API kullanir.
API key yoksa veya hata olursa sessizce BUY'a izin verir (fail-open).

Konfigürasyon (.env):
    ALPHAVANTAGE_API_KEY=your_key_here   (ucretsiz: alphavantage.co/support)

Limitler:
    Ucretsiz plan: 25 istek/gun
    Cache: 4 saat (sembol basina) → max ~6 istek/gun × 15 sembol = asla dolmaz
    Sadece BUY sinyali uretildigi anda cagrilir (her 60s degil)

Sentiment skoru: -1 (cok negatif) → +1 (cok pozitif)
BUY engelleme esigi: -0.25 (oldukca negatif haberler varsa atla)
"""

import json
import os
import requests
from datetime import datetime, timedelta

from logger import log_info, log_error

# ---------------------------------------------------------------------------
# Sabitler
# ---------------------------------------------------------------------------

_BASE_DIR          = os.path.dirname(os.path.abspath(__file__))
_CACHE_FILE        = os.path.join(_BASE_DIR, "logs", "sentiment_cache.json")
_CACHE_TTL_HOURS   = 4       # Kac saat cache'de tut
_NEGATIVE_THRESHOLD = -0.25  # Bu skorun altindaysa BUY engelle
_API_URL           = "https://www.alphavantage.co/query"


# ---------------------------------------------------------------------------
# Cache yardimcilari
# ---------------------------------------------------------------------------

def _load_cache():
    if not os.path.exists(_CACHE_FILE):
        return {}
    try:
        with open(_CACHE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _save_cache(data):
    os.makedirs(os.path.dirname(_CACHE_FILE), exist_ok=True)
    try:
        with open(_CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    except Exception:
        pass


def _get_cached(symbol):
    """Cache'den taze deger varsa dondurur, yoksa None."""
    cache = _load_cache()
    entry = cache.get(symbol)
    if not entry:
        return None
    try:
        ts = datetime.fromisoformat(entry["timestamp"])
        if datetime.now() - ts < timedelta(hours=_CACHE_TTL_HOURS):
            return entry["score"]
    except Exception:
        pass
    return None


def _set_cached(symbol, score):
    cache = _load_cache()
    cache[symbol] = {
        "timestamp": datetime.now().isoformat(),
        "score":     score,
    }
    _save_cache(cache)


# ---------------------------------------------------------------------------
# Alpha Vantage API
# ---------------------------------------------------------------------------

def _fetch_sentiment(symbol, api_key):
    """
    Alpha Vantage'dan sembol icin sentiment skoru ceker.

    Returns:
        float: -1 ile +1 arasi skor
        None : API hatasi veya veri yoksa
    """
    try:
        resp = requests.get(
            _API_URL,
            params={
                "function": "NEWS_SENTIMENT",
                "tickers":  symbol,
                "apikey":   api_key,
                "limit":    50,
            },
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()

        # API limiti asildiysa
        if "Note" in data or "Information" in data:
            msg = data.get("Note") or data.get("Information", "")
            log_error(f"[SENTIMENT] API limiti: {msg[:80]}")
            return None

        feed = data.get("feed", [])
        if not feed:
            return 0.0  # Haber yok = nötr

        # Sembol-spesifik skor varsa onu al, yoksa genel skoru kullan
        scores = []
        for article in feed:
            for ticker_sent in article.get("ticker_sentiment", []):
                if ticker_sent.get("ticker") == symbol:
                    try:
                        scores.append(float(ticker_sent["ticker_sentiment_score"]))
                    except (KeyError, ValueError):
                        pass

        if not scores:
            # Genel makale skorlarina bak
            for article in feed:
                try:
                    scores.append(float(article.get("overall_sentiment_score", 0)))
                except (TypeError, ValueError):
                    pass

        if not scores:
            return 0.0

        avg_score = sum(scores) / len(scores)
        return round(avg_score, 4)

    except requests.exceptions.Timeout:
        log_error(f"[SENTIMENT] {symbol}: API timeout")
        return None
    except Exception as e:
        log_error(f"[SENTIMENT] {symbol}: {e}")
        return None


# ---------------------------------------------------------------------------
# Ana fonksiyon
# ---------------------------------------------------------------------------

def get_sentiment(symbol):
    """
    Sembol icin sentiment skoru dondurur (-1 ile +1).

    Cache'de taze veri varsa direkt dondurur.
    API key yoksa 0.0 (notr) dondurur.
    Hata durumunda 0.0 (fail-open: BUY'a izin ver).
    """
    # Cache kontrolu
    cached = _get_cached(symbol)
    if cached is not None:
        log_info(f"[SENTIMENT] {symbol}: cache'den skor={cached:.3f}")
        return cached

    # API key yoksa atla
    api_key = os.getenv("ALPHAVANTAGE_API_KEY", "").strip()
    if not api_key:
        return 0.0   # Key yok, nötr dön

    score = _fetch_sentiment(symbol, api_key)

    if score is None:
        return 0.0   # API hatasi — fail-open

    _set_cached(symbol, score)
    label = "POZITIF" if score > 0.15 else ("NEGATIF" if score < -0.15 else "NOTR")
    log_info(f"[SENTIMENT] {symbol}: skor={score:.3f} ({label})")
    return score


def should_allow_buy(symbol):
    """
    BUY emrine izin verilmeli mi?

    Returns:
        True  : Sentiment nötr veya pozitif → BUY geçebilir
        False : Sentiment çok negatif → BUY engelle
    """
    score = get_sentiment(symbol)
    allowed = score >= _NEGATIVE_THRESHOLD
    if not allowed:
        log_info(
            f"[SENTIMENT] {symbol} BUY ENGELLENDI: "
            f"skor={score:.3f} < esik={_NEGATIVE_THRESHOLD}"
        )
    return allowed


# ---------------------------------------------------------------------------
# Dogrudan calistirilirsa test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import sys
    sym = sys.argv[1] if len(sys.argv) > 1 else "AAPL"
    print(f"Sentiment testi: {sym}")
    score = get_sentiment(sym)
    print(f"  Skor   : {score:.4f}")
    print(f"  BUY OK : {should_allow_buy(sym)}")
