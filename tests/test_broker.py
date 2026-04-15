# -*- coding: utf-8 -*-
"""
test_broker.py - broker.py modulu icin birim testler
Gercek API cagrilmaz; unittest.mock ile sahte nesneler kullanilir.
"""

import sys
import os
import pytest
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# ---------------------------------------------------------------------------
# Mock kurulumu
# ---------------------------------------------------------------------------

def _make_mock_account(equity=100_000, buying_power=95_000, status="ACTIVE"):
    acc = MagicMock()
    acc.equity       = equity
    acc.buying_power = buying_power
    acc.status       = status
    return acc


def _make_mock_position(symbol="AAPL", qty=10):
    pos = MagicMock()
    pos.symbol = symbol
    pos.qty    = qty
    return pos


def _make_mock_order(status="accepted"):
    order = MagicMock()
    order.status = status
    return order


def _make_mock_trade(price=185.0):
    trade = MagicMock()
    trade.price = price
    return trade


def _make_mock_clock(is_open=True):
    clock = MagicMock()
    clock.is_open = is_open
    return clock


# ---------------------------------------------------------------------------
# get_account
# ---------------------------------------------------------------------------

class TestGetAccount:

    @patch("broker._get_trading_client")
    def test_returns_dict(self, mock_client_fn):
        mock_client_fn.return_value.get_account.return_value = _make_mock_account()
        import broker
        result = broker.get_account()
        assert isinstance(result, dict)

    @patch("broker._get_trading_client")
    def test_equity_value(self, mock_client_fn):
        mock_client_fn.return_value.get_account.return_value = _make_mock_account(equity=123_456)
        import broker
        result = broker.get_account()
        assert result["equity"] == 123_456.0

    @patch("broker._get_trading_client")
    def test_buying_power_value(self, mock_client_fn):
        mock_client_fn.return_value.get_account.return_value = _make_mock_account(buying_power=80_000)
        import broker
        result = broker.get_account()
        assert result["buying_power"] == 80_000.0

    @patch("broker._get_trading_client")
    def test_returns_none_on_exception(self, mock_client_fn):
        mock_client_fn.return_value.get_account.side_effect = Exception("API down")
        import broker
        result = broker.get_account()
        assert result is None


# ---------------------------------------------------------------------------
# get_position
# ---------------------------------------------------------------------------

class TestGetPosition:

    @patch("broker._get_trading_client")
    def test_returns_position_when_exists(self, mock_client_fn):
        pos = _make_mock_position("AAPL", 10)
        mock_client_fn.return_value.get_open_position.return_value = pos
        import broker
        result = broker.get_position("AAPL")
        assert result is not None
        assert result.qty == 10

    @patch("broker._get_trading_client")
    def test_returns_none_when_not_found(self, mock_client_fn):
        mock_client_fn.return_value.get_open_position.side_effect = Exception("position does not exist")
        import broker
        result = broker.get_position("AAPL")
        assert result is None

    @patch("broker._get_trading_client")
    def test_returns_none_on_404(self, mock_client_fn):
        mock_client_fn.return_value.get_open_position.side_effect = Exception("404 not found")
        import broker
        result = broker.get_position("MSFT")
        assert result is None


# ---------------------------------------------------------------------------
# place_buy_order
# ---------------------------------------------------------------------------

class TestPlaceBuyOrder:

    @patch("broker._get_trading_client")
    def test_returns_order_on_success(self, mock_client_fn):
        order = _make_mock_order("accepted")
        mock_client_fn.return_value.submit_order.return_value = order
        import broker
        result = broker.place_buy_order("AAPL", 5)
        assert result is not None

    @patch("broker._get_trading_client")
    def test_order_submitted_with_correct_qty(self, mock_client_fn):
        order = _make_mock_order()
        mock_client_fn.return_value.submit_order.return_value = order
        import broker
        broker.place_buy_order("AAPL", 7)
        call_args = mock_client_fn.return_value.submit_order.call_args
        req = call_args[0][0]
        assert req.qty == 7

    @patch("broker._get_trading_client")
    def test_returns_none_on_exception(self, mock_client_fn):
        mock_client_fn.return_value.submit_order.side_effect = Exception("insufficient funds")
        import broker
        result = broker.place_buy_order("AAPL", 999)
        assert result is None


# ---------------------------------------------------------------------------
# place_sell_order
# ---------------------------------------------------------------------------

class TestPlaceSellOrder:

    @patch("broker._get_trading_client")
    def test_returns_order_on_success(self, mock_client_fn):
        order = _make_mock_order("accepted")
        mock_client_fn.return_value.submit_order.return_value = order
        import broker
        result = broker.place_sell_order("GLD", 3)
        assert result is not None

    @patch("broker._get_trading_client")
    def test_returns_none_on_exception(self, mock_client_fn):
        mock_client_fn.return_value.submit_order.side_effect = Exception("no position")
        import broker
        result = broker.place_sell_order("GLD", 3)
        assert result is None


# ---------------------------------------------------------------------------
# get_latest_price
# ---------------------------------------------------------------------------

class TestGetLatestPrice:

    @patch("broker._get_data_client")
    def test_returns_price(self, mock_client_fn):
        trade = _make_mock_trade(price=185.50)
        mock_client_fn.return_value.get_stock_latest_trade.return_value = {"AAPL": trade}
        import broker
        price = broker.get_latest_price("AAPL")
        assert abs(price - 185.50) < 0.01

    @patch("broker._get_data_client")
    def test_returns_none_on_exception(self, mock_client_fn):
        mock_client_fn.return_value.get_stock_latest_trade.side_effect = Exception("timeout")
        import broker
        price = broker.get_latest_price("AAPL")
        assert price is None


# ---------------------------------------------------------------------------
# is_market_open
# ---------------------------------------------------------------------------

class TestIsMarketOpen:

    @patch("broker._get_trading_client")
    def test_market_open(self, mock_client_fn):
        mock_client_fn.return_value.get_clock.return_value = _make_mock_clock(is_open=True)
        import broker
        assert broker.is_market_open() is True

    @patch("broker._get_trading_client")
    def test_market_closed(self, mock_client_fn):
        mock_client_fn.return_value.get_clock.return_value = _make_mock_clock(is_open=False)
        import broker
        assert broker.is_market_open() is False

    @patch("broker._get_trading_client")
    def test_returns_false_on_exception(self, mock_client_fn):
        mock_client_fn.return_value.get_clock.side_effect = Exception("network error")
        import broker
        assert broker.is_market_open() is False
