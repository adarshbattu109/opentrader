# Contributing to OpenTrader

Thanks for considering a contribution. This document covers the process and the conventions
that are specific to a codebase that computes money.

Read [SECURITY.md](SECURITY.md) before touching anything on the order path — several
"simplifications" in this repo are deliberate correctness guarantees, and reversing one is a
breaking change even when it makes the code shorter.

## Getting Started

```bash
git clone https://github.com/adarshbattu109/opentrader.git
cd opentrader
uv sync
cp .env.example .env.local     # only needed for --source dhan
```

Backtesting needs no credentials. `tvdatafeed` reads public data anonymously, so you can run
the full suite and every shipped strategy on a fresh clone.

## Development Workflow

1. Create a branch from `main`
2. Make your changes
3. Run the checks (below)
4. Open a pull request with a [conventional commit](https://www.conventionalcommits.org/) title

PR titles are validated by CI (`feat:`, `fix:`, `docs:`, `refactor:`, `test:`, `chore:`, …) and
drive the version bump.

## Running Checks

```bash
uv run pytest                                   # no network, under a second
uv tool run ruff check .
uv tool run ruff format --check .

# Manually, against real data
uv run opentrader backtest strategies/ema_cross.json
uv run opentrader live strategies/ema_cross.json --once
uv run opentrader serve         # then click a few trades in the chart
```

## Test Conventions

Tests live in `tests/` and run under pytest.

- **No network in tests.** Every test builds its bars inline or uses `tmp_path`. A test that
  needs `tvdatafeed` or a broker token will not run in CI, and a flaky data source makes the
  suite useless as a signal.
- **Assert the actual number.** `assert trade["pnl"] == Decimal("-18.627")` catches a broken
  stop calculation; `assert trade["pnl"] < 0` does not.
- **Test observable behavior** — return values, raised exceptions, the contents of the closed
  trade — not internal attributes.
- **Money assertions use `Decimal`**, never a float tolerance. If a test needs
  `pytest.approx` on a price, the code under test has a float leak.

New behavior on the money path needs a test that fails without the change. The bar for
indicator math or a CLI flag is lower; use judgment.

### Tests that exist to protect the design

Some tests are not about a function, they are about the premise of the project:

- `test_live_uses_the_same_step_function` — asserts `live_paper.step is engine.step`. If the
  live runner ever grows its own copy of the evaluation logic, backtest and live have drifted
  and the whole design has failed. Don't "fix" this test by making it more permissive.
- `test_three_distinct_strategies_exist` — asserts the repo still proves strategies-as-data
  with genuinely different files, not three variations of one.
- Ambiguous-bar and warmup tests — see SECURITY.md for why these are security tests.

## Code Style

- **Formatter:** Ruff
- **Line length:** 100 characters
- **Target:** Python 3.14
- **Type hints:** Required on public functions
- **Docstrings:** One-line summary on modules and public functions
- **Comments:** Only when the "why" is non-obvious
- **`ponytail:` comments:** Mark a deliberate simplification with its ceiling and upgrade path,
  e.g. `# ponytail: no cost model, add before sizing anything off this P&L`

## Project Conventions

These are load-bearing. Follow them rather than the habit they replace.

- **Paths come from `constants/filepaths.py`**, which resolves everything from a single
  repo-root anchor. Do not write `Path(__file__).resolve().parent...` in a new module, and do
  not build a path by string-joining onto a directory constant.
- **Constants come from `constants/constants.py`.** If a number appears in two modules, it
  belongs there — `INTERVALS` and the market-hours window already do.
- **Money is `Decimal` from the signal onward.** Indicator math stays in pandas floats; the
  conversion boundary is `to_money()` in `mock_ledger.py`. Never `Decimal(some_float)`.
- **One evaluation function.** `engine.step()` is called by both drivers. A new feature goes
  *into* `step()` or into the data the strategy declares — never into a driver.
- **Three surfaces, one engine.** `src/opentrader/` is the engine and imports neither of the
  others. `src/cli/` (terminal) and `app/` (web) both depend on it, and neither holds strategy
  logic: `cli/prompts.py` builds the argv a flag invocation would have used, and
  `app/service.py` only reshapes a finished result into a chart payload. If you are about to
  put an `if` about entries or exits in either one, it belongs in the engine.
- **Extend by registering, not by branching.** A new indicator is a function plus a dict entry
  in `INDICATORS`; a new operator is a function plus an entry in `OPS` with the same
  `(l_prev, l_cur, r_prev, r_cur)` signature. If you find yourself adding an `if` on indicator
  type, that's the signal you're in the wrong place.
- **The web UI is read-only.** `app/` serves results. It does not place orders, and it does not
  get an endpoint that mutates anything on disk beyond what a CLI backtest already writes.
- **A missing credential exits.** Use `require()`; never default a secret, and never let a
  missing one disable a check.

## Adding a broker adapter

Wanted, with one hard rule: **a data adapter may read, but this project does not transmit
orders.** Return an OHLC frame with the same columns as the `tv` source so the engine cannot
tell adapters apart, keep credentials in `.env.local` via `require()`, and read the SEBI
section of [SECURITY.md](SECURITY.md) first. A PR that adds live order placement will not be
merged in this phase — see the phased plan in `docs/OpenTrader_Design.md`.

## Pull Request Guidelines

- Keep PRs focused — one logical change per PR
- Include a test for new behavior on the money path
- Ensure CI passes before requesting review
- Never commit `.env.local`, `trades/`, or `src/logs/`
- If you change how P&L is computed, say so explicitly in the PR body — every prior result
  becomes incomparable

## Changing the Engine

`step()` in `src/opentrader/engine.py` decides every entry and exit, and its bar-level ordering
(stop, then target, then entry) is the calibration knob for how pessimistic the backtest is.
Changing that order changes every historical result this project has produced. If you have a
reason to, make it a standalone PR with the before/after numbers for all three shipped
strategies in the description.
