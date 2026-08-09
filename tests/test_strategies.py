"""Strategy loading and validation -- the guard that fails loud on a typo."""

import json

import pytest

from constants.filepaths import STRATEGIES_DIR
from opentrader.engine import load_strategy

SHIPPED = sorted(STRATEGIES_DIR.glob("*.json"))


@pytest.mark.parametrize("path", SHIPPED, ids=lambda p: p.stem)
def test_shipped_strategies_load(path):
    """Every strategy in the repo must parse -- this is the §5 criterion 4 set."""
    strat = load_strategy(path)
    assert strat["indicators"] and strat["entry"]
    assert strat["stop_loss_pct"] > 0 and strat["risk_reward_ratio"] > 0


def test_three_distinct_strategies_exist():
    """§5 criterion 4: 2-3 different files through the same code, untouched."""
    assert len(SHIPPED) >= 3, "need >=3 strategies to prove 'strategies are data'"
    assert len({json.loads(p.read_text())["symbol"] for p in SHIPPED}) >= 2


def _write(tmp_path, **overrides):
    strat = {
        "name": "t",
        "symbol": "X",
        "exchange": "NSE",
        "indicators": [{"id": "ema9", "type": "ema", "period": 9}],
        "entry": {"left": "ema9", "op": "crosses_above", "right": "close"},
        "stop_loss_pct": 1.5,
        "risk_reward_ratio": 3.0,
    }
    strat.update(overrides)
    p = tmp_path / "s.json"
    p.write_text(json.dumps(strat))
    return p


def test_rejects_unknown_indicator(tmp_path):
    bad = _write(tmp_path, indicators=[{"id": "x", "type": "macd", "period": 9}])
    with pytest.raises(ValueError, match="unknown indicator"):
        load_strategy(bad)


def test_rejects_unknown_operator(tmp_path):
    bad = _write(tmp_path, entry={"left": "ema9", "op": "wiggles", "right": "close"})
    with pytest.raises(ValueError, match="unknown op"):
        load_strategy(bad)


def test_rejects_dangling_reference(tmp_path):
    bad = _write(tmp_path, entry={"left": "ema9", "op": "greater", "right": "ema99"})
    with pytest.raises(ValueError, match="not an indicator id"):
        load_strategy(bad)


def test_rejects_missing_field(tmp_path):
    strat = json.loads(_write(tmp_path).read_text())
    del strat["stop_loss_pct"]
    p = tmp_path / "bad.json"
    p.write_text(json.dumps(strat))
    with pytest.raises(ValueError, match="missing required field"):
        load_strategy(p)


def test_numeric_right_hand_side_is_allowed(tmp_path):
    ok = _write(
        tmp_path,
        indicators=[{"id": "rsi14", "type": "rsi", "period": 14}],
        entry={"left": "rsi14", "op": "crosses_above", "right": 30},
    )
    assert load_strategy(ok)["entry"]["right"] == 30
