"""
Test Kite Connect without placing orders.

Loads credentials from env / .env / access_token.txt / .kite_session.json,
fetches profile + margins, and prints a short connection summary.
"""

from __future__ import annotations

import sys

from kite_credentials import credential_status, make_kite


def main() -> int:
    status = credential_status()
    if not (status["api_key"] and status["access_token"]):
        missing = [k for k, ok in status.items() if k != "api_secret" and not ok]
        raise RuntimeError(
            "Missing credentials: "
            + ", ".join(missing)
            + ". Set KITE_API_KEY and KITE_ACCESS_TOKEN, or run "
            "python scripts/zerodha_login.py locally."
        )

    kite = make_kite()
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
