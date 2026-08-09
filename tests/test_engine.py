"""Engine logic checks. No network, no fixtures.

uv run pytest
"""

from decimal import Decimal

import pandas as pd
import pytest

from opentrader.engine import OPS, compute_indicators, run, step, warmup_bars
from opentrader.mock_ledger import MockLedger, to_money


def _bars(rows):
    """rows = [(open, high, low, close), ...] on a synthetic daily index."""
    return pd.DataFrame(
        rows,
        columns=["open", "high", "low", "close"],
        index=pd.date_range("2026-01-01", periods=len(rows), freq="D"),
    )


def test_operators():
    assert OPS["crosses_above"](1.0, 3.0, 2.0, 2.0)
    assert not OPS["crosses_above"](3.0, 4.0, 2.0, 2.0), "already above is not a cross"
    assert OPS["crosses_below"](3.0, 1.0, 2.0, 2.0)
    assert OPS["greater"](0.0, 3.0, 0.0, 2.0)
    assert OPS["less"](0.0, 1.0, 0.0, 2.0)


def test_ema_matches_manual():
    got = compute_indicators(
        _bars([(1, 1, 1, 1), (2, 2, 2, 2), (3, 3, 3, 3)]),
        {"indicators": [{"id": "e", "type": "ema", "period": 2}]},
    )["e"]
    # alpha = 2/(2+1); e0=1, e1=1+2/3*(2-1)=1.6667, e2=1.6667+2/3*(3-1.6667)
    assert abs(got.iloc[1] - 1.666667) < 1e-5, got.iloc[1]
    assert abs(got.iloc[2] - 2.555556) < 1e-5, got.iloc[2]


def test_stop_and_target_prices():
    """Entry 100, sl 2% -> stop 98, risk 2, R:R 3 -> target 106."""
    led = MockLedger()
    pos = led.enter("X", pd.Timestamp("2026-01-01"), 100.0, 2.0, 3.0)
    assert pos.stop_loss == Decimal("98.00"), pos.stop_loss
    assert pos.target == Decimal("106.00"), pos.target
    assert isinstance(pos.entry_price, Decimal)


def test_target_exit_fills_at_target_not_close():
    strat = {
        "name": "t",
        "symbol": "X",
        "indicators": [{"id": "e", "type": "ema", "period": 2}],
        "entry": {"left": "close", "op": "greater", "right": 0},
        "stop_loss_pct": 2.0,
        "risk_reward_ratio": 3.0,
    }
    # bar1 enters at close 100; bar2 spikes to 110 (> target 106) and closes at 101.
    df = compute_indicators(
        _bars([(100, 100, 100, 100), (100, 100, 100, 100), (100, 110, 100, 101)]), strat
    )
    led = MockLedger()
    assert step(df, 1, strat, led) == "entry"
    assert step(df, 2, strat, led) == "target"
    t = led.closed[0]
    assert t.exit_price == Decimal("106.00"), t.exit_price
    assert t.pnl == Decimal("6.00"), t.pnl


def test_stop_wins_when_a_bar_hits_both():
    strat = {
        "name": "t",
        "symbol": "X",
        "indicators": [{"id": "e", "type": "ema", "period": 2}],
        "entry": {"left": "close", "op": "greater", "right": 0},
        "stop_loss_pct": 2.0,
        "risk_reward_ratio": 3.0,
    }
    # bar2 range 95..110 straddles both stop (98) and target (106).
    df = compute_indicators(
        _bars([(100, 100, 100, 100), (100, 100, 100, 100), (100, 110, 95, 101)]), strat
    )
    led = MockLedger()
    step(df, 1, strat, led)
    assert step(df, 2, strat, led) == "stop_loss", "conservative read: loss wins"
    assert led.closed[0].pnl == Decimal("-2.00")


def test_no_position_no_entry_while_open():
    strat = {
        "name": "t",
        "symbol": "X",
        "indicators": [{"id": "e", "type": "ema", "period": 2}],
        "entry": {"left": "close", "op": "greater", "right": 0},
        "stop_loss_pct": 50.0,
        "risk_reward_ratio": 99.0,
    }
    df = compute_indicators(_bars([(100, 100, 100, 100)] * 12), strat)
    led = run(df, strat, verbose=False)
    assert len(led.open) == 1 and not led.closed, "one open position, never re-entered"


def test_warmup_skips_unconverged_indicator_bars():
    """ewm() emits from bar 0, so warmup is by count, not NaN-dropping."""
    strat = {
        "name": "t",
        "symbol": "X",
        "indicators": [{"id": "e", "type": "ema", "period": 50}],
        "entry": {"left": "close", "op": "crosses_above", "right": "e"},
        "stop_loss_pct": 1.0,
        "risk_reward_ratio": 4.0,
    }
    assert warmup_bars(strat) == 150
    # 100 bars is under warmup for an ema50 -- must refuse, not silently trade.
    df = _bars([(100, 101, 99, 100)] * 100)
    with pytest.raises(SystemExit):
        run(df, strat, verbose=False)


def test_money_never_binary_floats():
    assert to_money(0.1) + to_money(0.2) == Decimal("0.3")
