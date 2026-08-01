#!/usr/bin/env python3
"""
Fixed Crude Oil contract resolver.

Reads TRADING_SYMBOL from config.py, downloads the Kite instrument master,
finds that exact MCX contract, and returns its instrument_token (and metadata).

No rollover logic. No expiry calculations. No automatic contract selection.
Update config.TRADING_SYMBOL manually when you want to switch months.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
import urllib.request
from dataclasses import asdict, dataclass
from datetime import date, datetime
from io import StringIO
from pathlib import Path

import config

INSTRUMENTS_URL = "https://api.kite.trade/instruments"
EXCHANGE = "MCX"
SEGMENT = "MCX-FUT"
UNDERLYING = "CRUDEOIL"


@dataclass(frozen=True)
class CrudeOilContract:
    tradingsymbol: str
    instrument_token: int
    expiry: date | None
    exchange: str = EXCHANGE
    segment: str = SEGMENT
    name: str = UNDERLYING
    lot_size: int = 1
    tick_size: float = 1.0
    exchange_token: int | None = None

    def to_dict(self) -> dict:
        payload = asdict(self)
        payload["expiry"] = self.expiry.isoformat() if self.expiry else None
        return payload


class ContractLookupError(RuntimeError):
    """Raised when the configured trading symbol cannot be resolved."""


def download_instruments(url: str = INSTRUMENTS_URL, timeout: float = 60.0) -> str:
    """Download the latest Kite instrument master CSV as text."""
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "kite-project-crude-oil-selector/1.0"},
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read().decode("utf-8-sig")


def load_instruments_csv(text: str) -> list[dict[str, str]]:
    return list(csv.DictReader(StringIO(text)))


def _parse_expiry(value: str) -> date | None:
    value = (value or "").strip()
    if not value:
        return None
    return datetime.strptime(value, "%Y-%m-%d").date()


def find_contract_by_symbol(
    rows: list[dict[str, str]],
    trading_symbol: str,
    *,
    exchange: str = EXCHANGE,
) -> CrudeOilContract:
    """Find one instrument row by exact tradingsymbol (and exchange)."""
    symbol = (trading_symbol or "").strip()
    if not symbol:
        raise ContractLookupError("TRADING_SYMBOL is empty. Set it in config.py.")

    for row in rows:
        if row.get("tradingsymbol", "").strip() != symbol:
            continue
        if exchange and row.get("exchange") != exchange:
            continue

        try:
            token = int(row["instrument_token"])
        except (KeyError, TypeError, ValueError) as exc:
            raise ContractLookupError(
                f"Invalid instrument_token for {symbol!r}."
            ) from exc

        exchange_token = None
        raw_exchange_token = (row.get("exchange_token") or "").strip()
        if raw_exchange_token:
            try:
                exchange_token = int(raw_exchange_token)
            except ValueError:
                exchange_token = None

        lot_size = 1
        try:
            lot_size = int(float(row.get("lot_size") or 1))
        except ValueError:
            pass

        tick_size = 1.0
        try:
            tick_size = float(row.get("tick_size") or 1)
        except ValueError:
            pass

        return CrudeOilContract(
            tradingsymbol=symbol,
            instrument_token=token,
            expiry=_parse_expiry(row.get("expiry", "")),
            exchange=row.get("exchange") or exchange,
            segment=row.get("segment") or SEGMENT,
            name=row.get("name") or UNDERLYING,
            lot_size=lot_size,
            tick_size=tick_size,
            exchange_token=exchange_token,
        )

    raise ContractLookupError(
        f"Trading symbol {symbol!r} not found in the instrument list "
        f"for exchange {exchange}. Update config.TRADING_SYMBOL."
    )


def resolve_contract(
    *,
    trading_symbol: str | None = None,
    instruments_csv: str | Path | None = None,
    instruments_url: str = INSTRUMENTS_URL,
) -> CrudeOilContract:
    """
    Resolve the fixed contract from config (or an explicit symbol override).

    Steps:
      1. Read TRADING_SYMBOL from config.py (unless overridden).
      2. Download / load the Kite instrument master.
      3. Find the matching contract by trading symbol.
      4. Return tradingsymbol + instrument_token (+ metadata).
    """
    symbol = trading_symbol if trading_symbol is not None else config.TRADING_SYMBOL

    if instruments_csv is not None:
        text = Path(instruments_csv).read_text(encoding="utf-8-sig")
    else:
        text = download_instruments(instruments_url)

    rows = load_instruments_csv(text)
    return find_contract_by_symbol(rows, symbol)


# Backwards-compatible alias used by earlier imports / docs.
get_active_crude_oil_contract = resolve_contract


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Resolve the fixed MCX Crude Oil contract from config.py"
    )
    parser.add_argument(
        "--symbol",
        help="Override config.TRADING_SYMBOL for this run only",
    )
    parser.add_argument(
        "--csv",
        help="Use a local instruments CSV instead of downloading",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print the resolved contract as JSON",
    )
    args = parser.parse_args(argv)

    try:
        contract = resolve_contract(
            trading_symbol=args.symbol,
            instruments_csv=args.csv,
        )
    except Exception as exc:  # noqa: BLE001
        print(f"Crude oil selector failed: {exc}", file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps(contract.to_dict(), indent=2))
    else:
        print("Resolved Crude Oil contract")
        print(f"  tradingsymbol   : {contract.tradingsymbol}")
        print(f"  instrument_token: {contract.instrument_token}")
        print(
            f"  expiry          : "
            f"{contract.expiry.isoformat() if contract.expiry else 'n/a'}"
        )
        print(f"  lot_size        : {contract.lot_size}")
        print(f"  source          : config.TRADING_SYMBOL / override")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
