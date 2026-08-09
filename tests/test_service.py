"""Chart payload reshaping. No network -- every DataFrame here is built inline.

chart_payload takes an already-fetched frame, so nothing in this file touches
tvdatafeed. Money is asserted as the exact string the ledger's Decimal produced:
the whole point of the string boundary is that 55.8810 does not become 55.88099.

uv run pytest
"""

from decimal import Decimal

import pandas as pd

from app.service import PANE_TYPES, chart_payload, stop_and_target, to_ts
from opentrader.engine import run, warmup_bars
from opentrader.mock_ledger import MockLedger

FLAT = (931.35, 931.35, 931.35, 931.35)


def _bars(rows):
    """rows = [(open, high, low, close), ...] on a synthetic daily index."""
    return pd.DataFrame(
        rows,
        columns=["open", "high", "low", "close"],
        index=pd.date_range("2026-01-01", periods=len(rows), freq="D"),
    )


def _strat(**overrides):
    """ema1 -> warmup 3, and `close greater 0` is true on every bar.

    So the first eligible bar is index 3 and it always enters there: entry price
    is that bar's close, which makes the whole bracket computable by hand.
    """
    strat = {
        "name": "t",
        "symbol": "X",
        "exchange": "NSE",
        "indicators": [{"id": "e", "type": "ema", "period": 1}],
        "entry": {"left": "close", "op": "greater", "right": 0},
        "stop_loss_pct": 2.0,
        "risk_reward_ratio": 3.0,
    }
    strat.update(overrides)
    return strat


def _payload(rows, strat=None, interval="1d"):
    """Replay rows through the real engine, then reshape. df is never refetched."""
    strat = strat or _strat()
    df = _bars(rows)
    return df, chart_payload(df, strat, run(df, strat, verbose=False), interval)


# Entry 931.35, sl 2% -> risk 18.6270, stop 912.723, target 987.2310 (rr 3).
STOP_BAR = (931.0, 935.0, 900.0, 905.0)
TARGET_BAR = (931.0, 990.0, 931.0, 950.0)


def test_payload_shape():
    df, p = _payload([FLAT] * 4 + [STOP_BAR])
    for key in ("candles", "indicators", "markers", "trades", "summary"):
        assert key in p, key
    assert len(p["candles"]) == len(df) == 5
    assert p["candles"][0] == {
        "time": to_ts(df.index[0]),
        "open": 931.35,
        "high": 931.35,
        "low": 931.35,
        "close": 931.35,
    }
    assert p["range"]["bars"] == 5


def test_money_stays_an_exact_string_on_a_loss():
    """entry 931.35, stop 2% -> exit 912.723, pnl -18.627. Not -18.626999999."""
    _, p = _payload([FLAT] * 4 + [STOP_BAR])
    (t,) = p["trades"]

    for field in ("entry_price", "exit_price", "stop_loss", "target", "pnl"):
        assert isinstance(t[field], str), f"{field} must cross as a string, got {type(t[field])}"

    assert t["entry_price"] == "931.35"
    assert t["exit_price"] == "912.723"
    assert t["stop_loss"] == "912.723"
    assert t["target"] == "987.2310"
    assert t["pnl"] == "-18.627"
    assert t["exit_reason"] == "stop_loss"
    assert t["won"] is False
    assert isinstance(p["summary"]["net"], str)
    assert p["summary"]["net"] == "-18.627", "net must be exact, not rounded"


def test_money_stays_an_exact_string_on_a_win():
    """Same entry, target leg: 931.35 + 18.6270*3 = 987.2310, pnl 55.8810."""
    _, p = _payload([FLAT] * 4 + [TARGET_BAR])
    (t,) = p["trades"]

    assert t["exit_price"] == "987.2310"
    assert t["pnl"] == "55.8810"
    assert t["exit_reason"] == "target"
    assert t["won"] is True
    assert p["summary"]["net"] == "55.8810"


