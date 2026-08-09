"""Checks for the live paper driver's own logic -- no network, no broker.

The evaluation logic itself is covered by test_engine.py; live_paper reuses it
verbatim, which is exactly what test_live_uses_the_same_step_function pins down.
"""

from datetime import datetime
from zoneinfo import ZoneInfo

import pandas as pd

from opentrader import engine, live_paper
from opentrader.live_paper import extract_ltp, market_open_now
from opentrader.mock_ledger import MockLedger

IST = ZoneInfo("Asia/Kolkata")


def test_market_hours():
    # 2026-08-10 is a Monday, 2026-08-08 a Saturday.
    assert market_open_now(datetime(2026, 8, 10, 10, 0, tzinfo=IST))
    assert market_open_now(datetime(2026, 8, 10, 9, 15, tzinfo=IST)), "open is inclusive"
    assert market_open_now(datetime(2026, 8, 10, 15, 30, tzinfo=IST)), "close inclusive"
    assert not market_open_now(datetime(2026, 8, 10, 9, 14, tzinfo=IST))
    assert not market_open_now(datetime(2026, 8, 10, 15, 31, tzinfo=IST))
    assert not market_open_now(datetime(2026, 8, 8, 10, 0, tzinfo=IST)), "saturday"
    assert not market_open_now(datetime(2026, 8, 9, 10, 0, tzinfo=IST)), "sunday"


def test_extract_ltp_tolerates_shape():
    assert extract_ltp({"data": {"data": {"NSE_EQ": {"2885": {"last_price": 1325.5}}}}}) == 1325.5
    assert extract_ltp({"data": {"NSE_EQ": {"2885": {"last_price": 10}}}}) == 10.0
    # Garbage in must yield None so the caller falls back, not crash mid-session.
    assert extract_ltp(None) is None
    assert extract_ltp({}) is None
    assert extract_ltp({"data": {"NSE_EQ": {}}}) is None
    assert extract_ltp({"status": "failure", "remarks": "bad token"}) is None


def test_live_uses_the_same_step_function():
    """§5 criterion 2: the live path must not have its own copy of the logic."""
    assert live_paper.step is engine.step
    assert live_paper.compute_indicators is engine.compute_indicators


def test_dhan_source_is_registered():
    assert set(live_paper.SOURCES) == {"tv", "dhan"}


def test_tick_ignores_a_bar_it_has_already_evaluated(tmp_path):
    """Polling faster than the bar interval must not enter twice off one signal.

    Every poll returns the same still-forming last bar until the interval
    rolls over. Without the `seen` guard the second poll re-runs step() on it.
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
    df = pd.DataFrame(
        [(100.0, 100.0, 100.0, 100.0)] * 4,
        columns=["open", "high", "low", "close"],
        index=pd.date_range("2026-01-01", periods=4, freq="D"),
    )
    ledger, seen, log = MockLedger(), set(), tmp_path / "s.log"

    assert live_paper.tick(df, strat, ledger, seen, log) == "entry"
    assert live_paper.tick(df, strat, ledger, seen, log) is None, "same bar must be a no-op"
    assert len(ledger.open) == 1, "one signal, one position"
    assert len(log.read_text().splitlines()) == 1, "the skipped tick logs nothing"
