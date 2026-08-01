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
