#!/usr/bin/env python3
"""
Crude Oil contract resolver + 5-day rollover helpers.

Fixed mode:
  Reads TRADING_SYMBOL from config.py and resolves instrument_token.

Rollover mode:
  Builds an MCX CRUDEOIL futures calendar and selects the active contract
  with a 5-calendar-day pre-expiry roll to the next month.
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

import config

INSTRUMENTS_URL = "https://api.kite.trade/instruments"
EXCHANGE = "MCX"
SEGMENT = "MCX-FUT"
UNDERLYING = "CRUDEOIL"
DEFAULT_ROLLOVER_DAYS = 5

MONTH_CODE = {
    1: "JAN",
    2: "FEB",
    3: "MAR",
    4: "APR",
    5: "MAY",
    6: "JUN",
    7: "JUL",
    8: "AUG",
    9: "SEP",
    10: "OCT",
    11: "NOV",
    12: "DEC",
}


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


@dataclass(frozen=True)
class ContractMonth:
    """One CRUDEOIL futures month (may be historical / not in live dump)."""

    tradingsymbol: str
    expiry: date
    instrument_token: int | None = None
    lot_size: int = 1


@dataclass(frozen=True)
class RolloverDay:
    as_of: date
    tradingsymbol: str
    expiry: date
    month_offset: int  # 0=front, 1=next, ... relative to chain on that day


def crude_oil_symbol(year: int, month: int) -> str:
    return f"CRUDEOIL{year % 100:02d}{MONTH_CODE[month]}FUT"


def _adjust_weekday(d: date) -> date:
    """Move weekend expiries back to Friday."""
    if d.weekday() == 5:  # Saturday
        return d - timedelta(days=1)
    if d.weekday() == 6:  # Sunday
        return d - timedelta(days=2)
    return d


def estimate_crude_oil_expiry(year: int, month: int) -> date:
    """
    Approximate MCX Crude Oil futures expiry (typically ~19th of the month).
    Live instrument expiries override this when available.
    """
    return _adjust_weekday(date(year, month, 19))


def iter_year_months(start: date, end: date):
    y, m = start.year, start.month
    while (y, m) <= (end.year, end.month):
        yield y, m
        if m == 12:
            y, m = y + 1, 1
        else:
            m += 1


def list_live_crude_oil_futures(
    rows: list[dict[str, str]] | None = None,
) -> list[CrudeOilContract]:
    """Return live MCX CRUDEOIL futures sorted by expiry."""
    if rows is None:
        rows = load_instruments_csv(download_instruments())
    out: list[CrudeOilContract] = []
    for row in rows:
        if row.get("exchange") != EXCHANGE:
            continue
        if row.get("segment") != SEGMENT:
            continue
        if row.get("name") != UNDERLYING:
            continue
        if (row.get("instrument_type") or "").upper() != "FUT":
            continue
        expiry = _parse_expiry(row.get("expiry", ""))
        if expiry is None:
            continue
        try:
            token = int(row["instrument_token"])
        except (KeyError, TypeError, ValueError):
            continue
        lot_size = 1
        try:
            lot_size = int(float(row.get("lot_size") or 1))
        except ValueError:
            pass
        out.append(
            CrudeOilContract(
                tradingsymbol=row["tradingsymbol"].strip(),
                instrument_token=token,
                expiry=expiry,
                lot_size=lot_size,
            )
        )
    out.sort(key=lambda c: (c.expiry or date.max, c.tradingsymbol))
    return out


def build_contract_calendar(
    start: date,
    end: date,
    *,
    live: list[CrudeOilContract] | None = None,
) -> list[ContractMonth]:
    """
    Build CRUDEOIL month contracts covering [start, end], including one extra
    month after end for early rollover.
    Live instrument expiries/tokens override estimates.
    """
    live = live if live is not None else list_live_crude_oil_futures()
    live_by_symbol = {c.tradingsymbol: c for c in live}

    # Cover through month after `end` so the 5-day roll has a next contract.
    if end.month == 12:
        calendar_end = date(end.year + 1, 1, 1)
    else:
        calendar_end = date(end.year, end.month + 1, 1)

    contracts: list[ContractMonth] = []
    for y, m in iter_year_months(date(start.year, start.month, 1), calendar_end):
        symbol = crude_oil_symbol(y, m)
        if symbol in live_by_symbol:
            lc = live_by_symbol[symbol]
            contracts.append(
                ContractMonth(
                    tradingsymbol=symbol,
                    expiry=lc.expiry or estimate_crude_oil_expiry(y, m),
                    instrument_token=lc.instrument_token,
                    lot_size=lc.lot_size,
                )
            )
        else:
            contracts.append(
                ContractMonth(
                    tradingsymbol=symbol,
                    expiry=estimate_crude_oil_expiry(y, m),
                    instrument_token=None,
                    lot_size=1,
                )
            )
    contracts.sort(key=lambda c: c.expiry)
    return contracts


def select_contract_for_date(
    contracts: list[ContractMonth],
    as_of: date,
    *,
    rollover_days: int = DEFAULT_ROLLOVER_DAYS,
) -> tuple[ContractMonth, int]:
    """
    Pick active contract for as_of with early rollover.

    If nearest expiry is more than rollover_days away → trade it (offset 0).
    Else → trade next expiry (offset 1).
    Returns (contract, month_offset).
    """
    active = [c for c in contracts if c.expiry >= as_of]
    if not active:
        raise ContractLookupError(f"No CRUDEOIL contract available on {as_of}.")
    nearest = active[0]
    days_left = (nearest.expiry - as_of).days
    if days_left > rollover_days:
        return nearest, 0
    if len(active) < 2:
        raise ContractLookupError(
            f"Need next-month contract to roll {nearest.tradingsymbol} on {as_of}."
        )
    return active[1], 1


def build_rollover_schedule(
    start: date,
    end: date,
    *,
    rollover_days: int = DEFAULT_ROLLOVER_DAYS,
    live: list[CrudeOilContract] | None = None,
) -> list[RolloverDay]:
    """Daily schedule of which CRUDEOIL contract to trade."""
    contracts = build_contract_calendar(start, end, live=live)
    schedule: list[RolloverDay] = []
    d = start
    while d <= end:
        # Skip weekends for schedule compactness (MCX weekdays).
        if d.weekday() < 5:
            contract, offset = select_contract_for_date(
                contracts, d, rollover_days=rollover_days
            )
            schedule.append(
                RolloverDay(
                    as_of=d,
                    tradingsymbol=contract.tradingsymbol,
                    expiry=contract.expiry,
                    month_offset=offset,
                )
            )
        d += timedelta(days=1)
    return schedule


def schedule_segments(
    schedule: list[RolloverDay],
) -> list[tuple[str, int, date, date]]:
    """
    Collapse consecutive days with the same symbol/offset into segments.
    Returns list of (tradingsymbol, month_offset, from_date, to_date).
    """
    if not schedule:
        return []
    segments: list[tuple[str, int, date, date]] = []
    cur_sym = schedule[0].tradingsymbol
    cur_off = schedule[0].month_offset
    seg_from = schedule[0].as_of
    seg_to = schedule[0].as_of
    for day in schedule[1:]:
        if day.tradingsymbol == cur_sym and day.month_offset == cur_off:
            seg_to = day.as_of
            continue
        segments.append((cur_sym, cur_off, seg_from, seg_to))
        cur_sym = day.tradingsymbol
        cur_off = day.month_offset
        seg_from = day.as_of
        seg_to = day.as_of
    segments.append((cur_sym, cur_off, seg_from, seg_to))
    return segments


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
