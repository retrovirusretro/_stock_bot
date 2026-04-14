# -*- coding: utf-8 -*-
"""
risk.py - Risk yonetim modulu
ASCII-only, Windows cp1254 uyumlu.
"""


class RiskManager:
    """
    Basit kural tabanli risk yoneticisi.

    Parametreler
    ------------
    capital            : Baslangic sermayesi (TL veya USD)
    max_position_pct   : Tek islem icin max sermaye orani  (varsayilan: %5)
    stop_loss_pct      : Stop-loss orani                   (varsayilan: %3)
    take_profit_pct    : Take-profit orani                 (varsayilan: %6)
    daily_loss_limit   : Gunluk max kayip orani            (varsayilan: %2)
    weekly_loss_limit  : Haftalik max kayip orani          (varsayilan: %5)
    max_open_positions : Ayni anda max acik pozisyon sayisi (varsayilan: 3)
    """

    def __init__(
        self,
        capital,
        max_position_pct=0.05,
        stop_loss_pct=0.03,
        take_profit_pct=0.06,
        daily_loss_limit=0.02,
        weekly_loss_limit=0.05,
        max_open_positions=3,
    ):
        self.capital = float(capital)
        self.max_position_pct = float(max_position_pct)
        self.stop_loss_pct = float(stop_loss_pct)
        self.take_profit_pct = float(take_profit_pct)
        self.daily_loss_limit = float(daily_loss_limit)
        self.weekly_loss_limit = float(weekly_loss_limit)
        self.max_open_positions = int(max_open_positions)

    # ------------------------------------------------------------------
    # Pozisyon boyutu
    # ------------------------------------------------------------------

    def position_size(self, price):
        """
        Kac adet alabilirim?
        Formul: floor(capital * max_position_pct / price)
        Minimum 0 doner (fiyat cok yuksekse sifir adet).
        """
        if price <= 0:
            return 0
        qty = int(self.capital * self.max_position_pct / price)
        return max(0, qty)

    def atr_position_size(self, price, atr, risk_per_trade=0.01):
        """
        ATR tabanli pozisyon boyutu.
        Formul: floor((capital * risk_per_trade) / (atr * 2))
        price parametresi gelecekte fiyat filtresi icin tutulur.
        """
        if atr <= 0:
            return 0
        qty = int((self.capital * risk_per_trade) / (atr * 2))
        return max(0, qty)

    # ------------------------------------------------------------------
    # Fiyat seviyeleri
    # ------------------------------------------------------------------

    def stop_loss_price(self, entry_price):
        """Stop-loss fiyati: entry * (1 - stop_loss_pct)"""
        return round(entry_price * (1.0 - self.stop_loss_pct), 4)

    def take_profit_price(self, entry_price):
        """Take-profit fiyati: entry * (1 + take_profit_pct)"""
        return round(entry_price * (1.0 + self.take_profit_pct), 4)

    # ------------------------------------------------------------------
    # Sinir kontrolleri
    # ------------------------------------------------------------------

    def should_stop_trading(self, daily_loss):
        """
        Gunluk islem durdurulmali mi?
        daily_loss: gunde gerceklesen kayip miktari (pozitif sayi).
        Kayip, sermayenin daily_loss_limit oranini gecmisse True doner.
        """
        limit = self.capital * self.daily_loss_limit
        return daily_loss >= limit

    def can_open_position(self, open_positions_count):
        """
        Yeni pozisyon acilabilir mi?
        Mevcut acik pozisyon sayisi max_open_positions'dan azsa True doner.
        """
        return open_positions_count < self.max_open_positions

    # ------------------------------------------------------------------
    # Ozet
    # ------------------------------------------------------------------

    def summary(self):
        """Tum parametreleri dict olarak dondur."""
        return {
            "capital": self.capital,
            "max_position_pct": self.max_position_pct,
            "stop_loss_pct": self.stop_loss_pct,
            "take_profit_pct": self.take_profit_pct,
            "daily_loss_limit": self.daily_loss_limit,
            "weekly_loss_limit": self.weekly_loss_limit,
            "max_open_positions": self.max_open_positions,
            "max_position_value": round(self.capital * self.max_position_pct, 2),
            "daily_loss_threshold": round(self.capital * self.daily_loss_limit, 2),
            "weekly_loss_threshold": round(self.capital * self.weekly_loss_limit, 2),
        }
