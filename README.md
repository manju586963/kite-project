# kite-project

Zerodha Kite Connect helpers.

## Login to Zerodha

Interactive login via the official [Kite Connect](https://kite.trade/docs/connect/v3/) OAuth flow. The script opens Zerodha’s login page, captures the one-time `request_token`, exchanges it for a daily `access_token`, and saves the session to `.kite_session.json`.

### Setup

1. Create an API app at [developers.kite.trade](https://developers.kite.trade/).
2. Set the app **Redirect URL** to `http://127.0.0.1:8765/callback`.
3. Install dependencies and configure credentials:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# edit .env with KITE_API_KEY and KITE_API_SECRET
```

### Run

```bash
python scripts/zerodha_login.py
```

If the local callback server cannot bind (or you prefer not to use it), paste the redirect URL manually:

```bash
python scripts/zerodha_login.py --manual
```

After a successful login, the access token is saved to `.kite_session.json` and `access_token.txt` (valid until ~06:00 IST the next trading day). Re-run the script each trading day to refresh it.

## Test connection (no orders)

After logging in, verify the session by fetching profile and margins only:

```bash
python test_connection.py
```

Expected output:

```text
Connection successful
User name: Your Name
User ID: Your ID
Broker: ZERODHA
Available margin data received: True
```

## Crude Oil contract (fixed)

The active contract is set manually in `config.py`:

```python
TRADING_SYMBOL = "CRUDEOIL26AUGFUT"
```

`crude_oil_selector.py` reads that symbol, downloads the Kite instrument list, finds the matching MCX contract, and returns its `instrument_token`. No rollover logic — when the month changes, update only `TRADING_SYMBOL`.

```bash
python crude_oil_selector.py
python crude_oil_selector.py --json
python crude_oil_selector.py --symbol CRUDEOIL26SEPFUT
```

Import in other modules:

```python
from crude_oil_selector import resolve_contract

contract = resolve_contract()
print(contract.tradingsymbol, contract.instrument_token, contract.expiry)
```

Unit tests (no network):

```bash
python -m unittest tests.test_crude_oil_selector -v
```

## Live price feed (Step 3)

Streams LTP, volume, and open interest for the fixed August 2026 MCX CRUDEOIL futures contract. Looks up `instrument_token` from Kite’s live instrument list (prefers `config.TRADING_SYMBOL`). **No orders.**

```bash
python scripts/zerodha_login.py   # once per trading day
python live_price.py              # Ctrl+C to stop
```

Expected:

```text
========================================
MCX CRUDEOIL LIVE PRICE
========================================
Contract         : CRUDEOIL26AUGFUT
Expiry           : 2026-08-...
Instrument token : ...
Lot size         : ...
Tick size        : ...
Orders           : DISABLED
========================================
Connected to Kite.
Subscribed to: CRUDEOIL26AUGFUT
... | CRUDEOIL26AUGFUT | LTP: ... | Volume: ... | OI: ...
```

## Historical Supertrend paper trading (Step 5 — Intraday Master)

Validates Supertrend **(10, 1)** on historical **15-minute Heikin Ashi** candles for `config.TRADING_SYMBOL` using an **intraday-only** model:

- Raw Kite OHLC is converted to Heikin Ashi before Supertrend
- BUY / SELL on Supertrend flips at HA candle close
- Max loss per trade: **125 points** (`MAX_LOSS_STOP`; override with `--max-loss-points`)
- No new entries after **11:00 PM**
- Compulsory square-off at **11:15 PM** (`INTRADAY_SQUARE_OFF`)
- Each day starts **FLAT** (no overnight positions)
- Default test window: last **30 trading days**
- Paper trading only — **no real orders**

```bash
python scripts/zerodha_login.py
python historical_supertrend_paper.py
python historical_supertrend_paper.py --max-loss-points 125
python historical_supertrend_paper.py --trading-days 30
```

Outputs are saved under a dated folder in the project main folder (never overwrites):

`01-aug-2026/`  (re-runs the same day become `01-aug-2026_2`, etc.)

Inside each folder, filenames are also kept unique (`supertrend_signals_2.csv`, …) so nothing is overwritten.

- `supertrend_signals.csv` — HA candles + Supertrend + BUY/SELL marks
- `paper_trades.csv` — entry/exit, points, lot P&L, square-offs
- `paper_trading_summary.txt` — totals, win rate, daily & net paper P&L
- `monthly/jun-2025.xlsx`, `monthly/jul-2025.xlsx`, … — one Excel workbook per month with sheets `signals`, `trades`, `summary`
- `consolidated_monthly_summary.xlsx` — all months in one file (`monthly_summary`, `all_trades`, `daily_pnl`)
- `consolidated_monthly_summary.txt` — printable month-by-month totals

Offline test with a local candle CSV:

```bash
python historical_supertrend_paper.py --csv-candles my_candles.csv
python -m unittest tests.test_historical_supertrend_paper -v
```
