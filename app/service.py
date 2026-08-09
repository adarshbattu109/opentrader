"""Backtest results -> chart payload. Reshapes only; every decision stays in the engine.

Money crosses this boundary as strings, not floats: the ledger's Decimal values
are exact and JSON floats are not (§18). Chart geometry -- candles, indicator
lines -- is float, because that is pixel positioning, not money.
"""

from decimal import Decimal

import pandas as pd

from opentrader.engine import compute_indicators, warmup_bars
from opentrader.mock_ledger import MockLedger, to_money

# RSI is 0-100, so it cannot share the price axis. Everything else overlays.
PANE_TYPES = {"rsi"}


def to_ts(value) -> int:
    """UTC seconds for lightweight-charts.

    tvdatafeed returns naive stamps already in exchange-local time. Localising
    them to UTC keeps the wall clock the exchange's rather than shifting every
    bar into whatever zone the browser happens to sit in.
    """
    t = pd.Timestamp(value)
    return int((t.tz_localize("UTC") if t.tzinfo is None else t).timestamp())


def _num(value) -> float | None:
    return None if pd.isna(value) else round(float(value), 4)


def stop_and_target(trade, rr: Decimal) -> tuple[Decimal, Decimal]:
    """Recover the bracket from what the ledger recorded.

    Exits fill *at* the stop or the target, so one leg is the exit price itself
    and the other follows from the risk/reward ratio. Derived from facts on the
    trade rather than re-deriving the sizing rule, which lives in
    MockLedger.enter and must not be duplicated here.
    """
    entry = trade.entry_price
    if trade.exit_reason == "stop_loss":
        stop = trade.exit_price
        return stop, entry + (entry - stop) * rr
    target = trade.exit_price
    return entry - (target - entry) / rr, target


def chart_payload(df: pd.DataFrame, strat: dict, ledger: MockLedger, interval: str) -> dict:
    """Everything the browser needs for one run, in one response."""
    withind = compute_indicators(df, strat)
    warmup = warmup_bars(strat)
    rr = to_money(strat["risk_reward_ratio"])

    candles = [
        {
            "time": to_ts(ts),
            "open": _num(row.open),
            "high": _num(row.high),
            "low": _num(row.low),
            "close": _num(row.close),
        }
        for ts, row in withind.iterrows()
    ]

    indicators = []
    for ind in strat["indicators"]:
        series = withind[ind["id"]]
        indicators.append(
            {
                "id": ind["id"],
                "type": ind["type"],
                "period": ind["period"],
                "pane": ind["type"] in PANE_TYPES,
                "data": [
                    {"time": to_ts(ts), "value": v}
                    for ts, val in series.items()
                    if (v := _num(val)) is not None
                ],
            }
        )

    trades, markers = [], []
    for trade in ledger.closed:
        stop, target = stop_and_target(trade, rr)
        bar = withind.loc[trade.exit_time]
        # A repeated stamp makes .loc return a frame, not a row. Take the first
        # rather than letting float() fail on a Series and 500 the endpoint.
        if isinstance(bar, pd.DataFrame):
            bar = bar.iloc[0]
        # A bar whose range covers both legs is where the stop-before-target
        # rule actually decided the outcome. Flag it; a verifier should look.
        straddle = bool(float(bar.low) <= float(stop) and float(bar.high) >= float(target))
        won = trade.pnl > 0
        trades.append(
            {
                "entry_time": to_ts(trade.entry_time),
                "entry_price": str(trade.entry_price),
                "exit_time": to_ts(trade.exit_time),
                "exit_price": str(trade.exit_price),
                "exit_reason": trade.exit_reason,
                "stop_loss": str(stop),
                "target": str(target),
                "pnl": str(trade.pnl),
                "won": won,
                "straddle": straddle,
            }
        )
        markers += [
            {
                "time": to_ts(trade.entry_time),
                "kind": "entry",
                "won": won,
                "straddle": False,
                "text": f"entry {trade.entry_price}",
            },
            {
                "time": to_ts(trade.exit_time),
                "kind": trade.exit_reason,
                "won": won,
                "straddle": straddle,
                "text": f"{trade.exit_reason} {trade.exit_price}",
            },
        ]

    # A position the run never closed still has to render: it gets a row and an
    # entry marker, but no exit and no won/lost verdict.
    still_open = []
    for pos in ledger.open.values():
        still_open.append(
            {
                "entry_time": to_ts(pos.entry_time),
                "entry_price": str(pos.entry_price),
                "stop_loss": str(pos.stop_loss),
                "target": str(pos.target),
            }
        )
        markers.append(
            {
                "time": to_ts(pos.entry_time),
                "kind": "entry",
                "won": None,
                "straddle": False,
                "text": f"entry {pos.entry_price}",
            }
        )

    net = sum((t.pnl for t in ledger.closed), Decimal(0))
    wins = [t for t in ledger.closed if t.pnl > 0]
    return {
        "strategy": {
            "name": strat["name"],
            "symbol": strat["symbol"],
            "exchange": strat["exchange"],
            "interval": interval,
            "entry": f"{strat['entry']['left']} {strat['entry']['op']} {strat['entry']['right']}",
            "stop_loss_pct": strat["stop_loss_pct"],
            "risk_reward_ratio": strat["risk_reward_ratio"],
        },
        "range": {
            "bars": len(candles),
            "from": str(withind.index[0]),
            "to": str(withind.index[-1]),
        },
        # The shroud covers bars the engine refused to trade. engine.run() starts
        # at bar `warmup`, so the boundary is the last skipped bar -- shading up
        # to bar `warmup` itself would grey out the first tradeable bar.
        "warmup": {
            "bars": warmup,
            "time": to_ts(withind.index[min(warmup, len(withind)) - 1]),
        },
        "candles": candles,
        "indicators": indicators,
        "markers": markers,
        "trades": trades,
        "open": still_open,
        "summary": {
            "closed": len(ledger.closed),
            "wins": len(wins),
            "losses": len(ledger.closed) - len(wins),
            # Exact, not quantized: a UI summing the trade column must agree
            # with this to the last decimal. Round at render time, not here.
            "net": str(net),
            "open": len(ledger.open),
        },
    }
