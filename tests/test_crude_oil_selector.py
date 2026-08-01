#!/usr/bin/env python3
"""Unit tests for the fixed Crude Oil contract resolver."""

from __future__ import annotations

import csv
import unittest
from datetime import date
from io import StringIO
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from crude_oil_selector import (  # noqa: E402
    ContractLookupError,
    find_contract_by_symbol,
    resolve_contract,
)

SAMPLE_CSV = """instrument_token,exchange_token,tradingsymbol,name,last_price,expiry,strike,tick_size,lot_size,instrument_type,segment,exchange
111,1,CRUDEOIL26AUGFUT,CRUDEOIL,0,2026-08-19,0,1,1,FUT,MCX-FUT,MCX
222,2,CRUDEOIL26SEPFUT,CRUDEOIL,0,2026-09-21,0,1,1,FUT,MCX-FUT,MCX
555,5,GOLDM26AUGFUT,GOLD,0,2026-08-19,0,1,1,FUT,MCX-FUT,MCX
"""


class FixedContractResolverTests(unittest.TestCase):
    def setUp(self) -> None:
        self.rows = list(csv.DictReader(StringIO(SAMPLE_CSV)))
        self.csv_path = ROOT / "tests" / "_sample_instruments.csv"
        self.csv_path.write_text(SAMPLE_CSV, encoding="utf-8")

    def tearDown(self) -> None:
        if self.csv_path.exists():
            self.csv_path.unlink()

    def test_finds_exact_symbol(self) -> None:
        contract = find_contract_by_symbol(self.rows, "CRUDEOIL26AUGFUT")
        self.assertEqual(contract.tradingsymbol, "CRUDEOIL26AUGFUT")
        self.assertEqual(contract.instrument_token, 111)
        self.assertEqual(contract.expiry, date(2026, 8, 19))

    def test_resolve_from_config_symbol_via_csv(self) -> None:
        contract = resolve_contract(
            trading_symbol="CRUDEOIL26SEPFUT",
            instruments_csv=self.csv_path,
        )
        self.assertEqual(contract.tradingsymbol, "CRUDEOIL26SEPFUT")
        self.assertEqual(contract.instrument_token, 222)

    def test_missing_symbol_raises(self) -> None:
        with self.assertRaises(ContractLookupError):
            find_contract_by_symbol(self.rows, "CRUDEOIL26NOVFUT")

    def test_empty_symbol_raises(self) -> None:
        with self.assertRaises(ContractLookupError):
            find_contract_by_symbol(self.rows, "  ")

    def test_does_not_auto_switch_months(self) -> None:
        # Fixed symbol stays AUGUST even if a later contract exists.
        contract = find_contract_by_symbol(self.rows, "CRUDEOIL26AUGFUT")
        self.assertEqual(contract.tradingsymbol, "CRUDEOIL26AUGFUT")
        self.assertNotEqual(contract.tradingsymbol, "CRUDEOIL26SEPFUT")


if __name__ == "__main__":
    unittest.main()
