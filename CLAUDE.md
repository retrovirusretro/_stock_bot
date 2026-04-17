# Trading Bot — Claude Code Proje Kılavuzu

Bu dosya Claude Code'un projeyi ilk açtığında okuyacağı ana referanstır.
Her oturumda bu dosyayı oku, sonra `plans/` klasörüne bak.

---

## Proje Özeti

7/24 çalışan, kural tabanlı otomatik al-sat botu.
- **Platform:** Railway (deploy), Alpaca (broker), yfinance (veri)
- **Durum:** Paper trading aktif, live geçiş hazır ($50)
- **Hedef:** Ticari SaaS ürünü (bkz. plans/trading-saas-roadmap.md)

---

## Kritik Dosyalar

```
paper_trader.py   → Ana döngü. Buradan başla.
risk.py           → RiskManager: tüm risk parametreleri burada
strategy.py       → 3 strateji: filtered_signals, supertrend_signals, rsi_bounce_signals
broker.py         → Alpaca API. POSITION_UNKNOWN sentinel kritik — değiştirme.
reporter.py       → PnL + Sharpe/Kelly istatistikleri
sentiment.py      → Alpha Vantage haber filtresi
screener.py       → S&P500 503 sembol tarayıcı
dashboard.py      → Flask web arayüzü (port 5000)
data.py           → yfinance + tüm indikatörler
templates/index.html → Dashboard HTML/JS (tek dosya, büyük)
```

---

## Strateji Mimarisi

```
CRISIS_ASSETS  = {GLD, SLV, USO}        → SMA crossover, SMA200 filtresi YOK
MINING_ASSETS  = {GDX, GDXJ}            → SMA crossover + SMA200 filtresi
SUPERTREND_ASSETS = {XME, COPX, XLE,    → Supertrend (direction flip)
                     XLB, XLI, QQQ,
                     DIA, IWM, AAPL, MSFT}
```

SMA grubu için ayrıca **RSI Bounce** (rsi_low=35, rsi_high=50) ek katman.
Her BUY'dan önce **Sentiment filtresi** çalışır (skor < -0.25 → engel).
10+ gün veri varsa **Kelly Criterion** pozisyon boyutu devreye girer.

---

## Risk Parametreleri (Şu An: $50 Live)

```python
RiskManager(
    capital            = 50,
    max_position_pct   = 0.20,   # $10/pozisyon — notional order
    stop_loss_pct      = 0.03,
    take_profit_pct    = 0.06,
    daily_loss_limit   = 0.05,   # $2.50
    max_open_positions = 3,
    max_drawdown_pct   = 0.15,   # %15 → BUY halt
    consecutive_loss_limit = 3,  # 3 gün üst üste → BUY halt
)
```

**Önemli:** `capital=50` olduğu için tüm semboller notional order kullanır.
`risk.use_notional(price)` True döner → `broker.place_buy_order_notional()` çağrılır.

---

## Deployment

- **Railway:** `worker: python paper_trader.py` (Procfile)
- **Dashboard:** `python dashboard.py` → localhost:5000
- **Tek iterasyon:** `python paper_trader.py --once`

### Railway Environment Variables
```
ALPACA_API_KEY
ALPACA_SECRET_KEY
ALPACA_BASE_URL       (paper: https://paper-api.alpaca.markets)
ALPHAVANTAGE_API_KEY
```

---

## .env Yapısı

```
ALPACA_API_KEY=<paper veya live key>
ALPACA_SECRET_KEY=<secret>
ALPACA_BASE_URL=https://paper-api.alpaca.markets
ALPHAVANTAGE_API_KEY=<alpha vantage key>
```

Paper → Live geçiş: sadece ALPACA_* değerlerini değiştir.

---

## Önemli Kurallar (Değiştirme)

1. `broker.POSITION_UNKNOWN` sentinel'ı — `None` ile karıştırma, duplicate order olur
2. Drawdown haltında SELL sinyallerine izin ver, sadece BUY'ı blokla
3. `capital=50` ile qty bazlı order kullanma — notional order şart
4. `.env` dosyasını asla git'e commit etme
5. `logs/` klasörü Railway'de ephemeral — deploy'da sıfırlanır (ileride Supabase'e taşınacak)

---

## Sıradaki Görevler

**Kısa vade (paper gözlem süresinde):**
- Telegram bildirimleri (BUY/SELL anında telefona mesaj)
- Trailing stop — SMA grubu için (USO gibi geç SELL sorununu çözer)

**Orta vade (SaaS):**
- Supabase entegrasyonu (multi-tenant)
- Stripe ödeme (amazenlen.com'dan deneyim var)
- Landing page

Detay: `plans/trading-saas-roadmap.md`

---

## GitHub

```
https://github.com/retrovirusretro/_stock_bot
branch: main
```

---

## Log Dosyaları (Railway'de ephemeral)

```
logs/trading.log          → tüm işlem logları
logs/pnl_snapshots.json   → günlük PnL (deploy'da sıfırlanır)
logs/screener_cache.json  → S&P500 tarama sonucu (60dk cache)
logs/sp500_symbols.json   → sembol listesi (24s cache)
logs/sentiment_cache.json → sentiment skorları (4s cache)
```
