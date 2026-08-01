#!/usr/bin/env python3
"""
Crude Oil contract selector for MCX futures.

Downloads the Kite instrument master, finds MCX CRUDEOIL futures, and picks
the active contract using a 5-calendar-day pre-expiry rollover rule.

Never returns an expired contract. Never hard-codes contract month names.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
import urllib.request
from dataclasses import asdict, dataclass
from datetime import date, datetime, timedelta
from io import StringIO
from pathlib import Path
from typing import Iterable, Sequence

INSTRUMENTS_URL = "https://api.kite.trade/instruments"
EXCHANGE = "MCX"
SEGMENT = "MCX-FUT"
UNDERLYING = "CRUDEOIL"
DEFAULT_ROLLOVER_DAYS = 5


@dataclass(frozen=True)
class CrudeOilContract:
    tradingsymbol: str
    instrument_token: int
    expiry: date
    exchange: str = EXCHANGE
    segment: str = SEGMENT
    name: str = UNDERLYING
    lot_size: int = 1
    tick_size: float = 1.0
    exchange_token: int | None = None

    def to_dict(self) -> dict:
        payload = asdict(self)
        payload["expiry"] = self.expiry.isoformat()
        return payload


class ContractSelectionError(RuntimeError):
    """Raised when no valid Crude Oil futures contract can be selected."""


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


def _parse_expiry(value: str) -> date:
    value = (value or "").strip()
    if not value:
        raise ValueError("missing expiry")
    # Kite instruments use YYYY-MM-DD.
    return datetime.strptime(value, "%Y-%m-%d").date()


def find_crude_oil_futures(
    rows: Iterable[dict[str, str]],
    *,
    as_of: date | None = None,
) -> list[CrudeOilContract]:
    """
    Return non-expired MCX Crude Oil futures, sorted by expiry ascending.
    """
    today = as_of or date.today()
    contracts: list[CrudeOilContract] = []

    for row in rows:
        if row.get("exchange") != EXCHANGE:
            continue
        if row.get("segment") != SEGMENT:
            continue
        if row.get("name") != UNDERLYING:
            continue
        if (row.get("instrument_type") or "").upper() != "FUT":
            continue

        try:
            expiry = _parse_expiry(row.get("expiry", ""))
        except ValueError:
            continue

        # Never trade an expired contract.
        if expiry < today:
            continue

        try:
            token = int(row["instrument_token"])
        except (KeyError, TypeError, ValueError):
            continue

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

        contracts.append(
            CrudeOilContract(
                tradingsymbol=row["tradingsymbol"].strip(),
                instrument_token=token,
                expiry=expiry,
                lot_size=lot_size,
                tick_size=tick_size,
                exchange_token=exchange_token,
            )
        )

    contracts.sort(key=lambda c: (c.expiry, c.tradingsymbol))
    return contracts


def select_crude_oil_contract(
    contracts: Sequence[CrudeOilContract],
    *,
    as_of: date | None = None,
    rollover_days: int = DEFAULT_ROLLOVER_DAYS,
) -> CrudeOilContract:
    """
    Apply the rollover rule:

    - Sort by expiry (caller normally already does this).
    - Use the nearest expiry if it is more than `rollover_days` away.
    - Otherwise use the next expiry contract.
    """
    today = as_of or date.today()
    if rollover_days < 0:
        raise ValueError("rollover_days must be >= 0")

    active = [c for c in contracts if c.expiry >= today]
    if not active:
        raise ContractSelectionError(
            f"No non-expired {UNDERLYING} futures found on {EXCHANGE} as of {today}."
        )

    nearest = active[0]
    days_to_expiry = (nearest.expiry - today).days

    # More than N calendar days away → trade front month.
    if days_to_expiry > rollover_days:
        return nearest

    # Within the last N days before expiry → roll to next month.
    if len(active) < 2:
        raise ContractSelectionError(
            f"Nearest contract {nearest.tradingsymbol} expires in {days_to_expiry} day(s) "
            f"(rollover window={rollover_days}), but no next-month contract is available."
        )
    return active[1]


def get_active_crude_oil_contract(
    *,
    as_of: date | None = None,
    rollover_days: int = DEFAULT_ROLLOVER_DAYS,
    instruments_csv: str | Path | None = None,
    instruments_url: str = INSTRUMENTS_URL,
) -> CrudeOilContract:
    """
    Download (or load) the instrument master and return the selected contract.
    """
    if instruments_csv is not None:
        text = Path(instruments_csv).read_text(encoding="utf-8-sig")
    else:
        text = download_instruments(instruments_url)

    rows = load_instruments_csv(text)
    contracts = find_crude_oil_futures(rows, as_of=as_of)
    return select_crude_oil_contract(
        contracts,
        as_of=as_of,
        rollover_days=rollover_days,
    )


def _parse_as_of(value: str | None) -> date | None:
    if not value:
        return None
    return datetime.strptime(value, "%Y-%m-%d").date()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Select the active MCX Crude Oil futures contract"
    )
    parser.add_argument(
        "--as-of",
        help="Selection date YYYY-MM-DD (default: today)",
    )
    parser.add_argument(
        "--rollover-days",
        type=int,
        default=DEFAULT_ROLLOVER_DAYS,
        help=f"Roll to next month when within this many calendar days of expiry "
        f"(default {DEFAULT_ROLLOVER_DAYS})",
    )
    parser.add_argument(
        "--csv",
        help="Use a local instruments CSV instead of downloading",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print the selected contract as JSON",
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="List all non-expired CRUDEOIL futures before selecting",
    )
    args = parser.parse_args(argv)

    as_of = _parse_as_of(args.as_of)

    try:
        if args.csv:
            text = Path(args.csv).read_text(encoding="utf-8-sig")
        else:
            print("Downloading instrument master...", file=sys.stderr)
            text = download_instruments()

        rows = load_instruments_csv(text)
        contracts = find_crude_oil_futures(rows, as_of=as_of)

        if args.list:
            for contract in contracts:
                days = (contract.expiry - (as_of or date.today())).days
                print(
                    f"{contract.tradingsymbol}\t"
                    f"expiry={contract.expiry.isoformat()}\t"
                    f"days={days}\t"
                    f"token={contract.instrument_token}"
                )

        selected = select_crude_oil_contract(
            contracts,
            as_of=as_of,
            rollover_days=args.rollover_days,
        )
    except Exception as exc:  # noqa: BLE001
        print(f"Crude oil selector failed: {exc}", file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps(selected.to_dict(), indent=2))
    else:
        today = as_of or date.today()
        days = (selected.expiry - today).days
        print("Selected Crude Oil contract")
        print(f"  tradingsymbol   : {selected.tradingsymbol}")
        print(f"  instrument_token: {selected.instrument_token}")
        print(f"  expiry          : {selected.expiry.isoformat()}")
        print(f"  days_to_expiry  : {days}")
        print(f"  lot_size        : {selected.lot_size}")
        print(f"  as_of           : {today.isoformat()}")
        print(f"  rollover_days   : {args.rollover_days}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
