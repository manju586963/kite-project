#!/usr/bin/env python3
"""
Step 3 — Live price feed for the fixed MCX Crude Oil futures contract.

- Resolves the contract from config.TRADING_SYMBOL via crude_oil_selector
  (looks up instrument_token from the live Kite instrument list; never
  hard-codes the token).
- Streams LTP, volume, and open interest over KiteTicker.
- Places no paper or real orders.

Usage:
  python scripts/zerodha_login.py   # once per trading day
  python live_price.py
  Ctrl+C to stop
"""

from __future__ import annotations

import json
import os
import signal
import sys
from pathlib import Path

from dotenv import load_dotenv
from kiteconnect import KiteTicker

import config
from crude_oil_selector import resolve_contract

ROOT = Path(__file__).resolve().parent
ACCESS_TOKEN_FILE = ROOT / "access_token.txt"
SESSION_FILE = ROOT / ".kite_session.json"


def load_access_token() -> str:
    if ACCESS_TOKEN_FILE.exists():
        token = ACCESS_TOKEN_FILE.read_text(encoding="utf-8").strip()
        if token:
            return token

    if SESSION_FILE.exists():
        data = json.loads(SESSION_FILE.read_text(encoding="utf-8"))
        token = (data.get("access_token") or "").strip()
        if token:
            return token

    raise RuntimeError(
        "access_token.txt was not found. "
        "Complete today's Zerodha login first (python scripts/zerodha_login.py)."
    )


def load_api_key() -> str:
    load_dotenv(ROOT / ".env")
    api_key = os.getenv("KITE_API_KEY", "").strip()
    if api_key:
        return api_key

    if SESSION_FILE.exists():
        data = json.loads(SESSION_FILE.read_text(encoding="utf-8"))
        api_key = (data.get("api_key") or "").strip()
        if api_key:
            return api_key

    raise RuntimeError("KITE_API_KEY is missing from the .env file.")


def print_contract_banner(contract) -> None:
    print()
    print("========================================")
    print("MCX CRUDEOIL LIVE PRICE")
    print("========================================")
    print("Contract         :", contract.tradingsymbol)
    print("Expiry           :", contract.expiry)
    print("Instrument token :", contract.instrument_token)
    print("Lot size         :", contract.lot_size)
    print("Tick size        :", contract.tick_size)
    print("Orders           : DISABLED")
    print("========================================")
    print()
    print("Press Ctrl + C to stop.")
    print()


def main() -> int:
    api_key = load_api_key()
    access_token = load_access_token()

    print(
        f"Resolving fixed contract from config.TRADING_SYMBOL="
        f"{config.TRADING_SYMBOL!r} ..."
    )
    contract = resolve_contract()
    tokens = [int(contract.instrument_token)]
    trading_symbol = contract.tradingsymbol

    print_contract_banner(contract)

    ticker = KiteTicker(
        api_key,
        access_token,
        reconnect=True,
        reconnect_max_tries=50,
        reconnect_max_delay=60,
    )

    def on_connect(ws, response):
        print("Connected to Kite.")
        print("Subscribed to:", trading_symbol)
        print()
        ws.subscribe(tokens)
        ws.set_mode(ws.MODE_FULL, tokens)

    def on_ticks(ws, ticks):
        for tick in ticks:
            last_price = tick.get("last_price")
            volume = tick.get("volume_traded")
            open_interest = tick.get("oi")
            timestamp = tick.get("exchange_timestamp")
            print(
                f"{timestamp} | "
                f"{trading_symbol} | "
                f"LTP: {last_price} | "
                f"Volume: {volume} | "
                f"OI: {open_interest}"
            )

    def on_error(ws, code, reason):
        print()
        print("WebSocket error:", code, reason)

    def on_close(ws, code, reason):
        print()
        print("WebSocket closed:", code, reason)

    def on_reconnect(ws, attempt):
        print("Reconnecting. Attempt:", attempt)

    def on_noreconnect(ws):
        print("Maximum reconnection attempts reached.")

    def stop_program(signum=None, frame=None):
        print()
        print("Stopping live price feed...")
        try:
            ticker.close()
        except Exception:
            pass
        sys.exit(0)

    ticker.on_connect = on_connect
    ticker.on_ticks = on_ticks
    ticker.on_error = on_error
    ticker.on_close = on_close
    ticker.on_reconnect = on_reconnect
    ticker.on_noreconnect = on_noreconnect

    signal.signal(signal.SIGINT, stop_program)

    try:
        ticker.connect(threaded=False)
    except KeyboardInterrupt:
        stop_program()
    except Exception as error:
        print("Unable to start live feed.")
        print("Error:", error)
        return 1
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except RuntimeError as exc:
        print(f"Unable to start live feed.\nError: {exc}", file=sys.stderr)
        raise SystemExit(1)
