# -*- coding: utf-8 -*-
"""
logger.py - Trading bot log modulu
ASCII-only log mesajlari, dosya + konsol cikti
"""

import os
import sys
import logging
from datetime import datetime

# ---------------------------------------------------------------------------
# Log dizini ve dosya yolu
# ---------------------------------------------------------------------------
LOG_DIR  = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs")
LOG_FILE = os.path.join(LOG_DIR, "trading.log")

os.makedirs(LOG_DIR, exist_ok=True)

# ---------------------------------------------------------------------------
# Logger kurulumu
# ---------------------------------------------------------------------------
_logger = logging.getLogger("trading_bot")
_logger.setLevel(logging.DEBUG)

# Kanal eklenmemisse ekle (modul tekrar import edilirse duplicate olmaz)
if not _logger.handlers:
    # Dosya handler — append mode, UTF-8 (ASCII-only mesaj yazilacak)
    _fh = logging.FileHandler(LOG_FILE, mode="a", encoding="utf-8")
    _fh.setLevel(logging.DEBUG)

    # Konsol handler — cp1254 uyumlu, sadece ASCII yazilacak
    _ch = logging.StreamHandler(sys.stdout)
    _ch.setLevel(logging.DEBUG)

    # Sadece mesaji ilet; zaman damgasini biz manuel ekleyecegiz
    _fmt = logging.Formatter("%(message)s")
    _fh.setFormatter(_fmt)
    _ch.setFormatter(_fmt)

    _logger.addHandler(_fh)
    _logger.addHandler(_ch)


def _ts():
    """Simdi ki zaman damgasini string olarak dondur."""
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


# ---------------------------------------------------------------------------
# Public fonksiyonlar
# ---------------------------------------------------------------------------

def log_signal(symbol, action, price, sma20, sma50, rsi):
    """
    Sinyal logu.

    Ornek:
        2024-01-15 14:32:01 | AAPL | SIGNAL: BUY  | PRICE: 185.20 | SMA20: 183.10 | SMA50: 179.40 | RSI: 58.2
    """
    msg = (
        f"{_ts()} | {symbol:<6} | SIGNAL: {action:<4} "
        f"| PRICE: {price:>8.2f} "
        f"| SMA20: {sma20:>8.2f} "
        f"| SMA50: {sma50:>8.2f} "
        f"| RSI: {rsi:>5.1f}"
    )
    _logger.info(msg)


def log_order(symbol, action, qty, status):
    """
    Emir logu.

    Ornek:
        2024-01-15 14:32:01 | AAPL | ORDER: BUY   | QTY: 5 | STATUS: submitted
    """
    msg = (
        f"{_ts()} | {symbol:<6} | ORDER: {action:<5} "
        f"| QTY: {qty} "
        f"| STATUS: {status}"
    )
    _logger.info(msg)


def log_info(message):
    """
    Genel bilgi logu.

    Ornek:
        2024-01-15 14:32:01 | INFO  | Baglanti kuruldu. Hesap bakiyesi: $100000.00
    """
    msg = f"{_ts()} | INFO  | {message}"
    _logger.info(msg)


def log_error(message):
    """
    Hata logu.

    Ornek:
        2024-01-15 14:32:01 | ERROR | API baglantisi kesildi: timeout
    """
    msg = f"{_ts()} | ERROR | {message}"
    _logger.error(msg)


# ---------------------------------------------------------------------------
# Dogrudan calistirilirsa demo
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    log_info("Logger test basliyor.")
    log_signal("AAPL", "BUY",  185.20, 183.10, 179.40, 58.2)
    log_signal("MSFT", "SELL", 415.30, 410.00, 405.50, 72.1)
    log_signal("GLD",  "HOLD", 195.00, 194.00, 192.00, 51.0)
    log_order("AAPL", "BUY",  5, "submitted")
    log_order("MSFT", "SELL", 3, "filled")
    log_info("Hesap bakiyesi: $98500.00")
    log_error("API baglantisi kesildi: timeout")
    print(f"\nLog dosyasi: {LOG_FILE}")