def test_stop_and_target_round_trips_from_a_stop_exit():
    """Entry 100, sl 2% -> stop 98, risk 2, rr 3 -> target 106."""
    led = MockLedger()
    pos = led.enter("X", pd.Timestamp("2026-01-01"), 100.0, 2.0, 3.0)
    trade = led.exit("X", pd.Timestamp("2026-01-02"), pos.stop_loss, "stop_loss")

    stop, target = stop_and_target(trade, Decimal("3.0"))

    assert stop == Decimal("98"), stop
    assert target == Decimal("106"), target
    assert (stop, target) == (pos.stop_loss, pos.target), "must rebuild what the ledger set"


def test_stop_and_target_round_trips_from_a_target_exit():
    """The other leg: exit price is the target, stop follows from the ratio."""
    led = MockLedger()
    pos = led.enter("X", pd.Timestamp("2026-01-01"), 100.0, 2.0, 3.0)
    trade = led.exit("X", pd.Timestamp("2026-01-02"), pos.target, "target")

    stop, target = stop_and_target(trade, Decimal("3.0"))

    assert stop == Decimal("98"), stop
    assert target == Decimal("106"), target
    assert (stop, target) == (pos.stop_loss, pos.target), "must rebuild what the ledger set"


def test_rsi_gets_its_own_pane_and_ema_does_not():
    """RSI is 0-100, so it cannot share the price axis."""
    assert set(PANE_TYPES) == {"rsi"}
    strat = _strat(
        indicators=[
            {"id": "rsi14", "type": "rsi", "period": 14},
            {"id": "ema2", "type": "ema", "period": 2},
        ]
    )
    df = _bars([(100 + i, 101 + i, 99 + i, 100 + i) for i in range(10)])
    p = chart_payload(df, strat, MockLedger(), "15m")

    panes = {ind["id"]: ind["pane"] for ind in p["indicators"]}
    assert panes == {"rsi14": True, "ema2": False}


def test_warmup_boundary_is_the_last_bar_the_engine_skipped():
    """The shroud must end where trading starts.

    engine.run() loops range(warmup, len(df)), so bar `warmup` is the first
    tradeable bar. The boundary is the bar before it -- shading up to and
    including bar `warmup` would grey out a bar the engine actually traded.
    """
    strat = _strat()
    df, p = _payload([FLAT] * 4 + [STOP_BAR], strat)

    assert p["warmup"]["bars"] == warmup_bars(strat) == 3
    assert p["warmup"]["time"] == to_ts(df.index[2]), "boundary = last skipped bar"
    assert p["warmup"]["time"] < to_ts(df.index[3]), "first traded bar is outside the shroud"


def test_straddled_bar_is_flagged_and_books_the_loss():
    """low <= stop and high >= target: the conservative rule decided this one."""
    # stop 912.723, target 987.2310 -- this bar's 900..990 range covers both.
    _, p = _payload([FLAT] * 4 + [(930.0, 990.0, 900.0, 950.0)])
    (t,) = p["trades"]

    assert t["straddle"] is True
    assert t["exit_reason"] == "stop_loss", "conservative read: loss wins"
    assert t["pnl"] == "-18.627"

    exit_marker = [m for m in p["markers"] if m["kind"] == "stop_loss"]
    assert exit_marker and exit_marker[0]["straddle"] is True


def test_a_clean_bar_is_not_flagged_as_a_straddle():
    _, p = _payload([FLAT] * 4 + [TARGET_BAR])
    (t,) = p["trades"]
    assert t["straddle"] is False


def test_nan_indicator_values_are_dropped_not_emitted_as_null():
    """RSI's first bar is NaN (diff). The chart must not receive a null there."""
    strat = _strat(indicators=[{"id": "rsi14", "type": "rsi", "period": 14}])
    df = _bars([(100 + i, 101 + i, 99 + i, 100 + i) for i in range(10)])
    p = chart_payload(df, strat, MockLedger(), "1d")

    (rsi,) = p["indicators"]
    assert len(rsi["data"]) == len(df) - 1, "the NaN bar is dropped, not nulled"
    assert all(point["value"] is not None for point in rsi["data"])
    assert rsi["data"][0]["time"] == to_ts(df.index[1])


