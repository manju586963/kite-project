#!/usr/bin/env python3
"""Unit tests for Supertrend + paper-trade simulation (no network)."""

from __future__ import annotations

import unittest
from datetime import datetime, timedelta
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from historical_supertrend_paper import (  # noqa: E402
    Candle,
    compute_supertrend,
    simulate_paper_trades,
    summarize_trades,
)


def _series(prices: list[tuple[float, float, float, float]]) -> list[Candle]:
    """Build candles from (o,h,l,c) tuples starting at a fixed timestamp."""
    start = datetime(2026, 7, 1, 9, 15)
    out: list[Candle] = []
    for i, (o, h, l, c) in enumerate(prices):
        out.append(
            Candle(
                date=start + timedelta(minutes=15 * i),
                open=o,
                high=h,
                low=l,
                close=c,
                volume=100,
            )
        )
    return out


class SupertrendPaperTests(unittest.TestCase):
    def test_supertrend_emits_buy_and_sell_flips(self) -> None:
        # Steady down then sharp up then down again — enough bars for ATR seed.
        down = [(100 - i, 101 - i, 99 - i, 100 - i) for i in range(20)]
        up = [(80 + i, 81 + i, 79 + i, 80 + i) for i in range(20)]
        down2 = [(100 - i, 101 - i, 99 - i, 100 - i) for i in range(20)]
        candles = _series(down + up + down2)
        rows = compute_supertrend(candles, period=10, multiplier=3)
        signals = [r.signal for r in rows if r.signal]
        self.assertIn("BUY", signals)
        self.assertIn("SELL", signals)
        # Every row after warm-up should have a direction.
        warmed = [r for r in rows if r.direction is not None]
        self.assertGreater(len(warmed), 30)

    def test_paper_engine_flips_long_to_short(self) -> None:
        candles = _series(
            [(100, 101, 99, 100)] * 15
            + [(110, 112, 109, 111)] * 5
            + [(100, 101, 95, 96)] * 10
        )
        rows = compute_supertrend(candles, period=10, multiplier=3)
        # Inject explicit signals for engine test (deterministic).
        for r in rows:
            r.signal = None
        rows[20].signal = "BUY"
        rows[25].signal = "SELL"
        rows[28].signal = "BUY"

        trades = simulate_paper_trades(rows, lot_size=100)
        self.assertGreaterEqual(len(trades), 2)
        self.assertEqual(trades[0].side, "BUY")
        self.assertEqual(trades[0].exit_reason, "FLIP_SELL")
        self.assertEqual(trades[1].side, "SELL")
        # points for long: exit - entry
        self.assertAlmostEqual(
            trades[0].points or 0,
            trades[0].exit_price - trades[0].entry_price,
        )
        self.assertAlmostEqual(
            trades[0].pnl or 0,
            (trades[0].points or 0) * 100,
        )

    def test_summary_win_rate(self) -> None:
        candles = _series([(100, 101, 99, 100)] * 20)
        rows = compute_supertrend(candles, period=10, multiplier=3)
        for r in rows:
            r.signal = None
        rows[12].signal = "BUY"
        rows[14].signal = "SELL"  # may be win or loss depending on closes
        trades = simulate_paper_trades(rows, lot_size=1)
        stats = summarize_trades(trades)
        self.assertEqual(stats["total_trades"], len(trades))
        self.assertGreaterEqual(stats["win_rate_pct"], 0.0)
        self.assertLessEqual(stats["win_rate_pct"], 100.0)


if __name__ == "__main__":
    unittest.main()
