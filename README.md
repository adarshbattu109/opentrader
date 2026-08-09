# OpenTrader

Algorithmic trading strategies defined as JSON, not code. Write a strategy file, backtest it
against real market data, then run the *same* evaluation code against a live feed — without
touching a line of Python.

> **Status: proof of concept.** Every order is mock. Nothing is sent to an exchange, no broker
> account is debited, and no capital is at risk. See [Scope](#scope-what-this-is-not-yet).

```bash
uv sync
uv run opentrader backtest strategies/ema_cross.json
```

```
ema_cross_poc: 500 bars, 2024-08-13 -> 2026-08-07

2025-01-16 09:15:00  entry      fill 1266.45
2025-01-17 09:15:00  target     fill 1323.440250
2025-02-01 09:15:00  entry      fill 1264.6
2025-02-03 09:15:00  stop_loss  fill 1245.631
...
11 closed, 3 wins, net 17.77 (1 still open) -> trades/ema_cross_poc.csv
```

---

## Why

Backtesting a strategy and running it live are usually two different programs, and they drift.
The one you tested is not the one that trades. OpenTrader's premise is that a strategy is
**data**, and there is exactly one evaluation function — `engine.step()` — that both the
backtester and the live runner call. A test pins this down:

```python
def test_live_uses_the_same_step_function():
    assert live_paper.step is engine.step
```

If that assertion ever fails, the core design has failed with it.

---

## Quickstart

Requires [uv](https://docs.astral.sh/uv/) and Python 3.14.

```bash
git clone https://github.com/adarshbattu109/opentrader.git
cd opentrader
uv sync
```

No credentials needed to backtest — `tvdatafeed` reads public data anonymously.

```bash
# Pick strategy, mode and options from a menu — no flags to remember
uv run opentrader

# Backtest, daily bars, 500 of them
uv run opentrader backtest strategies/ema_cross.json

# Intraday, more history
uv run opentrader backtest strategies/rsi_oversold.json --interval 15m --bars 2000

# One live tick against the most recent bar (works when the market is closed)
uv run opentrader live strategies/ema_cross.json --once

# Poll every 60s during market hours; stops itself at 15:30 IST
uv run opentrader live strategies/ema_cross.json --interval 5m --poll 60

# Chart UI in a browser
uv run opentrader serve
```

Bare `opentrader` opens an interactive picker; it prints the equivalent flag form of whatever
you chose, so the menu teaches the CLI instead of hiding it. `opentrader --help` lists the
subcommands, `opentrader <cmd> --help` lists that subcommand's options. The module form
(`uv run python -m opentrader.backtest ...`) still works and is equivalent — the CLI only
dispatches, it does not parse strategy arguments itself.

Trade logs land in `trades/<name>.csv`, session logs in `src/logs/<name>.log`. Both gitignored.

---

## Writing a strategy

A strategy is a JSON file. This is the whole schema:

```json
{
  "name": "ema_cross_poc",
  "symbol": "RELIANCE",
  "exchange": "NSE",
  "indicators": [
    {"id": "ema9",  "type": "ema", "period": 9},
    {"id": "ema21", "type": "ema", "period": 21}
  ],
  "entry": {"left": "ema9", "op": "crosses_above", "right": "ema21"},
  "stop_loss_pct": 1.5,
  "risk_reward_ratio": 3.0
}
```

| Field | Meaning |
|---|---|
| `indicators[].id` | Name you reference in `entry`. Becomes a column on the bar frame. |
| `indicators[].type` | `ema` or `rsi`. |
| `entry.left` / `.right` | An indicator `id`, a price field (`open`/`high`/`low`/`close`), or a bare number. |
| `entry.op` | `crosses_above`, `crosses_below`, `greater`, `less`. |
| `stop_loss_pct` | Percent below entry. Computed once at entry; never trails. |
| `risk_reward_ratio` | Target distance as a multiple of the stop distance. 3.0 = risk 1 to make 3. |

Unknown indicators, operators and dangling references are rejected at load time with a real
message, not a `KeyError` 200 bars into a run.

Three strategies ship in `strategies/`, deliberately different from each other — an EMA cross,
an RSI threshold using a numeric right-hand side, and a price-vs-EMA state condition. They all
run through the same untouched code, which is what proves the "strategies are data" premise.

### Adding an indicator or operator

Add a plain function and register it in a dict. That's the extension point:

```python
# src/opentrader/indicators.py
def sma(s: pd.Series, period: int) -> pd.Series:
    return s.rolling(period).mean()


# src/opentrader/engine.py
INDICATORS = {"ema": indicators.ema, "rsi": indicators.rsi, "sma": indicators.sma}
```

Operators all take `(l_prev, l_cur, r_prev, r_cur)` so they dispatch through one dict with no
special cases. Point-in-time operators ignore the `_prev` arguments.

---

## How it works

```
strategy.json ──▶ load_strategy()      validate: unknown op/indicator/reference
                        │
bars ──────────▶ compute_indicators()  one column per declared indicator
                        │
                  warmup_bars()        skip 3x the longest period (see below)
                        │
                  step(df, i, ...) ◀── the ONE evaluation function
                        │
                  MockLedger           dict of open positions + list of closed trades
                        │
                  trades/<name>.csv
```

**Exit priority.** A bar is checked for stop, then target, then entry. A bar whose range
straddles both stop and target books the **loss** — the conservative read, since intrabar
sequence is unknowable from OHLC alone.

**Fills are stop/target prices, not bar closes.** Entering at 1241.80 with a 1.5% stop exits at
1223.173, not wherever the bar happened to close.

**Warmup is by bar count, not NaN-dropping.** `pandas.ewm()` emits a value from bar 0, so an
"ema50" on bar 3 is really just the price, and a `close crosses_above ema50` condition would
fire on noise. `run()` skips `3 × longest_period` bars and refuses outright if there aren't
enough. This is the difference between a backtest that looks plausible and one that is.

**Money is `Decimal` from signal onward.** Indicator math stays float/pandas; the moment a
signal becomes an order intent it goes through `to_money()`, which is `Decimal(str(v))` and
never `Decimal(float)`.

---

## Live paper trading

```bash
uv run python -m opentrader.live_paper strategies/ema_cross.json --source tv --once
```

Two data sources:

- **`tv`** (default) — polls `tvdatafeed`. No credentials.
- **`dhan`** — history warm-started from `tvdatafeed`, current price from Dhan's live quote.
  Needs `DHAN_CLIENT_ID`, `DHAN_ACCESS_TOKEN` and `DHAN_SECURITY_ID` in `.env.local`.

Both return an OHLC frame, so the engine cannot tell them apart. Outside market hours the
runner says so and exits; `--once` overrides that for a single tick. A failed poll prints and
retries rather than killing a session that holds an open position.

Copy `.env.example` to `.env.local` for credentials. `.env.local` is gitignored.

---

## Chart UI

```bash
uv run opentrader serve          # http://127.0.0.1:8000
```

A read-only web view for the job the trade log can't do: seeing whether signals fired where a
chart says they should. Candles, indicator overlays, entry/exit markers, and a clickable trade
log that zooms the chart to a trade and draws its stop and target.

Two things it shows that most charting tools hide:

- **The warmup shroud.** Bars before the indicators converge are shaded out, with the armed
  boundary marked. `pandas.ewm()` emits a value from bar 0, so an "ema50" on bar 3 is really
  just the price — signals there are noise, and the engine skips them. The shroud is where
  those skipped bars are.
- **Straddle flags.** Trades whose exit bar hit *both* the stop and the target are flagged.
  Those are the ones where the conservative "stop wins" rule decided the outcome rather than
  the market, so they're worth a human look.

The server never places an order — it runs the same backtest the CLI runs and serves the
result. `/api/docs` has the endpoint reference.

---

## Project layout

```
strategies/           strategy JSON files — the things you actually edit
src/
  opentrader/         the engine — knows nothing about terminals or browsers
    engine.py         load, validate, compute indicators, step() — the core
    indicators.py     ema(), rsi() as plain functions over a Series
    conditions.py     crosses_above(), crosses_below(), greater(), less()
    mock_ledger.py    open positions dict + closed trades list + CSV, Decimal money
    backtest.py       tvdatafeed replay driver
    live_paper.py     live poll driver — imports step() from engine, does not reimplement it
  cli/                terminal surface
    dispatch.py       routes `opentrader <cmd>`; bare command opens the picker
    prompts.py        InquirerPy picker — builds argv, then calls the same drivers
  constants/          constants.py, filepaths.py — all paths relative to repo root
  helpers/            env_helpers.py — .env.local loading
  logs/               session logs (gitignored)
  db/                 reserved for SQLite; POC persists to CSV
app/                  web surface — read-only, never places an order
  server.py           FastAPI routes + `opentrader serve`
  service.py          backtest result -> chart payload (reshapes only)
  static/             index.html, app.js, style.css — no build step
tests/                pytest suite, no network
docs/                 OpenTrader_Design.md — the full architecture spec
trades/               CSV trade logs (gitignored)
```

Three surfaces, one engine. `cli/` and `app/` both depend on `opentrader/`; neither contains
strategy logic, and the engine imports neither of them.

---

## Development

```bash
uv run pytest                                  # no network, under a second
uv tool run ruff check . && uv tool run ruff format --check .
```

Test conventions, code style and PR rules are in [CONTRIBUTING.md](CONTRIBUTING.md).

---

## Scope: what this is *not*, yet

This is the POC stage of a phased design ([docs/OpenTrader_Design.md](docs/OpenTrader_Design.md)).
The deferrals below are deliberate — each one solves a problem that only exists under a
condition this POC does not meet.

| Not built | Becomes necessary when |
|---|---|
| Real order placement | You accept the risk. Every fill here is assumed and instant. |
| SEBI static-IP + Algo-ID tagging | The first real order reaches an exchange. Mandatory then. |
| Position ledger, reconciliation | A second strategy shares a broker account. |
| OMS state machine, partial fills | Order size grows past instant-full-fill realism. |
| Multiprocessing, Redis, Postgres | More than one strategy runs at a time. |
| Full DSL, linter, validator | You stop eyeballing a handful of hand-written files. |
| Backtest cost model | Never trust the P&L above without it — no commission, slippage, STT or stamp duty is modelled. |
| Short positions | Entries are long-only. A `crosses_below` entry opens a long. |
| Trading calendar | Exchange holidays are not known; only weekends and session hours are. |

**The reported P&L is not a return estimate.** No costs, no slippage, quantity fixed at 1,
survivorship and lookahead unaudited. It is a correctness signal for the engine, nothing more.

---

## License

Apache License 2.0 — see [LICENSE](LICENSE).