def test_summary_counts_and_net_are_exact():
    """Two closed (one win, one loss) plus one still open."""
    df, p = _payload(
        [FLAT] * 4
        + [
            TARGET_BAR,  # target: +55.8810
            (1000.0, 1000.0, 1000.0, 1000.0),  # re-enter at 1000, stop 980
            (990.0, 995.0, 900.0, 950.0),  # stop: -20.00
            (500.0, 500.0, 500.0, 500.0),  # re-enter, never closes
        ]
    )

    assert p["summary"] == {"closed": 2, "wins": 1, "losses": 1, "net": "35.8810", "open": 1}
    assert [t["pnl"] for t in p["trades"]] == ["55.8810", "-20.00"]
    assert [t["won"] for t in p["trades"]] == [True, False]


def test_open_position_is_reported_and_gets_an_entry_marker():
    """A position the run never closed still has to render."""
    df, p = _payload([FLAT] * 6)

    assert p["trades"] == []
    assert p["summary"]["open"] == 1
    (pos,) = p["open"]
    assert pos == {
        "entry_time": to_ts(df.index[3]),
        "entry_price": "931.35",
        "stop_loss": "912.723",
        "target": "987.2310",
    }
    for field in ("entry_price", "stop_loss", "target"):
        assert isinstance(pos[field], str), field

    (marker,) = p["markers"]
    assert marker["kind"] == "entry"
    assert marker["time"] == to_ts(df.index[3])


def test_closed_trade_emits_both_markers():
    df, p = _payload([FLAT] * 4 + [STOP_BAR])
    kinds = [m["kind"] for m in p["markers"]]
    assert kinds == ["entry", "stop_loss"]
    assert [m["time"] for m in p["markers"]] == [to_ts(df.index[3]), to_ts(df.index[4])]


def test_ts_localises_naive_stamps_to_utc():
    """tvdatafeed stamps are naive exchange-local; the wall clock must not shift."""
    assert to_ts(pd.Timestamp("2026-01-01 00:00:00")) == 1767225600
    assert to_ts(pd.Timestamp("2026-01-01 00:00:00", tz="UTC")) == 1767225600


def test_strategy_block_echoes_the_request():
    _, p = _payload([FLAT] * 4 + [STOP_BAR], _strat(), interval="15m")
    assert p["strategy"] == {
        "name": "t",
        "symbol": "X",
        "exchange": "NSE",
        "interval": "15m",
        "entry": "close greater 0",
        "stop_loss_pct": 2.0,
        "risk_reward_ratio": 3.0,
    }


def test_duplicate_exit_timestamp_does_not_crash():
    """A repeated stamp makes .loc return a DataFrame, not a row.

    tvdatafeed can hand back a frame with a duplicated timestamp. Indexing it
    with .loc then yields two rows, and float() on a Series raises -- which
    would take down the whole endpoint over one malformed bar.
    """
    strat = _strat()
    df = _bars([FLAT] * 4 + [STOP_BAR])
    df.index = [*df.index[:4], df.index[3]]  # exit stamp now collides with entry

    p = chart_payload(df, strat, run(df, strat, verbose=False), "1d")

    assert p["summary"]["closed"] == 1
    assert p["trades"][0]["exit_reason"] == "stop_loss"


def test_every_marker_has_the_same_keys():
    """A consumer reading marker.straddle must never get undefined."""
    _, p = _payload([FLAT] * 4 + [STOP_BAR] + [FLAT] * 2)

    assert len(p["markers"]) >= 3, "entry + exit + the still-open re-entry"
    shape = {"time", "kind", "won", "straddle", "text"}
    for m in p["markers"]:
        assert set(m) == shape, f"{m['kind']} marker shape drifted: {sorted(m)}"
