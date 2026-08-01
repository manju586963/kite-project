#!/usr/bin/env python3
"""Unit tests for intraday Supertrend paper trading (no network)."""

from __future__ import annotations

import unittest
from datetime import datetime, timedelta
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from historical_supertrend_paper import (  # noqa: E402
    Candle,
    CandleST,
    allows_new_entry,
    compute_supertrend,
    filter_last_trading_days,
    is_square_off_candle,
    make_output_dir,
    simulate_paper_trades,
    summarize_trades,
)


def _candle(ts: datetime, close: float = 100.0) -> CandleST:
    return CandleST(
        date=ts,
        open=close,
        high=close + 1,
        low=close - 1,
        close=close,
        volume=10,
        signal=None,
        direction="bullish",
        supertrend=close - 5,
        atr=1.0,
    )


class IntradayRuleTests(unittest.TestCase):
    def test_entry_cutoff_and_square_off_times(self) -> None:
        self.assertTrue(allows_new_entry(datetime(2026, 8, 1, 22, 45)))
        self.assertTrue(allows_new_entry(datetime(2026, 8, 1, 23, 0)))
        self.assertFalse(allows_new_entry(datetime(2026, 8, 1, 23, 15)))
        self.assertFalse(is_square_off_candle(datetime(2026, 8, 1, 23, 0)))
        self.assertTrue(is_square_off_candle(datetime(2026, 8, 1, 23, 15)))

    def test_supertrend_10_1_emits_flips(self) -> None:
        start = datetime(2026, 7, 1, 10, 0)
        prices = (
            [(100 - i, 101 - i, 99 - i, 100 - i) for i in range(20)]
            + [(80 + i, 81 + i, 79 + i, 80 + i) for i in range(20)]
            + [(100 - i, 101 - i, 99 - i, 100 - i) for i in range(20)]
        )
        candles = [
            Candle(
                date=start + timedelta(minutes=15 * i),
                open=o,
                high=h,
                low=l,
                close=c,
            )
            for i, (o, h, l, c) in enumerate(prices)
        ]
        rows = compute_supertrend(candles, period=10, multiplier=1)
        signals = [r.signal for r in rows if r.signal]
        self.assertIn("BUY", signals)
        self.assertIn("SELL", signals)

    def test_intraday_square_off_at_2315(self) -> None:
        d = datetime(2026, 8, 1)
        rows = [
            _candle(d.replace(hour=10, minute=0), 100),
            _candle(d.replace(hour=11, minute=0), 105),
            _candle(d.replace(hour=23, minute=15), 102),
        ]
        rows[0].signal = "BUY"
        rows[1].signal = None
        rows[2].signal = "SELL"  # after cutoff / at square-off — ignored for entry

        trades = simulate_paper_trades(rows, lot_size=1)
        self.assertEqual(len(trades), 1)
        self.assertEqual(trades[0].side, "BUY")
        self.assertEqual(trades[0].exit_reason, "INTRADAY_SQUARE_OFF")
        self.assertEqual(trades[0].exit_price, 102)
        self.assertAlmostEqual(trades[0].points or 0, 2)

    def test_no_new_entry_after_2300(self) -> None:
        d = datetime(2026, 8, 1)
        rows = [
            _candle(d.replace(hour=22, minute=30), 100),
            _candle(d.replace(hour=23, minute=0), 101),  # last allowed entry time
            _candle(d.replace(hour=23, minute=15), 99),
        ]
        rows[0].signal = None
        rows[1].signal = "BUY"
        rows[2].signal = "SELL"

        trades = simulate_paper_trades(rows, lot_size=1)
        self.assertEqual(len(trades), 1)
        self.assertEqual(trades[0].entry_time.hour, 23)
        self.assertEqual(trades[0].entry_time.minute, 0)
        self.assertEqual(trades[0].exit_reason, "INTRADAY_SQUARE_OFF")

    def test_daily_reset_does_not_carry_position(self) -> None:
        day1 = datetime(2026, 8, 1)
        day2 = datetime(2026, 8, 2)
        rows = [
            _candle(day1.replace(hour=10, minute=0), 100),
            _candle(day1.replace(hour=23, minute=15), 110),
            _candle(day2.replace(hour=10, minute=0), 111),
            _candle(day2.replace(hour=23, minute=15), 105),
        ]
        rows[0].signal = "BUY"
        rows[1].signal = None
        rows[2].signal = None  # no fresh signal on day 2 → stays flat
        rows[3].signal = None

        trades = simulate_paper_trades(rows, lot_size=1)
        self.assertEqual(len(trades), 1)
        self.assertEqual(trades[0].trade_date.isoformat(), "2026-08-01")
        self.assertEqual(trades[0].exit_reason, "INTRADAY_SQUARE_OFF")

    def test_flip_within_day(self) -> None:
        d = datetime(2026, 8, 1)
        rows = [
            _candle(d.replace(hour=10, minute=0), 100),
            _candle(d.replace(hour=12, minute=0), 110),
            _candle(d.replace(hour=23, minute=15), 108),
        ]
        rows[0].signal = "BUY"
        rows[1].signal = "SELL"
        rows[2].signal = None

        trades = simulate_paper_trades(rows, lot_size=10)
        self.assertEqual(len(trades), 2)
        self.assertEqual(trades[0].exit_reason, "FLIP_SELL")
        self.assertEqual(trades[1].side, "SELL")
        self.assertEqual(trades[1].exit_reason, "INTRADAY_SQUARE_OFF")
        self.assertAlmostEqual(trades[0].pnl or 0, 100.0)  # 10 pts * lot 10

    def test_filter_last_trading_days(self) -> None:
        rows = []
        for day in range(1, 6):
            rows.append(_candle(datetime(2026, 8, day, 10, 0)))
        filtered = filter_last_trading_days(rows, trading_days=2)
        days = sorted({r.date.date() for r in filtered})
        self.assertEqual(days, [datetime(2026, 8, 4).date(), datetime(2026, 8, 5).date()])

    def test_summary_includes_square_offs(self) -> None:
        d = datetime(2026, 8, 1)
        rows = [
            _candle(d.replace(hour=10, minute=0), 100),
            _candle(d.replace(hour=23, minute=15), 101),
        ]
        rows[0].signal = "BUY"
        trades = simulate_paper_trades(rows, lot_size=1)
        stats = summarize_trades(trades)
        self.assertEqual(stats["square_offs"], 1)
        self.assertEqual(stats["total_trades"], 1)

    def test_output_dir_is_dated_and_unique(self) -> None:
        import shutil
        from historical_supertrend_paper import OUTPUT_ROOT

        fixed = datetime(2026, 8, 1, 16, 41, 5)
        first = make_output_dir(fixed)
        second = make_output_dir(fixed)
        try:
            self.assertEqual(first.name, "01-aug-2026")
            self.assertEqual(second.name, "01-aug-2026_2")
            self.assertNotEqual(first, second)
            self.assertTrue(first.is_dir())
            self.assertTrue(second.is_dir())
            self.assertEqual(first.parent, OUTPUT_ROOT)
        finally:
            shutil.rmtree(first, ignore_errors=True)
            shutil.rmtree(second, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
