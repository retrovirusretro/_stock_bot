# -*- coding: utf-8 -*-
"""
broker.py - Alpaca paper trading API baglantisi
alpaca-py (yeni resmi SDK) kullanir.
pip install alpaca-py
"""

import os
from dotenv import load_dotenv
from alpaca.trading.client import TradingClient
from alpaca.trading.requests import MarketOrderRequest
from alpaca.trading.enums import OrderSide, TimeInForce
from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockLatestTradeRequest

from logger import log_info, log_error, log_order

# ---------------------------------------------------------------------------
# Sentinel: get_position() API hatasi durumunda None ile karistirmamak icin
# ---------------------------------------------------------------------------
POSITION_UNKNOWN = object()

# ---------------------------------------------------------------------------
# .env yukle
# ---------------------------------------------------------------------------
_ENV_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
load_dotenv(_ENV_PATH)

_API_KEY    = os.getenv("ALPACA_API_KEY")
_SECRET_KEY = os.getenv("ALPACA_SECRET_KEY")
_PAPER      = "paper-api" in os.getenv("ALPACA_BASE_URL", "paper-api")

# Lazy-init clients
_trading_client = None
_data_client    = None


def _get_trading_client():
    global _trading_client
    if _trading_client is None:
        _trading_client = TradingClient(_API_KEY, _SECRET_KEY, paper=_PAPER)
    return _trading_client


def _get_data_client():
    global _data_client
    if _data_client is None:
        _data_client = StockHistoricalDataClient(_API_KEY, _SECRET_KEY)
    return _data_client


# ---------------------------------------------------------------------------
# Public fonksiyonlar
# ---------------------------------------------------------------------------

def connect():
    """API baglantisi kur, hesap bilgisi dondur."""
    try:
        account = _get_trading_client().get_account()
        log_info(
            f"Baglanti kuruldu. "
            f"Hesap bakiyesi: ${float(account.equity):,.2f} | "
            f"Buying power: ${float(account.buying_power):,.2f} | "
            f"Durum: {account.status}"
        )
        return account
    except Exception as e:
        log_error(f"Baglanti hatasi: {e}")
        return None


def get_account():
    """Hesap bakiyesi ve buying power bilgisi dondurur."""
    try:
        account = _get_trading_client().get_account()
        return {
            "equity":       float(account.equity),
            "buying_power": float(account.buying_power),
            "status":       str(account.status),
        }
    except Exception as e:
        log_error(f"get_account hatasi: {e}")
        return None


def get_position(symbol):
    """
    Acik pozisyon varsa dondurur.
    Pozisyon yoksa          -> None
    API/network hatasi ise  -> POSITION_UNKNOWN (sentinel)

    KRITIK: Hata durumunda None degil POSITION_UNKNOWN dondurmak,
    duplicate order'i onler. handle_signal bu durumda BUY'u atlamalı.
    """
    try:
        return _get_trading_client().get_open_position(symbol)
    except Exception as e:
        msg = str(e).lower()
        if "position does not exist" in msg or "404" in msg:
            return None  # gercekten pozisyon yok
        log_error(f"get_position({symbol}) hatasi: {e}")
        return POSITION_UNKNOWN  # bilinmiyor — guvenli tarafta kal


def get_open_positions_count():
    """
    Alpaca'daki tum acik pozisyon sayisini dondurur.
    Bot yeniden basladiginda _open_positions_count'u gercekle senkronize eder.
    Hata durumunda 0 dondurur (muhafazakar: daha az emir gonderilebilir).
    """
    try:
        positions = _get_trading_client().get_all_positions()
        count = len(positions)
        log_info(f"Alpaca acik pozisyonlar: {count} adet ({[p.symbol for p in positions]})")
        return count
    except Exception as e:
        log_error(f"get_open_positions_count hatasi: {e}")
        return 0


def place_buy_order(symbol, qty):
    """Market order BUY gonder."""
    try:
        req = MarketOrderRequest(
            symbol=symbol,
            qty=qty,
            side=OrderSide.BUY,
            time_in_force=TimeInForce.DAY,
        )
        order = _get_trading_client().submit_order(req)
        log_order(symbol, "BUY", qty, str(order.status))
        return order
    except Exception as e:
        log_error(f"place_buy_order({symbol}, {qty}) hatasi: {e}")
        return None


def place_sell_order(symbol, qty):
    """Market order SELL gonder."""
    try:
        req = MarketOrderRequest(
            symbol=symbol,
            qty=qty,
            side=OrderSide.SELL,
            time_in_force=TimeInForce.DAY,
        )
        order = _get_trading_client().submit_order(req)
        log_order(symbol, "SELL", qty, str(order.status))
        return order
    except Exception as e:
        log_error(f"place_sell_order({symbol}, {qty}) hatasi: {e}")
        return None


def get_latest_price(symbol):
    """Guncel fiyati dondurur."""
    try:
        req    = StockLatestTradeRequest(symbol_or_symbols=symbol)
        trades = _get_data_client().get_stock_latest_trade(req)
        return float(trades[symbol].price)
    except Exception as e:
        log_error(f"get_latest_price({symbol}) hatasi: {e}")
        return None


def is_market_open():
    """Market acik mi?"""
    try:
        clock = _get_trading_client().get_clock()
        return clock.is_open
    except Exception as e:
        log_error(f"is_market_open hatasi: {e}")
        return False


# ---------------------------------------------------------------------------
# Dogrudan calistirilirsa test et
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    print("=== broker.py baglanti testi ===\n")

    account = connect()
    if account is None:
        print("BAGLANTI BASARISIZ -- .env dosyasini kontrol et.")
    else:
        info = get_account()
        print(f"  Equity       : ${info['equity']:,.2f}")
        print(f"  Buying power : ${info['buying_power']:,.2f}")
        print(f"  Durum        : {info['status']}")
        print(f"  Market acik  : {is_market_open()}")

        pos = get_position("AAPL")
        if pos:
            print(f"  AAPL pozisyon: {pos.qty} adet")
        else:
            print("  AAPL pozisyon: yok")

        price = get_latest_price("AAPL")
        if price:
            print(f"  AAPL son fiyat: ${price:,.2f}")

    print("\n=== Test tamamlandi ===")
