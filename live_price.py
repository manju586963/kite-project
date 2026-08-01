#!/usr/bin/env python3
"""
Step 3 — Live price feed for MCX CRUDEOIL August 2026 futures.

- Finds the August 2026 CRUDEOIL contract from Kite's instrument list
  (instrument_token is looked up live; never permanently hard-coded).
- Displays live LTP, volume, and open interest.
- Places no paper or real orders.

Usage:
  python scripts/zerodha_login.py
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
from kiteconnect import KiteConnect, KiteTicker

# =========================================================
# FIXED CONTRACT (August 2026)
# Prefer config.TRADING_SYMBOL when set; otherwise year/month match.
# =========================================================
try:
    import config as app_config

    CONFIG_TRADING_SYMBOL = getattr(app_config, "TRADING_SYMBOL", "").strip()
except ImportError:
    CONFIG_TRADING_SYMBOL = ""

CONTRACT_NAME = "CRUDEOIL"
CONTRACT_YEAR = 2026
CONTRACT_MONTH = 8  # August

ROOT = Path(__file__).resolve().parent
ACCESS_TOKEN_FILE = ROOT / "access_token.txt"
SESSION_FILE = ROOT / ".kite_session.json"

# =========================================================
# LOAD KITE CREDENTIALS
# =========================================================
load_dotenv(ROOT / ".env")

api_key = os.getenv("KITE_API_KEY", "").strip()
if not api_key and SESSION_FILE.exists():
    api_key = (
        json.loads(SESSION_FILE.read_text(encoding="utf-8")).get("api_key") or ""
    ).strip()

if not api_key:
    raise RuntimeError("KITE_API_KEY is missing from the .env file.")

access_token = ""
if ACCESS_TOKEN_FILE.exists():
    access_token = ACCESS_TOKEN_FILE.read_text(encoding="utf-8").strip()
elif SESSION_FILE.exists():
    access_token = (
        json.loads(SESSION_FILE.read_text(encoding="utf-8")).get("access_token") or ""
    ).strip()

if not access_token:
    raise RuntimeError(
        "access_token.txt was not found. "
        "Complete today's Zerodha login first "
        "(python scripts/zerodha_login.py)."
    )

# =========================================================
# CONNECT TO KITE
# =========================================================
kite = KiteConnect(api_key=api_key)
kite.set_access_token(access_token)


# =========================================================
# FIND AUGUST CRUDEOIL FUTURES
# =========================================================
def find_contract():
    print("Downloading MCX instruments...")
    instruments = kite.instruments("MCX")
    matches = []

    for instrument in instruments:
        name = str(instrument.get("name", "")).upper()
        instrument_type = str(instrument.get("instrument_type", "")).upper()
        expiry = instrument.get("expiry")
        tradingsymbol = str(instrument.get("tradingsymbol", "")).strip()

        if not expiry:
            continue
        if name != CONTRACT_NAME:
            continue
        if instrument_type != "FUT":
            continue

        # Prefer exact symbol from config.py when provided.
        if CONFIG_TRADING_SYMBOL:
            if tradingsymbol == CONFIG_TRADING_SYMBOL:
                matches.append(instrument)
            continue

        if expiry.year == CONTRACT_YEAR and expiry.month == CONTRACT_MONTH:
            matches.append(instrument)

    if not matches:
        target = CONFIG_TRADING_SYMBOL or (
            f"{CONTRACT_NAME} {CONTRACT_YEAR}-{CONTRACT_MONTH:02d}"
        )
        raise RuntimeError(
            f"MCX CRUDEOIL contract was not found ({target}). "
            "Check config.TRADING_SYMBOL / contract month."
        )

    matches.sort(key=lambda item: item["expiry"])
    if len(matches) > 1:
        print(
            "Warning: More than one matching contract was found. "
            "The earliest expiry was selected."
        )
    return matches[0]


contract = find_contract()
instrument_token = int(contract["instrument_token"])
trading_symbol = contract["tradingsymbol"]
expiry = contract["expiry"]
lot_size = int(contract["lot_size"])
tick_size = float(contract["tick_size"])
tokens = [instrument_token]

# =========================================================
# DISPLAY CONTRACT
# =========================================================
print()
print("========================================")
print("MCX CRUDEOIL LIVE PRICE")
print("========================================")
print("Contract         :", trading_symbol)
print("Expiry           :", expiry)
print("Instrument token :", instrument_token)
print("Lot size         :", lot_size)
print("Tick size        :", tick_size)
print("Orders           : DISABLED")
print("========================================")
print()
print("Press Ctrl + C to stop.")
print()

# =========================================================
# WEBSOCKET
# =========================================================
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

# =========================================================
# START
# =========================================================
try:
    ticker.connect(threaded=False)
except KeyboardInterrupt:
    stop_program()
except Exception as error:
    print("Unable to start live feed.")
    print("Error:", error)
    sys.exit(1)
