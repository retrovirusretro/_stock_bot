# -*- coding: utf-8 -*-
"""
test_risk.py - risk.py modulu icin birim testler
Edge case'ler dahil tum RiskManager metodlari test edilir.
"""

import sys
import os
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from risk import RiskManager


# ---------------------------------------------------------------------------
# Fixture
# ---------------------------------------------------------------------------

@pytest.fixture
def rm():
    """Standart $100,000 sermayeli RiskManager."""
    return RiskManager(capital=100_000)


@pytest.fixture
def rm_small():
    """Kucuk sermayeli RiskManager ($1,000)."""
    return RiskManager(capital=1_000)


# ---------------------------------------------------------------------------
# Baslangic parametreleri
# ---------------------------------------------------------------------------

class TestInit:

    def test_default_capital(self, rm):
        assert rm.capital == 100_000.0

    def test_default_max_position_pct(self, rm):
        assert rm.max_position_pct == 0.05

    def test_default_stop_loss_pct(self, rm):
        assert rm.stop_loss_pct == 0.03

    def test_default_take_profit_pct(self, rm):
        assert rm.take_profit_pct == 0.06

    def test_default_daily_loss_limit(self, rm):
        assert rm.daily_loss_limit == 0.02

    def test_default_max_open_positions(self, rm):
        assert rm.max_open_positions == 3

    def test_custom_parameters(self):
        rm = RiskManager(capital=50_000, max_position_pct=0.10, stop_loss_pct=0.05)
        assert rm.capital == 50_000.0
        assert rm.max_position_pct == 0.10
        assert rm.stop_loss_pct == 0.05


# ---------------------------------------------------------------------------
# position_size
# ---------------------------------------------------------------------------

class TestPositionSize:

    def test_aapl_example(self, rm):
        """$100k sermaye, %5 max, $259 fiyat -> 19 adet"""
        qty = rm.position_size(259)
        assert qty == 19

    def test_zero_price_returns_zero(self, rm):
        """Sifir fiyat -> 0 adet donmeli."""
        assert rm.position_size(0) == 0

    def test_negative_price_returns_zero(self, rm):
        """Negatif fiyat -> 0 adet donmeli."""
        assert rm.position_size(-100) == 0

    def test_very_high_price_can_return_zero(self, rm_small):
        """Cok yuksek fiyatta ($10,000) kucuk sermaye -> 0 adet."""
        qty = rm_small.position_size(10_000)
        assert qty == 0

    def test_returns_integer(self, rm):
        qty = rm.position_size(100)
        assert isinstance(qty, int)

    def test_floor_division(self, rm):
        """$100k * %5 / $150 = 33.33 -> 33 adet (tam kat)."""
        qty = rm.position_size(150)
        assert qty == 33

    def test_small_capital_small_price(self, rm_small):
        """$1,000 * %5 / $10 = 5 adet."""
        qty = rm_small.position_size(10)
        assert qty == 5


# ---------------------------------------------------------------------------
# atr_position_size
# ---------------------------------------------------------------------------

class TestAtrPositionSize:

    def test_basic_atr_calc(self, rm):
        """$100k * %1 / ($5 ATR * 2) = 100 adet."""
        qty = rm.atr_position_size(price=100, atr=5.0)
        assert qty == 100

    def test_zero_atr_returns_zero(self, rm):
        assert rm.atr_position_size(price=100, atr=0) == 0

    def test_negative_atr_returns_zero(self, rm):
        assert rm.atr_position_size(price=100, atr=-1) == 0

    def test_returns_integer(self, rm):
        assert isinstance(rm.atr_position_size(100, 5.0), int)


# ---------------------------------------------------------------------------
# stop_loss_price / take_profit_price
# ---------------------------------------------------------------------------

class TestPriceLevels:

    def test_stop_loss_aapl(self, rm):
        """$259 * (1 - 0.03) = $251.23"""
        sl = rm.stop_loss_price(259.0)
        assert abs(sl - 251.23) < 0.01

    def test_take_profit_aapl(self, rm):
        """$259 * (1 + 0.06) = $274.54"""
        tp = rm.take_profit_price(259.0)
        assert abs(tp - 274.54) < 0.01

    def test_stop_below_entry(self, rm):
        """Stop daima giris fiyatinin altinda olmali."""
        entry = 100.0
        assert rm.stop_loss_price(entry) < entry

    def test_take_profit_above_entry(self, rm):
        """Take-profit daima giris fiyatinin ustunde olmali."""
        entry = 100.0
        assert rm.take_profit_price(entry) > entry

    def test_stop_loss_custom_pct(self):
        rm = RiskManager(capital=10_000, stop_loss_pct=0.05)
        sl = rm.stop_loss_price(100.0)
        assert abs(sl - 95.0) < 0.01

    def test_take_profit_custom_pct(self):
        rm = RiskManager(capital=10_000, take_profit_pct=0.10)
        tp = rm.take_profit_price(100.0)
        assert abs(tp - 110.0) < 0.01


