"""§4 step 5: same evaluation loop, live data source, orders still mock.

The engine is untouched -- `engine.step` here is the exact function backtest.py
calls. Only where the bars come from changes. That is the whole point of the
POC (§5 criterion 2): if this file needed its own copy of the entry/exit logic,
the design would already have failed.

No order ever reaches an exchange. MockLedger prints and records; that is it.
"""

import argparse
import time
from datetime import datetime
from datetime import time as dtime
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

from constants.constants import MARKET_CLOSE, MARKET_OPEN, TIMEZONE
from constants.filepaths import session_log, trade_log

from .engine import compute_indicators, fill_price, load_strategy, step, warmup_bars
from .mock_ledger import MockLedger

TZ = ZoneInfo(TIMEZONE)


def market_open_now(now: datetime | None = None) -> bool:
    now = now or datetime.now(TZ)
    if now.weekday() >= 5:
        return False
    o_h, o_m = (int(x) for x in MARKET_OPEN.split(":"))
    c_h, c_m = (int(x) for x in MARKET_CLOSE.split(":"))
    return dtime(o_h, o_m) <= now.timetz().replace(tzinfo=None) <= dtime(c_h, c_m)


def bars_tv(strat: dict, interval: str, n: int) -> pd.DataFrame:
    """Poll tvdatafeed. The final row is the still-forming current bar."""
    from .backtest import fetch

    return fetch(strat["symbol"], strat.get("exchange", "NSE"), interval, n)


def bars_dhan(strat: dict, interval: str, n: int) -> pd.DataFrame:
    """Broker LTP as the live price, history warm-started from tvdatafeed.

    Dhan's historical endpoint keys off a numeric security_id, which needs the
    instrument master (design doc §11.9) -- a v1 component. So history comes
    from tvdatafeed (§10.3 endorses warm-starting this way) and only the
    current bar's price comes from the broker.

    ponytail: last-price-only, so the forming bar's high/low are tvdatafeed's.
    Fine for a mock-order POC; build the real Broker Live Feed Adapter at v1
    when fills actually depend on intrabar extremes.
    """
    from dhanhq import DhanContext, dhanhq

    from helpers.env_helpers import require

    ctx = DhanContext(require("DHAN_CLIENT_ID"), require("DHAN_ACCESS_TOKEN"))
    sec_id = require("DHAN_SECURITY_ID")

    df = bars_tv(strat, interval, n)
    resp = dhanhq(ctx).ticker_data(
        securities={"NSE_EQ": [int(sec_id)]},
    )
    ltp = extract_ltp(resp)
    if ltp is None:
        print("  ! dhan returned no LTP, using tvdatafeed close for this tick")
        return df

    i = df.index[-1]
    df.loc[i, "close"] = ltp
    df.loc[i, "high"] = max(df.loc[i, "high"], ltp)
    df.loc[i, "low"] = min(df.loc[i, "low"], ltp)
    return df


def extract_ltp(resp) -> float | None:
    """Dig the last price out of Dhan's nested response without trusting shape."""
    if not isinstance(resp, dict):
        return None
    node = resp.get("data", resp)
    for key in ("data", "NSE_EQ"):
        if isinstance(node, dict) and key in node:
            node = node[key]
    if isinstance(node, dict):
        for v in node.values():
            if isinstance(v, dict) and (p := v.get("last_price")):
                return float(p)
    return None


SOURCES = {"tv": bars_tv, "dhan": bars_dhan}


def tick(df: pd.DataFrame, strat: dict, ledger: MockLedger, seen: set, log: Path) -> str | None:
    """Evaluate the newest bar and record it. Returns the action taken, or None.

    A poll that lands mid-bar returns the same still-forming bar as the last
    one; re-evaluating it would enter twice off one signal. `seen` is what
    makes a tick idempotent per bar.
    """
    ts = df.index[-1]
    if ts in seen:
        return None
    seen.add(ts)

    action = step(df, len(df) - 1, strat, ledger)
    if action:
        print(f"{ts}  {action:<10} fill {fill_price(action, strat, ledger)}")
    with log.open("a") as fh:
        fh.write(
            f"{datetime.now(TZ).isoformat()} bar={ts} "
            f"close={df['close'].iloc[-1]} action={action or '-'} "
            f"open={len(ledger.open)}\n"
        )
    return action


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("strategy")
    p.add_argument("--source", choices=SOURCES, default="tv")
    p.add_argument("--interval", default="5m")
    p.add_argument("--poll", type=int, default=60, help="seconds between polls")
    p.add_argument("--once", action="store_true", help="single tick, ignore hours")
    args = p.parse_args()

    strat = load_strategy(args.strategy)
    get_bars = SOURCES[args.source]
    need = warmup_bars(strat) + 2
    ledger = MockLedger()
    log = session_log(strat["name"])
    seen: set = set()

    print(f"{strat['name']} | {strat['symbol']} {args.interval} | source={args.source}")
    print(f"MOCK ORDERS ONLY -- nothing is sent to an exchange. log -> {log}\n")

    if not args.once and not market_open_now():
        print(f"market closed ({MARKET_OPEN}-{MARKET_CLOSE} IST, Mon-Fri).")
        print("use --once to take a single tick against the last available bar.")
        return

    while True:
        try:
            bars = compute_indicators(get_bars(strat, args.interval, need), strat)
            tick(bars, strat, ledger, seen, log)
        except KeyboardInterrupt:
            raise
        except Exception as exc:
            # A dropped feed must not kill a session holding an open position.
            print(f"  ! poll failed ({type(exc).__name__}: {exc}) -- retrying")

        if args.once:
            break
        if not market_open_now():
            print("\nmarket closed, stopping.")
            break
        time.sleep(args.poll)

    if ledger.closed:
        out = trade_log(strat["name"])
        ledger.to_csv(out)
        print(f"\n{len(ledger.closed)} closed -> {out}")
    print(f"{len(ledger.open)} position(s) still open" if ledger.open else "flat")


if __name__ == "__main__":
    main()
