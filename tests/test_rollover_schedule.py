#!/usr/bin/env python3
"""Unit tests for CRUDEOIL 5-day rollover schedule."""

from __future__ import annotations

import unittest
from datetime import date
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from crude_oil_selector import (  # noqa: E402
    ContractMonth,
    build_contract_calendar,
    build_rollover_schedule,
    crude_oil_symbol,
    schedule_segments,
    select_contract_for_date,
)


class RolloverScheduleTests(unittest.TestCase):
    def test_symbol_format(self) -> None:
        self.assertEqual(crude_oil_symbol(2025, 6), "CRUDEOIL25JUNFUT")
        self.assertEqual(crude_oil_symbol(2026, 8), "CRUDEOIL26AUGFUT")

    def test_select_front_when_more_than_5_days(self) -> None:
        contracts = [
            ContractMonth("CRUDEOIL26AUGFUT", date(2026, 8, 19)),
            ContractMonth("CRUDEOIL26SEPFUT", date(2026, 9, 21)),
        ]
        # 1 Aug 2026 → 18 days to 19 Aug → front
        c, offset = select_contract_for_date(contracts, date(2026, 8, 1), rollover_days=5)
        self.assertEqual(c.tradingsymbol, "CRUDEOIL26AUGFUT")
        self.assertEqual(offset, 0)

    def test_select_next_inside_5_day_window(self) -> None:
        contracts = [
            ContractMonth("CRUDEOIL26AUGFUT", date(2026, 8, 19)),
            ContractMonth("CRUDEOIL26SEPFUT", date(2026, 9, 21)),
        ]
        # 15 Aug → 4 days left → roll to SEP
        c, offset = select_contract_for_date(contracts, date(2026, 8, 15), rollover_days=5)
        self.assertEqual(c.tradingsymbol, "CRUDEOIL26SEPFUT")
        self.assertEqual(offset, 1)

    def test_schedule_segments_collapse(self) -> None:
        schedule = build_rollover_schedule(
            date(2026, 8, 10),
            date(2026, 8, 20),
            rollover_days=5,
            live=[],
        )
        segs = schedule_segments(schedule)
        self.assertGreaterEqual(len(segs), 1)
        # Around 14 Aug (5 days before 19) should switch to next month.
        symbols = {d.tradingsymbol for d in schedule}
        self.assertIn("CRUDEOIL26AUGFUT", symbols)
        self.assertIn("CRUDEOIL26SEPFUT", symbols)

    def test_calendar_covers_requested_range(self) -> None:
        cal = build_contract_calendar(date(2025, 6, 1), date(2026, 7, 31), live=[])
        symbols = [c.tradingsymbol for c in cal]
        self.assertIn("CRUDEOIL25JUNFUT", symbols)
        self.assertIn("CRUDEOIL26JULFUT", symbols)
        # Extra month after end for roll target
        self.assertIn("CRUDEOIL26AUGFUT", symbols)


if __name__ == "__main__":
    unittest.main()
