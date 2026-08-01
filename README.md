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

After a successful login, `.kite_session.json` contains the `access_token` (valid until ~06:00 IST the next trading day). Re-run the script each trading day to refresh it.
