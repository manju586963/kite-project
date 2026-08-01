"""
Test Kite Connect without placing orders.

Loads the daily access_token from access_token.txt (or .kite_session.json),
fetches profile + margins, and prints a short connection summary.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from kiteconnect import KiteConnect

ROOT = Path(__file__).resolve().parent
TOKEN_FILE = ROOT / "access_token.txt"
SESSION_FILE = ROOT / ".kite_session.json"


def load_access_token() -> str:
    if TOKEN_FILE.exists():
        token = TOKEN_FILE.read_text(encoding="utf-8").strip()
        if token:
            return token

    if SESSION_FILE.exists():
        data = json.loads(SESSION_FILE.read_text(encoding="utf-8"))
        token = (data.get("access_token") or "").strip()
        if token:
            return token

    raise RuntimeError(
        "access_token.txt was not found. Run scripts/zerodha_login.py and log in first."
    )


def main() -> int:
    load_dotenv(ROOT / ".env")

    api_key = os.getenv("KITE_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("KITE_API_KEY is missing from the .env file.")

    access_token = load_access_token()

    kite = KiteConnect(api_key=api_key)
    kite.set_access_token(access_token)

    profile = kite.profile()
    margins = kite.margins()

    print("Connection successful")
    print("User name:", profile.get("user_name"))
    print("User ID:", profile.get("user_id"))
    print("Broker:", profile.get("broker"))
    print("Available margin data received:", bool(margins))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:  # noqa: BLE001
        print(f"Connection test failed: {exc}", file=sys.stderr)
        raise SystemExit(1)
