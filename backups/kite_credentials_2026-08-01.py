"""
Load Kite Connect credentials for local scripts and cloud/CI agents.

Resolution order
----------------
API key:
  1. KITE_API_KEY environment variable (or .env)
  2. api_key field in .kite_session.json

Access token:
  1. KITE_ACCESS_TOKEN environment variable (or .env)
  2. access_token.txt
  3. access_token field in .kite_session.json

Cloud / Cursor agents cannot complete the browser OAuth login. Generate a
token on your PC with ``python scripts/zerodha_login.py``, then set
KITE_API_KEY + KITE_ACCESS_TOKEN as environment secrets (or in a local .env).
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent
ENV_FILE = ROOT / ".env"
ACCESS_TOKEN_FILE = ROOT / "access_token.txt"
SESSION_FILE = ROOT / ".kite_session.json"

_MISSING_API_KEY = (
    "KITE_API_KEY is missing.\n"
    "Set it in .env, export it in the environment, or complete login so "
    ".kite_session.json contains api_key.\n"
    "See .env.example and README (Credentials)."
)

_MISSING_ACCESS_TOKEN = (
    "Kite access token is missing.\n"
    "Options:\n"
    "  1. Local PC: python scripts/zerodha_login.py  "
    "(writes access_token.txt)\n"
    "  2. Cloud/CI: set KITE_ACCESS_TOKEN (and KITE_API_KEY) in the "
    "environment or .env after generating today's token locally.\n"
    "Tokens expire around 06:00 IST each trading day."
)


def _load_dotenv() -> None:
    load_dotenv(ENV_FILE)


def _session_dict() -> dict:
    if not SESSION_FILE.exists():
        return {}
    try:
        data = json.loads(SESSION_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def load_api_key() -> str:
    """Return Kite API key or raise RuntimeError."""
    _load_dotenv()
    api_key = os.getenv("KITE_API_KEY", "").strip()
    if api_key:
        return api_key
    api_key = (_session_dict().get("api_key") or "").strip()
    if api_key:
        return api_key
    raise RuntimeError(_MISSING_API_KEY)


def load_access_token() -> str:
    """Return daily Kite access token or raise RuntimeError."""
    _load_dotenv()
    token = os.getenv("KITE_ACCESS_TOKEN", "").strip()
    if token:
        return token
    if ACCESS_TOKEN_FILE.exists():
        token = ACCESS_TOKEN_FILE.read_text(encoding="utf-8").strip()
        if token:
            return token
    token = (_session_dict().get("access_token") or "").strip()
    if token:
        return token
    raise RuntimeError(_MISSING_ACCESS_TOKEN)


def load_api_secret() -> str:
    """Return API secret (login only). Optional for historical/live calls."""
    _load_dotenv()
    secret = os.getenv("KITE_API_SECRET", "").strip()
    if secret:
        return secret
    raise RuntimeError(
        "KITE_API_SECRET is missing from .env / the environment.\n"
        "Required only for scripts/zerodha_login.py."
    )


def credential_status() -> dict[str, bool]:
    """Non-throwing presence check (values never returned)."""
    _load_dotenv()
    session = _session_dict()
    has_key = bool(os.getenv("KITE_API_KEY", "").strip() or session.get("api_key"))
    has_token = bool(
        os.getenv("KITE_ACCESS_TOKEN", "").strip()
        or (
            ACCESS_TOKEN_FILE.exists()
            and ACCESS_TOKEN_FILE.read_text(encoding="utf-8").strip()
        )
        or session.get("access_token")
    )
    has_secret = bool(os.getenv("KITE_API_SECRET", "").strip())
    return {
        "api_key": has_key,
        "access_token": has_token,
        "api_secret": has_secret,
    }


def make_kite():
    """Build an authenticated KiteConnect client."""
    from kiteconnect import KiteConnect

    kite = KiteConnect(api_key=load_api_key())
    kite.set_access_token(load_access_token())
    return kite


if __name__ == "__main__":
    status = credential_status()
    print("Kite credential status (no secrets printed):")
    for name, present in status.items():
        print(f"  {name}: {'ok' if present else 'MISSING'}")
    if not (status["api_key"] and status["access_token"]):
        raise SystemExit(1)
