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
