"""Backtest driver: tvdatafeed replay -> engine.run() -> CSV trade log (§4 step 3).

uv run python -m opentrader.backtest strategies/ema_cross.json
uv run python -m opentrader.backtest strategies/ema_cross.json --interval 15m --bars 2000
"""

import argparse
from decimal import Decimal
from pathlib import Path

from tvDatafeed import Interval, TvDatafeed

from constants.constants import INTERVALS
from constants.filepaths import trade_log

from .engine import load_strategy, run


def _interval(name: str) -> Interval:
    return getattr(Interval, INTERVALS[name])


def fetch(symbol: str, exchange: str, interval: str, bars: int):
    df = TvDatafeed().get_hist(
        symbol=symbol, exchange=exchange, interval=_interval(interval), n_bars=bars
    )
    if df is None or df.empty:
        raise SystemExit(f"no data for {exchange}:{symbol} @ {interval}")
    return df


def main() -> None:
    p = argparse.ArgumentParser(description="Backtest one strategy JSON.")
    p.add_argument("strategy", help="path to a strategy JSON file")
    p.add_argument("--interval", default="1d", choices=INTERVALS)
    p.add_argument("--bars", type=int, default=500)
    p.add_argument("--out", default=None, help="CSV path (default trades/<name>.csv)")
    args = p.parse_args()

    strat = load_strategy(args.strategy)
    df = fetch(strat["symbol"], strat["exchange"], args.interval, args.bars)
    print(f"{strat['name']}: {len(df)} bars, {df.index[0]} -> {df.index[-1]}\n")

    ledger = run(df, strat)

    out = Path(args.out) if args.out else trade_log(strat["name"])
    ledger.to_csv(out)

    wins = [t for t in ledger.closed if t.pnl > 0]
    net = sum((t.pnl for t in ledger.closed), Decimal(0))
    print(
        f"\n{len(ledger.closed)} closed, {len(wins)} wins, net {net:.2f} "
        f"({len(ledger.open)} still open) -> {out}"
    )


if __name__ == "__main__":
    main()
