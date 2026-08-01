#!/usr/bin/env python3
"""Unit tests for the Crude Oil contract selector (no live network required)."""

from __future__ import annotations

import unittest
from datetime import date
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from crude_oil_selector import (  # noqa: E402
    ContractSelectionError,
    CrudeOilContract,
    find_crude_oil_futures,
    select_crude_oil_contract,
)

SAMPLE_CSV = """instrument_token,exchange_token,tradingsymbol,name,last_price,expiry,strike,tick_size,lot_size,instrument_type,segment,exchange
111,1,CRUDEOIL26AUGFUT,CRUDEOIL,0,2026-08-19,0,1,1,FUT,MCX-FUT,MCX
222,2,CRUDEOIL26SEPFUT,CRUDEOIL,0,2026-09-18,0,1,1,FUT,MCX-FUT,MCX
333,3,CRUDEOIL26OCTFUT,CRUDEOIL,0,2026-10-19,0,1,1,FUT,MCX-FUT,MCX
444,4,CRUDEOIL26JULFUT,CRUDEOIL,0,2026-07-18,0,1,1,FUT,MCX-FUT,MCX
555,5,GOLDM26AUGFUT,GOLD,0,2026-08-19,0,1,1,FUT,MCX-FUT,MCX
666,6,CRUDEOIL26AUG5000CE,CRUDEOIL,0,2026-08-19,5000,1,1,CE,MCX-OPT,MCX
"""


class CrudeOilSelectorTests(unittest.TestCase):
    def setUp(self) -> None:
        import csv
        from io import StringIO

        self.rows = list(csv.DictReader(StringIO(SAMPLE_CSV)))

    def test_filters_mcx_crude_futures_and_drops_expired(self) -> None:
        contracts = find_crude_oil_futures(self.rows, as_of=date(2026, 8, 1))
        symbols = [c.tradingsymbol for c in contracts]
        self.assertEqual(
            symbols,
            ["CRUDEOIL26AUGFUT", "CRUDEOIL26SEPFUT", "CRUDEOIL26OCTFUT"],
        )
        # July expired relative to 1 Aug; options and GOLD excluded.
        self.assertNotIn("CRUDEOIL26JULFUT", symbols)
        self.assertNotIn("GOLDM26AUGFUT", symbols)

    def test_selects_front_month_when_more_than_5_days_away(self) -> None:
        # Example from the strategy: 1 Aug 2026 → AUG (expires 19 Aug).
        contracts = find_crude_oil_futures(self.rows, as_of=date(2026, 8, 1))
        selected = select_crude_oil_contract(contracts, as_of=date(2026, 8, 1))
        self.assertEqual(selected.tradingsymbol, "CRUDEOIL26AUGFUT")
        self.assertEqual(selected.instrument_token, 111)
        self.assertEqual(selected.expiry, date(2026, 8, 19))

    def test_rolls_to_next_month_inside_5_day_window(self) -> None:
        # Example: 15 Aug 2026 → 4 days to 19 Aug → SEP.
        contracts = find_crude_oil_futures(self.rows, as_of=date(2026, 8, 15))
        selected = select_crude_oil_contract(contracts, as_of=date(2026, 8, 15))
        self.assertEqual(selected.tradingsymbol, "CRUDEOIL26SEPFUT")
        self.assertEqual(selected.instrument_token, 222)

    def test_rolls_on_exactly_5_days_remaining(self) -> None:
        # 14 Aug → 5 days to 19 Aug → still inside window → SEP.
        contracts = find_crude_oil_futures(self.rows, as_of=date(2026, 8, 14))
        selected = select_crude_oil_contract(contracts, as_of=date(2026, 8, 14))
        self.assertEqual(selected.tradingsymbol, "CRUDEOIL26SEPFUT")

    def test_never_returns_expired_contract(self) -> None:
        contracts = find_crude_oil_futures(self.rows, as_of=date(2026, 8, 20))
        symbols = [c.tradingsymbol for c in contracts]
        self.assertNotIn("CRUDEOIL26AUGFUT", symbols)
        selected = select_crude_oil_contract(contracts, as_of=date(2026, 8, 20))
        self.assertEqual(selected.tradingsymbol, "CRUDEOIL26SEPFUT")

    def test_raises_when_no_contracts(self) -> None:
        with self.assertRaises(ContractSelectionError):
            select_crude_oil_contract([], as_of=date(2026, 8, 1))

    def test_raises_when_rollover_needed_but_no_next_month(self) -> None:
        only = [
            CrudeOilContract(
                tradingsymbol="CRUDEOIL26AUGFUT",
                instrument_token=111,
                expiry=date(2026, 8, 19),
            )
        ]
        with self.assertRaises(ContractSelectionError):
            select_crude_oil_contract(only, as_of=date(2026, 8, 15))


if __name__ == "__main__":
    unittest.main()
