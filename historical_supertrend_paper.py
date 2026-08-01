#!/usr/bin/env python3
"""
Step 5 — Historical Supertrend paper trading (15-minute candles).

Instrument : config.TRADING_SYMBOL (default CRUDEOIL26AUGFUT)
Timeframe  : 15-minute OHLC
Indicator  : Supertrend (10, 3)
Mode       : Paper trading only — no Kite order APIs

Outputs (project root):
  supertrend_signals.csv
  paper_trades.csv
  paper_trading_summary.txt
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Iterable, Literal, Sequence

from dotenv import load_dotenv
from kiteconnect import KiteConnect

import config
from crude_oil_selector import resolve_contract

ROOT = Path(__file__).resolve().parent
ACCESS_TOKEN_FILE = ROOT / "access_token.txt"
SESSION_FILE = ROOT / ".kite_session.json"

INTERVAL = "15minute"
ST_PERIOD = 10
ST_MULTIPLIER = 3.0
DEFAULT_LOOKBACK_DAYS = 60

SIGNALS_FILE = ROOT / "supertrend_signals.csv"
TRADES_FILE = ROOT / "paper_trades.csv"
SUMMARY_FILE = ROOT / "paper_trading_summary.txt"

Direction = Literal["bullish", "bearish"]
Side = Literal["BUY", "SELL"]


# ---------------------------------------------------------------------------
# Credentials / Kite client
# ---------------------------------------------------------------------------
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


def make_kite() -> KiteConnect:
    kite = KiteConnect(api_key=load_api_key())
    kite.set_access_token(load_access_token())
    return kite


# ---------------------------------------------------------------------------
# Supertrend (10, 3) — Wilder ATR
# ---------------------------------------------------------------------------
@dataclass
class Candle:
    date: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float = 0.0
    oi: float | None = None


@dataclass
class CandleST(Candle):
    atr: float | None = None
    supertrend: float | None = None
    direction: Direction | None = None
    signal: Side | None = None


def true_range(high: float, low: float, prev_close: float) -> float:
    return max(high - low, abs(high - prev_close), abs(low - prev_close))


def compute_supertrend(
    candles: Sequence[Candle],
    period: int = ST_PERIOD,
    multiplier: float = ST_MULTIPLIER,
) -> list[CandleST]:
    """
    Classic Supertrend using Wilder's ATR.

    direction:
      bullish → price above Supertrend (support)
      bearish → price below Supertrend (resistance)

    signal on completed candle close:
      BUY  when direction flips bearish → bullish
      SELL when direction flips bullish → bearish
    """
    if period < 1:
        raise ValueError("period must be >= 1")
    if not candles:
        return []

    n = len(candles)
    highs = [c.high for c in candles]
    lows = [c.low for c in candles]
    closes = [c.close for c in candles]

    tr = [0.0] * n
    atr = [None] * n  # type: list[float | None]
    basic_ub = [0.0] * n
    basic_lb = [0.0] * n
    final_ub = [0.0] * n
    final_lb = [0.0] * n
    st = [None] * n  # type: list[float | None]
    direction: list[Direction | None] = [None] * n

    tr[0] = highs[0] - lows[0]
    for i in range(1, n):
        tr[i] = true_range(highs[i], lows[i], closes[i - 1])

    if n >= period:
        seed = sum(tr[0:period]) / period
        atr[period - 1] = seed
        for i in range(period, n):
            prev = atr[i - 1]
            assert prev is not None
            atr[i] = ((prev * (period - 1)) + tr[i]) / period

    for i in range(n):
        if atr[i] is None:
            continue
        mid = (highs[i] + lows[i]) / 2.0
        basic_ub[i] = mid + multiplier * atr[i]
        basic_lb[i] = mid - multiplier * atr[i]

        if i == period - 1:
            final_ub[i] = basic_ub[i]
            final_lb[i] = basic_lb[i]
        else:
            prev_fub = final_ub[i - 1]
            prev_flb = final_lb[i - 1]
            final_ub[i] = (
                basic_ub[i]
                if (basic_ub[i] < prev_fub or closes[i - 1] > prev_fub)
                else prev_fub
            )
            final_lb[i] = (
                basic_lb[i]
                if (basic_lb[i] > prev_flb or closes[i - 1] < prev_flb)
                else prev_flb
            )

        if i == period - 1:
            if closes[i] <= final_ub[i]:
                st[i] = final_ub[i]
                direction[i] = "bearish"
            else:
                st[i] = final_lb[i]
                direction[i] = "bullish"
            continue

        prev_st = st[i - 1]
        prev_dir = direction[i - 1]
        if prev_st is None or prev_dir is None:
            continue

        if prev_dir == "bullish":
            if closes[i] < final_lb[i]:
                st[i] = final_ub[i]
                direction[i] = "bearish"
            else:
                st[i] = final_lb[i]
                direction[i] = "bullish"
        else:  # bearish
            if closes[i] > final_ub[i]:
                st[i] = final_lb[i]
                direction[i] = "bullish"
            else:
                st[i] = final_ub[i]
                direction[i] = "bearish"

    rows: list[CandleST] = []
    for i, c in enumerate(candles):
        signal: Side | None = None
        if i > 0 and direction[i] and direction[i - 1] and direction[i] != direction[i - 1]:
            signal = "BUY" if direction[i] == "bullish" else "SELL"
        rows.append(
            CandleST(
                date=c.date,
                open=c.open,
                high=c.high,
                low=c.low,
                close=c.close,
                volume=c.volume,
                oi=c.oi,
                atr=atr[i],
                supertrend=st[i],
                direction=direction[i],
                signal=signal,
            )
        )
    return rows


# ---------------------------------------------------------------------------
# Paper trading engine
# ---------------------------------------------------------------------------
@dataclass
class PaperTrade:
    trade_id: int
    side: Side  # direction of the open position: BUY=LONG, SELL=SHORT
    entry_time: datetime
    entry_price: float
    exit_time: datetime | None = None
    exit_price: float | None = None
    points: float | None = None
    pnl: float | None = None
    exit_reason: str | None = None


def simulate_paper_trades(
    rows: Sequence[CandleST],
    *,
    lot_size: int,
) -> list[PaperTrade]:
    """
    No position → BUY opens LONG
    LONG → SELL closes LONG and opens SHORT
    SHORT → BUY closes SHORT and opens LONG
    Open position at end is closed at the last candle close (marked EOD_CLOSE).
    """
    trades: list[PaperTrade] = []
    open_trade: PaperTrade | None = None
    next_id = 1

    def close_open(exit_time: datetime, exit_price: float, reason: str) -> None:
        nonlocal open_trade
        if open_trade is None:
            return
        if open_trade.side == "BUY":
            points = exit_price - open_trade.entry_price
        else:
            points = open_trade.entry_price - exit_price
        open_trade.exit_time = exit_time
        open_trade.exit_price = exit_price
        open_trade.points = points
        open_trade.pnl = points * lot_size
        open_trade.exit_reason = reason
        trades.append(open_trade)
        open_trade = None

    for row in rows:
        if not row.signal:
            continue
        price = float(row.close)
        ts = row.date

        if open_trade is None:
            open_trade = PaperTrade(
                trade_id=next_id,
                side=row.signal,
                entry_time=ts,
                entry_price=price,
            )
            next_id += 1
            continue

        if row.signal == open_trade.side:
            # Same-side signal while already in that direction — ignore.
            continue

        # Flip: close current, open opposite.
        close_open(ts, price, f"FLIP_{row.signal}")
        open_trade = PaperTrade(
            trade_id=next_id,
            side=row.signal,
            entry_time=ts,
            entry_price=price,
        )
        next_id += 1

    if open_trade is not None and rows:
        last = rows[-1]
        close_open(last.date, float(last.close), "EOD_CLOSE")

    return trades


def summarize_trades(trades: Sequence[PaperTrade]) -> dict:
    closed = [t for t in trades if t.pnl is not None]
    wins = [t for t in closed if (t.pnl or 0) > 0]
    losses = [t for t in closed if (t.pnl or 0) < 0]
    flats = [t for t in closed if (t.pnl or 0) == 0]
    net = sum(t.pnl or 0 for t in closed)
    return {
        "total_trades": len(closed),
        "wins": len(wins),
        "losses": len(losses),
        "flats": len(flats),
        "win_rate_pct": (len(wins) / len(closed) * 100.0) if closed else 0.0,
        "net_pnl": net,
        "gross_profit": sum(t.pnl or 0 for t in wins),
        "gross_loss": sum(t.pnl or 0 for t in losses),
    }


# ---------------------------------------------------------------------------
# Historical download
# ---------------------------------------------------------------------------
def candles_from_kite_records(records: Iterable[dict]) -> list[Candle]:
    out: list[Candle] = []
    for r in records:
        out.append(
            Candle(
                date=r["date"] if isinstance(r["date"], datetime) else datetime.fromisoformat(str(r["date"])),
                open=float(r["open"]),
                high=float(r["high"]),
                low=float(r["low"]),
                close=float(r["close"]),
                volume=float(r.get("volume") or 0),
                oi=float(r["oi"]) if r.get("oi") is not None else None,
            )
        )
    out.sort(key=lambda c: c.date)
    return out


def fetch_historical_15m(
    kite: KiteConnect,
    instrument_token: int,
    from_dt: datetime,
    to_dt: datetime,
) -> list[Candle]:
    """
    Download 15-minute candles. Kite limits range per request for intraday
    intervals, so fetch in ~60-day chunks and merge.
    """
    chunk_days = 60
    cursor = from_dt
    all_records: list[dict] = []

    while cursor < to_dt:
        chunk_end = min(cursor + timedelta(days=chunk_days), to_dt)
        print(
            f"  Fetching {cursor:%Y-%m-%d} → {chunk_end:%Y-%m-%d} ({INTERVAL})..."
        )
        records = kite.historical_data(
            instrument_token,
            cursor,
            chunk_end,
            INTERVAL,
            continuous=False,
            oi=True,
        )
        all_records.extend(records)
        cursor = chunk_end + timedelta(seconds=1)

    # De-duplicate by timestamp
    by_ts: dict[datetime, dict] = {}
    for r in all_records:
        ts = r["date"]
        by_ts[ts] = r
    ordered = [by_ts[k] for k in sorted(by_ts)]
    return candles_from_kite_records(ordered)


# ---------------------------------------------------------------------------
# Output writers
# ---------------------------------------------------------------------------
def write_signals_csv(path: Path, rows: Sequence[CandleST], symbol: str) -> None:
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(
            [
                "datetime",
                "symbol",
                "open",
                "high",
                "low",
                "close",
                "volume",
                "atr",
                "supertrend",
                "direction",
                "signal",
            ]
        )
        for r in rows:
            writer.writerow(
                [
                    r.date.isoformat(),
                    symbol,
                    r.open,
                    r.high,
                    r.low,
                    r.close,
                    r.volume,
                    "" if r.atr is None else round(r.atr, 4),
                    "" if r.supertrend is None else round(r.supertrend, 4),
                    r.direction or "",
                    r.signal or "",
                ]
            )


def write_trades_csv(path: Path, trades: Sequence[PaperTrade], symbol: str, lot_size: int) -> None:
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(
            [
                "trade_id",
                "symbol",
                "side",
                "position",
                "entry_time",
                "entry_price",
                "exit_time",
                "exit_price",
                "points",
                "lot_size",
                "pnl",
                "exit_reason",
            ]
        )
        for t in trades:
            writer.writerow(
                [
                    t.trade_id,
                    symbol,
                    t.side,
                    "LONG" if t.side == "BUY" else "SHORT",
                    t.entry_time.isoformat(),
                    t.entry_price,
                    "" if t.exit_time is None else t.exit_time.isoformat(),
                    "" if t.exit_price is None else t.exit_price,
                    "" if t.points is None else round(t.points, 4),
                    lot_size,
                    "" if t.pnl is None else round(t.pnl, 4),
                    t.exit_reason or "",
                ]
            )


def write_summary(
    path: Path,
    *,
    symbol: str,
    token: int,
    lot_size: int,
    from_dt: datetime,
    to_dt: datetime,
    candle_count: int,
    signal_count: int,
    trades: Sequence[PaperTrade],
    stats: dict,
) -> None:
    lines = [
        "Historical Supertrend Paper Trading Summary",
        "==========================================",
        "",
        f"Symbol              : {symbol}",
        f"Instrument token    : {token}",
        f"Interval            : {INTERVAL}",
        f"Supertrend          : ({ST_PERIOD}, {ST_MULTIPLIER:g})",
        f"Lot size            : {lot_size}",
        f"From                : {from_dt.isoformat()}",
        f"To                  : {to_dt.isoformat()}",
        f"Candles             : {candle_count}",
        f"Signals (BUY/SELL)  : {signal_count}",
        "",
        f"Total trades        : {stats['total_trades']}",
        f"Wins                : {stats['wins']}",
        f"Losses              : {stats['losses']}",
        f"Flats               : {stats['flats']}",
        f"Win rate            : {stats['win_rate_pct']:.2f}%",
        f"Gross profit        : {stats['gross_profit']:.2f}",
        f"Gross loss          : {stats['gross_loss']:.2f}",
        f"Net paper P&L       : {stats['net_pnl']:.2f}",
        "",
        "Notes:",
        "- Paper trading only. No real orders were placed.",
        "- Entry/exit prices use the close of the completed 15-minute signal candle.",
        "- Any open position at the end of the series is closed at the last candle (EOD_CLOSE).",
        "- P&L = points × lot_size (from the instrument master).",
        "",
    ]
    if trades:
        lines.append("Trade log (brief):")
        for t in trades:
            lines.append(
                f"  #{t.trade_id} {t.side:4} "
                f"{t.entry_price} → {t.exit_price} "
                f"pts={t.points} pnl={t.pnl} ({t.exit_reason})"
            )
        lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Historical Supertrend (10,3) paper trading on 15-minute candles"
    )
    parser.add_argument(
        "--days",
        type=int,
        default=DEFAULT_LOOKBACK_DAYS,
        help=f"Lookback days ending now (default {DEFAULT_LOOKBACK_DAYS})",
    )
    parser.add_argument("--from", dest="from_date", help="Start date YYYY-MM-DD")
    parser.add_argument("--to", dest="to_date", help="End date YYYY-MM-DD")
    parser.add_argument(
        "--csv-candles",
        help="Optional local candles CSV (datetime,open,high,low,close[,volume]) "
        "to run without calling Kite historical API",
    )
    return parser.parse_args(argv)


def load_candles_csv(path: Path) -> list[Candle]:
    rows: list[Candle] = []
    with path.open(encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        for r in reader:
            ts = r.get("datetime") or r.get("date")
            if not ts:
                continue
            rows.append(
                Candle(
                    date=datetime.fromisoformat(ts.replace("Z", "+00:00")),
                    open=float(r["open"]),
                    high=float(r["high"]),
                    low=float(r["low"]),
                    close=float(r["close"]),
                    volume=float(r["volume"]) if r.get("volume") else 0.0,
                )
            )
    rows.sort(key=lambda c: c.date)
    return rows


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)

    symbol = config.TRADING_SYMBOL
    print("========================================")
    print("HISTORICAL SUPERTREND PAPER TRADING")
    print("========================================")
    print(f"Symbol     : {symbol}")
    print(f"Interval   : {INTERVAL}")
    print(f"Supertrend : ({ST_PERIOD}, {ST_MULTIPLIER:g})")
    print("Orders     : DISABLED (paper only)")
    print("========================================")
    print()

    if args.csv_candles:
        print(f"Loading candles from {args.csv_candles}...")
        candles = load_candles_csv(Path(args.csv_candles))
        # Resolve contract metadata when possible; fall back for offline runs.
        try:
            contract = resolve_contract()
            token = contract.instrument_token
            lot_size = int(contract.lot_size)
            symbol = contract.tradingsymbol
        except Exception:
            token = 0
            lot_size = 1
        from_dt = candles[0].date if candles else datetime.now()
        to_dt = candles[-1].date if candles else datetime.now()
    else:
        print(f"Resolving contract {symbol!r}...")
        contract = resolve_contract()
        token = int(contract.instrument_token)
        lot_size = int(contract.lot_size)
        symbol = contract.tradingsymbol
        print(f"  token={token}  expiry={contract.expiry}  lot_size={lot_size}")

        to_dt = (
            datetime.strptime(args.to_date, "%Y-%m-%d")
            if args.to_date
            else datetime.now()
        )
        from_dt = (
            datetime.strptime(args.from_date, "%Y-%m-%d")
            if args.from_date
            else to_dt - timedelta(days=args.days)
        )

        kite = make_kite()
        print("Downloading historical 15-minute candles...")
        candles = fetch_historical_15m(kite, token, from_dt, to_dt)

    if len(candles) < ST_PERIOD + 2:
        raise RuntimeError(
            f"Not enough candles ({len(candles)}) to compute Supertrend({ST_PERIOD})."
        )

    print(f"Candles loaded: {len(candles)}")
    print("Computing Supertrend and simulating paper trades...")
    rows = compute_supertrend(candles, ST_PERIOD, ST_MULTIPLIER)
    signals = [r for r in rows if r.signal]
    trades = simulate_paper_trades(rows, lot_size=lot_size)
    stats = summarize_trades(trades)

    write_signals_csv(SIGNALS_FILE, rows, symbol)
    write_trades_csv(TRADES_FILE, trades, symbol, lot_size)
    write_summary(
        SUMMARY_FILE,
        symbol=symbol,
        token=token,
        lot_size=lot_size,
        from_dt=from_dt,
        to_dt=to_dt,
        candle_count=len(candles),
        signal_count=len(signals),
        trades=trades,
        stats=stats,
    )

    print()
    print("Done (paper trading only — no real orders).")
    print(f"  Signals file : {SIGNALS_FILE.name} ({len(signals)} BUY/SELL marks)")
    print(f"  Trades file  : {TRADES_FILE.name} ({stats['total_trades']} trades)")
    print(f"  Summary file : {SUMMARY_FILE.name}")
    print(f"  Win rate     : {stats['win_rate_pct']:.2f}%")
    print(f"  Net paper P&L: {stats['net_pnl']:.2f}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:  # noqa: BLE001
        print(f"Historical paper trading failed: {exc}", file=sys.stderr)
        raise SystemExit(1)
