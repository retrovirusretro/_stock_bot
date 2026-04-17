# -*- coding: utf-8 -*-
"""
reporter.py - Gunluk P&L takip modulu

Her trading iterasyonunda cagrilir:
  - Gun basinda equity'yi 'start' olarak kaydeder
  - Gun boyunca 'end' degerini gunceller
  - Log'a ozet yazar

Veri dosyasi: logs/pnl_snapshots.json
Format: {"2026-04-17": {"start": 100000, "end": 100150, "positions": ["USO"]}}
"""

import json
import math
import os
from datetime import date
from logger import log_info, log_error

# ---------------------------------------------------------------------------
# Sabitler
# ---------------------------------------------------------------------------

_BASE_DIR      = os.path.dirname(os.path.abspath(__file__))
SNAPSHOT_FILE  = os.path.join(_BASE_DIR, "logs", "pnl_snapshots.json")

# Log'u her iterasyonda degil, equity degisince yaz (kuculuk: 1 cent)
_LOG_THRESHOLD = 0.01


# ---------------------------------------------------------------------------
# Yardimci: dosya okuma / yazma
# ---------------------------------------------------------------------------

def _load():
    if os.path.exists(SNAPSHOT_FILE):
        try:
            with open(SNAPSHOT_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}


def _save(data):
    os.makedirs(os.path.dirname(SNAPSHOT_FILE), exist_ok=True)
    with open(SNAPSHOT_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


# ---------------------------------------------------------------------------
# Ana fonksiyon: her iterasyonda cagrilir
# ---------------------------------------------------------------------------

def update(equity, positions=None):
    """
    Gunluk equity snapshot'ini gunceller ve log'a ozet yazar.

    Args:
        equity:    Anlık hesap equity degeri (float)
        positions: Acik pozisyon sembolleri listesi (orn: ["USO", "QQQ"])
    """
    today     = date.today().isoformat()
    equity    = round(float(equity), 2)
    positions = positions or []
    data      = _load()

    if today not in data:
        # Gun baslangici: start ve end ikisi de bugunun ilk equity degeri
        data[today] = {
            "start":     equity,
            "end":       equity,
            "positions": positions,
        }
        _save(data)
        log_info(
            f"[PNL] Yeni gun: {today} | "
            f"Baslangic equity: ${equity:,.2f} | "
            f"Pozisyonlar: {positions}"
        )
        return

    # Gun icinde guncelleme
    prev_end = data[today].get("end", data[today]["start"])
    start    = data[today]["start"]

    data[today]["end"]       = equity
    data[today]["positions"] = positions
    _save(data)

    # Degisim buyukse log'a yaz
    if abs(equity - prev_end) >= _LOG_THRESHOLD:
        change   = equity - start
        pct      = (change / start * 100) if start > 0 else 0.0
        sign     = "+" if change >= 0 else ""
        log_info(
            f"[PNL] {today} | "
            f"Baslangic: ${start:,.2f} | "
            f"Guncel: ${equity:,.2f} | "
            f"Degisim: {sign}${change:,.2f} ({sign}{pct:.2f}%) | "
            f"Pozisyonlar: {positions}"
        )


# ---------------------------------------------------------------------------
# Gecmis verisi: dashboard ve sorgular icin
# ---------------------------------------------------------------------------

def get_history(last_n=30):
    """
    Son N gunun PnL gecmisini dondurur (en yeniden en eskiye).

    Returns:
        list of dict: date, start, end, change, pct, positions
    """
    data   = _load()
    result = []

    for day in sorted(data.keys(), reverse=True)[:last_n]:
        entry  = data[day]
        start  = entry.get("start", 0.0)
        end    = entry.get("end", start)
        change = round(end - start, 2)
        pct    = round((change / start * 100) if start > 0 else 0.0, 2)
        result.append({
            "date":      day,
            "start":     round(start, 2),
            "end":       round(end,   2),
            "change":    change,
            "pct":       pct,
            "positions": entry.get("positions", []),
        })

    return result


def get_today():
    """Bugunun PnL ozetini dondurur (yoksa None)."""
    today = date.today().isoformat()
    data  = _load()
    if today not in data:
        return None
    entry  = data[today]
    start  = entry.get("start", 0.0)
    end    = entry.get("end", start)
    change = round(end - start, 2)
    pct    = round((change / start * 100) if start > 0 else 0.0, 2)
    return {
        "date":      today,
        "start":     round(start, 2),
        "end":       round(end,   2),
        "change":    change,
        "pct":       pct,
        "positions": entry.get("positions", []),
    }


# ---------------------------------------------------------------------------
# Performans istatistikleri
# ---------------------------------------------------------------------------

def get_performance_stats():
    """
    Tum PnL gecmisinden performans istatistiklerini hesaplar.

    Returns dict:
        sharpe_ratio    : Annualized Sharpe ratio (sqrt(252) * mean/std of daily returns)
        max_drawdown    : En buyuk tepe-cukur dusus orani (0-1)
        win_rate        : Kazancli gun orani (0-1)
        total_return    : Toplam getiri orani (0-1)
        total_return_usd: Toplam getiri USD
        avg_daily_pct   : Gunluk ortalama getiri (%)
        trading_days    : Veri icindeki gun sayisi
        start_equity    : Ilk kayitli equity
        current_equity  : En son kayitli equity
    """
    data = _load()
    if not data:
        return _empty_stats()

    days = sorted(data.keys())
    if len(days) < 2:
        return _empty_stats()

    equities = []
    for d in days:
        entry  = data[d]
        end_eq = entry.get("end", entry.get("start", 0.0))
        equities.append(float(end_eq))

    # Gunluk getiriler (log yerine basit oran)
    daily_returns = []
    for i in range(1, len(equities)):
        if equities[i - 1] > 0:
            r = (equities[i] - equities[i - 1]) / equities[i - 1]
            daily_returns.append(r)

    # Sharpe ratio (annualized, risk-free = 0)
    sharpe = 0.0
    if len(daily_returns) >= 2:
        mean_r = sum(daily_returns) / len(daily_returns)
        var_r  = sum((r - mean_r) ** 2 for r in daily_returns) / (len(daily_returns) - 1)
        std_r  = math.sqrt(var_r) if var_r > 0 else 0.0
        if std_r > 0:
            sharpe = round((mean_r / std_r) * math.sqrt(252), 2)

    # Max drawdown
    peak   = equities[0]
    max_dd = 0.0
    for eq in equities:
        if eq > peak:
            peak = eq
        dd = (peak - eq) / peak if peak > 0 else 0.0
        if dd > max_dd:
            max_dd = dd

    # Win rate (kazancli gunler)
    wins     = sum(1 for r in daily_returns if r > 0)
    win_rate = round(wins / len(daily_returns), 4) if daily_returns else 0.0

    # Toplam getiri
    start_eq   = equities[0]
    current_eq = equities[-1]
    total_ret  = round((current_eq - start_eq) / start_eq, 4) if start_eq > 0 else 0.0
    total_usd  = round(current_eq - start_eq, 2)

    avg_daily  = round(sum(daily_returns) / len(daily_returns) * 100, 4) if daily_returns else 0.0

    # Ortalama kazanc / kayip (Kelly icin)
    pos_returns = [r for r in daily_returns if r > 0]
    neg_returns = [r for r in daily_returns if r < 0]
    avg_win_pct  = round(sum(pos_returns) / len(pos_returns), 6) if pos_returns else 0.01
    avg_loss_pct = round(abs(sum(neg_returns) / len(neg_returns)), 6) if neg_returns else 0.01

    return {
        "sharpe_ratio":     sharpe,
        "max_drawdown":     round(max_dd, 4),
        "win_rate":         win_rate,
        "total_return":     total_ret,
        "total_return_usd": total_usd,
        "avg_daily_pct":    avg_daily,
        "trading_days":     len(days),
        "start_equity":     round(start_eq,   2),
        "current_equity":   round(current_eq, 2),
        "avg_win_pct":      avg_win_pct,
        "avg_loss_pct":     avg_loss_pct,
    }


def _empty_stats():
    return {
        "sharpe_ratio":     0.0,
        "max_drawdown":     0.0,
        "win_rate":         0.0,
        "total_return":     0.0,
        "total_return_usd": 0.0,
        "avg_daily_pct":    0.0,
        "trading_days":     0,
        "start_equity":     0.0,
        "current_equity":   0.0,
    }


# ---------------------------------------------------------------------------
# Dogrudan calistirilirsa
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print("PnL gecmisi:")
    for row in get_history(10):
        sign = "+" if row["change"] >= 0 else ""
        print(
            f"  {row['date']} | "
            f"${row['start']:,.2f} -> ${row['end']:,.2f} | "
            f"{sign}${row['change']:,.2f} ({sign}{row['pct']:.2f}%) | "
            f"{row['positions']}"
        )
