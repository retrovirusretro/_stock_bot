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
    capital               : Baslangic sermayesi (TL veya USD)
    max_position_pct      : Tek islem icin max sermaye orani  (varsayilan: %5)
    stop_loss_pct         : Stop-loss orani                   (varsayilan: %3)
    take_profit_pct       : Take-profit orani                 (varsayilan: %6)
    daily_loss_limit      : Gunluk max kayip orani            (varsayilan: %2)
    weekly_loss_limit     : Haftalik max kayip orani          (varsayilan: %5)
    max_open_positions    : Ayni anda max acik pozisyon sayisi (varsayilan: 3)
    max_drawdown_pct      : Max izin verilen drawdown orani   (varsayilan: %10)
    consecutive_loss_limit: Ust uste kayip gun limiti         (varsayilan: 3)
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
        max_drawdown_pct=0.10,
        consecutive_loss_limit=3,
    ):
        self.capital = float(capital)
        self.max_position_pct = float(max_position_pct)
        self.stop_loss_pct = float(stop_loss_pct)
        self.take_profit_pct = float(take_profit_pct)
        self.daily_loss_limit = float(daily_loss_limit)
        self.weekly_loss_limit = float(weekly_loss_limit)
        self.max_open_positions = int(max_open_positions)
        self.max_drawdown_pct = float(max_drawdown_pct)
        self.consecutive_loss_limit = int(consecutive_loss_limit)

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

    def position_notional_value(self):
        """
        Pozisyon icin harcanacak maksimum dolar tutari.
        Kucuk sermayede (capital < 1000) fractional share icin kullanilir.
        Formul: capital * max_position_pct
        Ornek: capital=50, max_position_pct=0.20 -> $10 notional
        """
        return round(self.capital * self.max_position_pct, 2)

    def use_notional(self, price):
        """
        Notional order kullanilmali mi?
        Tam hisse alinabiliyorsa False (standart qty), alinmiyorsa True.
        """
        return self.position_size(price) == 0

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

    def atr_stop_loss_price(self, entry_price, atr, multiplier=2.0):
        """
        ATR tabanli dinamik stop-loss.
        Volatileye gore stop mesafesi degisir.
        Formul: entry - (atr * multiplier)
        Sakin piyasada dar stop, volatil piyasada genis stop.
        """
        if atr <= 0:
            return self.stop_loss_price(entry_price)  # fallback: sabit %3
        stop = entry_price - (atr * multiplier)
        return round(max(stop, 0), 4)

    def atr_take_profit_price(self, entry_price, atr, multiplier=4.0):
        """
        ATR tabanli dinamik take-profit.
        Risk/Odul orani: 1:2 (stop 2xATR, TP 4xATR)
        """
        if atr <= 0:
            return self.take_profit_price(entry_price)  # fallback: sabit %6
        return round(entry_price + (atr * multiplier), 4)

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

    def check_drawdown(self, current_equity, peak_equity):
        """
        Maksimum drawdown limitine ulasildi mi?

        current_equity : Anlik hesap equity degeri.
        peak_equity    : Bot basindan beri gorulmus en yuksek equity.

        Returns True eger drawdown >= max_drawdown_pct (islem durdur).
        """
        if peak_equity <= 0:
            return False
        drawdown = (peak_equity - current_equity) / peak_equity
        return drawdown >= self.max_drawdown_pct

    def drawdown_pct(self, current_equity, peak_equity):
        """Anlık drawdown oranini (0-1) dondurur."""
        if peak_equity <= 0:
            return 0.0
        return max(0.0, (peak_equity - current_equity) / peak_equity)

    def kelly_position_size(self, price, win_rate, avg_win_pct, avg_loss_pct, half_kelly=True):
        """
        Kelly Criterion pozisyon boyutu.

        Formul: f* = (p*b - q) / b
            p = win_rate (kazanma olasiligi)
            q = 1 - p   (kaybetme olasiligi)
            b = avg_win_pct / avg_loss_pct  (kazanc/kayip orani)

        half_kelly=True: f*'i 0.5 ile carp (daha muhafazakar, overfit'e karsi)
        Sonuc max_position_pct ile kirpilir.

        En az 10 gun verisi olmadan cagirmamali (reporter.py kontrol eder).
        """
        if price <= 0 or avg_loss_pct <= 0:
            return self.position_size(price)   # veri yoksa standart boyut

        b = avg_win_pct / avg_loss_pct
        q = 1.0 - win_rate
        f = (win_rate * b - q) / b

        if half_kelly:
            f *= 0.5

        # 0 ile max_position_pct arasinda kirp
        f = max(0.0, min(f, self.max_position_pct))

        qty = int(self.capital * f / price)
        return max(0, qty)

    def check_consecutive_losses(self, loss_streak):
        """
        Ust uste kayip gun limiti asildi mi?

        loss_streak: Kac gun arka arkaya kayip yasandi (int).
        Returns True eger loss_streak >= consecutive_loss_limit (islem durdur).
        """
        return loss_streak >= self.consecutive_loss_limit

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
            "max_drawdown_pct": self.max_drawdown_pct,
            "consecutive_loss_limit": self.consecutive_loss_limit,
            "max_position_value": round(self.capital * self.max_position_pct, 2),
            "daily_loss_threshold": round(self.capital * self.daily_loss_limit, 2),
            "weekly_loss_threshold": round(self.capital * self.weekly_loss_limit, 2),
        }
