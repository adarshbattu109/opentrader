## Summary

<!-- Brief description of what this PR does and why -->

## Changes

<!-- List the key changes made -->

-

## Test Plan

- [ ] `uv run pytest` passes
- [ ] New/changed behavior has a test that fails without the change
- [ ] Linting passes (`uv tool run ruff check . && uv tool run ruff format --check .`)
- [ ] Ran a real backtest if the engine, indicators or ledger changed
- [ ] No secrets, `.env.local`, or `trades/*.csv` committed

## Money Path

- [ ] This PR does **not** change entry/exit logic, fills, stop/target math, or P&L

<!-- If it does, uncheck the box above and fill this in: paste before/after results for all
     three shipped strategies. Every prior backtest number becomes incomparable, so the
     diff in outcomes is the actual review artifact here. -->

## Design Invariants

- [ ] Money stays `Decimal` past the signal boundary (no `Decimal(float)`)
- [ ] Live and backtest still share one `engine.step()` — no logic added to a driver
- [ ] New paths come from `constants/filepaths.py`; new shared numbers from `constants.py`
- [ ] New indicator/operator is registered in a dict, not branched on by type
- [ ] Any new credential uses `require()` and is documented in `.env.example` without a value
- [ ] No real order transmission added (see CONTRIBUTING.md — deferred by phase, not oversight)
