"""The evaluation loop. Shared verbatim by backtest and live paper (§5 criterion 2).

One function, `step()`, decides what happens on one bar. Backtest feeds it bars
from tvdatafeed replay; live_paper feeds it bars built from polled quotes.
Neither knows which it is.
"""

import json
from decimal import Decimal
from pathlib import Path

import pandas as pd

from . import conditions, indicators
from .mock_ledger import MockLedger

INDICATORS = {"ema": indicators.ema, "rsi": indicators.rsi}
OPS = {
    "crosses_above": conditions.crosses_above,
    "crosses_below": conditions.crosses_below,
    "greater": conditions.greater,
    "less": conditions.less,
}


def load_strategy(path: str | Path) -> dict:
    """Load and sanity-check a §2.3-shaped strategy file.

    Not the v2 Validator -- just enough to fail loudly on a typo instead of
    KeyError-ing 200 bars into a backtest.
    """
    strat = json.loads(Path(path).read_text())
    for field in (
        "name",
        "symbol",
        "exchange",
        "indicators",
        "entry",
        "stop_loss_pct",
        "risk_reward_ratio",
    ):
        if field not in strat:
            raise ValueError(f"strategy missing required field: {field}")

    ids = set()
    for ind in strat["indicators"]:
        if ind["type"] not in INDICATORS:
            raise ValueError(f"unknown indicator type {ind['type']!r}; have {sorted(INDICATORS)}")
        ids.add(ind["id"])

    entry = strat["entry"]
    if entry["op"] not in OPS:
        raise ValueError(f"unknown op {entry['op']!r}; have {sorted(OPS)}")
    for side in ("left", "right"):
        ref = entry[side]
        # A bare number is a valid right-hand side (e.g. rsi greater 70).
        if isinstance(ref, str) and ref not in ids and ref not in ("open", "high", "low", "close"):
            raise ValueError(f"entry.{side}={ref!r} is not an indicator id or a price field")
    return strat


def compute_indicators(df: pd.DataFrame, strat: dict) -> pd.DataFrame:
    """Attach one column per declared indicator. Returns a copy."""
    df = df.copy()
    for ind in strat["indicators"]:
        fn = INDICATORS[ind["type"]]
        df[ind["id"]] = fn(df["close"], ind["period"])
    return df


def warmup_bars(strat: dict) -> int:
    """Bars to skip before an indicator is trustworthy.

    pandas `.ewm()` emits a value from bar 0, so NaN-dropping finds nothing to
    drop -- an "ema50" on bar 3 is really just the price, and a
    close-crosses-ema condition would fire on noise. 3x the longest period is
    the usual convergence rule of thumb for an EMA.
    """
    longest = max(i["period"] for i in strat["indicators"])
    return max(3 * longest, 1)


def _series(df: pd.DataFrame, ref, i: int) -> tuple[float, float]:
    """(previous, current) value of one side of a condition at bar i."""
    if not isinstance(ref, str):
        return float(ref), float(ref)
    return float(df[ref].iloc[i - 1]), float(df[ref].iloc[i])


def step(df: pd.DataFrame, i: int, strat: dict, ledger: MockLedger) -> str | None:
    """Evaluate bar i. Returns the action taken, or None.

    Exit checks run before entry, and stop before target: a bar that gaps
    through both is booked as the loss, which is the conservative read (§2.2 --
    a simple in-order if/elif is the POC's whole exit-protection story).
    """
    bar = df.iloc[i]
    symbol, time = strat["symbol"], df.index[i]

    if symbol in ledger.open:
        pos = ledger.open[symbol]
        if float(bar["low"]) <= float(pos.stop_loss):
            ledger.exit(symbol, time, pos.stop_loss, "stop_loss")
            return "stop_loss"
        if float(bar["high"]) >= float(pos.target):
            ledger.exit(symbol, time, pos.target, "target")
            return "target"
        return None

    entry = strat["entry"]
    l_prev, l_cur = _series(df, entry["left"], i)
    r_prev, r_cur = _series(df, entry["right"], i)
    if OPS[entry["op"]](l_prev, l_cur, r_prev, r_cur):
        ledger.enter(
            symbol,
            time,
            bar["close"],
            strat["stop_loss_pct"],
            strat["risk_reward_ratio"],
        )
        return "entry"
    return None


def fill_price(action: str, strat: dict, ledger: MockLedger) -> Decimal:
    """What an action actually filled at.

    Both drivers print the same "action fill price" line, so the lookup lives
    here rather than being re-derived identically in each.
    """
    if action == "entry":
        return ledger.open[strat["symbol"]].entry_price
    return ledger.closed[-1].exit_price


def run(
    df: pd.DataFrame, strat: dict, ledger: MockLedger | None = None, verbose: bool = True
) -> MockLedger:
    """Replay every bar in df through step(). Skips bars with NaN indicators."""
    ledger = ledger or MockLedger()
    df = compute_indicators(df, strat)
    start = warmup_bars(strat)
    if start >= len(df):
        raise SystemExit(f"need >{start} bars for warmup, got {len(df)}")

    for i in range(start, len(df)):
        action = step(df, i, strat, ledger)
        if action and verbose:
            print(f"{df.index[i]}  {action:<10} fill {fill_price(action, strat, ledger)}")
    return ledger