# ---------------------------------------------------------------------------
# should_stop_trading
# ---------------------------------------------------------------------------

class TestShouldStopTrading:

    def test_below_limit_false(self, rm):
        """Kayip limitin altindaysa False donmeli."""
        # %2 limit = $2,000. $1,999 kayip -> False
        assert rm.should_stop_trading(1_999) is False

    def test_at_limit_true(self, rm):
        """Tam esitteyse True donmeli."""
        assert rm.should_stop_trading(2_000) is True

    def test_above_limit_true(self, rm):
        """Limitin ustundeyse True donmeli."""
        assert rm.should_stop_trading(3_000) is True

    def test_zero_loss_false(self, rm):
        """Kayip yoksa False donmeli."""
        assert rm.should_stop_trading(0) is False

    def test_custom_limit(self):
        rm = RiskManager(capital=10_000, daily_loss_limit=0.01)
        assert rm.should_stop_trading(100) is True
        assert rm.should_stop_trading(99) is False


# ---------------------------------------------------------------------------
# can_open_position
# ---------------------------------------------------------------------------

class TestCanOpenPosition:

    def test_zero_open_positions(self, rm):
        """Hic pozisyon yoksa True."""
        assert rm.can_open_position(0) is True

    def test_below_max(self, rm):
        """2 < 3 -> True."""
        assert rm.can_open_position(2) is True

    def test_at_max_false(self, rm):
        """3 >= 3 -> False."""
        assert rm.can_open_position(3) is False

    def test_above_max_false(self, rm):
        """5 >= 3 -> False."""
        assert rm.can_open_position(5) is False

    def test_custom_max(self):
        rm = RiskManager(capital=10_000, max_open_positions=1)
        assert rm.can_open_position(0) is True
        assert rm.can_open_position(1) is False


# ---------------------------------------------------------------------------
# atr_stop_loss_price / atr_take_profit_price
# ---------------------------------------------------------------------------

class TestAtrPriceLevels:

    def test_atr_stop_below_entry(self, rm):
        """ATR stop daima giris altinda olmali."""
        sl = rm.atr_stop_loss_price(100.0, atr=2.0, multiplier=2.0)
        assert sl < 100.0

    def test_atr_stop_value(self, rm):
        """$100 - (2.0 * 2) = $96"""
        sl = rm.atr_stop_loss_price(100.0, atr=2.0, multiplier=2.0)
        assert abs(sl - 96.0) < 0.01

    def test_atr_tp_above_entry(self, rm):
        """ATR TP daima giris ustunde olmali."""
        tp = rm.atr_take_profit_price(100.0, atr=2.0, multiplier=4.0)
        assert tp > 100.0

    def test_atr_tp_value(self, rm):
        """$100 + (2.0 * 4) = $108"""
        tp = rm.atr_take_profit_price(100.0, atr=2.0, multiplier=4.0)
        assert abs(tp - 108.0) < 0.01

    def test_zero_atr_fallback_stop(self, rm):
        """ATR=0 ise sabit %3 stop'a dusmeli."""
        sl_atr   = rm.atr_stop_loss_price(100.0, atr=0)
        sl_fixed = rm.stop_loss_price(100.0)
        assert abs(sl_atr - sl_fixed) < 0.01

    def test_zero_atr_fallback_tp(self, rm):
        """ATR=0 ise sabit %6 TP'ye dusmeli."""
        tp_atr   = rm.atr_take_profit_price(100.0, atr=0)
        tp_fixed = rm.take_profit_price(100.0)
        assert abs(tp_atr - tp_fixed) < 0.01

    def test_risk_reward_ratio(self, rm):
        """Risk/odul orani 1:2 olmali (2xATR stop, 4xATR TP)."""
        entry = 100.0
        atr   = 3.0
        sl = rm.atr_stop_loss_price(entry, atr, multiplier=2.0)
        tp = rm.atr_take_profit_price(entry, atr, multiplier=4.0)
        risk   = entry - sl
        reward = tp - entry
        assert abs(reward / risk - 2.0) < 0.01

# ---------------------------------------------------------------------------
# summary
# ---------------------------------------------------------------------------

class TestSummary:

    def test_summary_keys(self, rm):
        s = rm.summary()
        expected_keys = [
            "capital", "max_position_pct", "stop_loss_pct",
            "take_profit_pct", "daily_loss_limit", "weekly_loss_limit",
            "max_open_positions", "max_position_value",
            "daily_loss_threshold", "weekly_loss_threshold",
        ]
        for k in expected_keys:
            assert k in s, f"'{k}' anahtari summary'de yok"

    def test_max_position_value(self, rm):
        """$100k * %5 = $5,000"""
        assert rm.summary()["max_position_value"] == 5_000.0

    def test_daily_loss_threshold(self, rm):
        """$100k * %2 = $2,000"""
        assert rm.summary()["daily_loss_threshold"] == 2_000.0
