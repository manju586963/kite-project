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

## Crude Oil contract selector

Automatically picks the active **MCX Crude Oil futures** contract from the live Kite instrument master using a **5-calendar-day** pre-expiry rollover rule (never trades an expired contract; never hard-codes month symbols).

```bash
python crude_oil_selector.py
python crude_oil_selector.py --list
python crude_oil_selector.py --as-of 2026-08-15 --json
```

Import in other modules:

```python
from crude_oil_selector import get_active_crude_oil_contract

contract = get_active_crude_oil_contract()
print(contract.tradingsymbol, contract.instrument_token, contract.expiry)
```

Unit tests (no network):

```bash
python -m unittest tests.test_crude_oil_selector -v
```
