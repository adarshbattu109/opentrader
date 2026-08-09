# Security Policy

## Supported Versions

| Version | Supported |
|---------|-----------|
| 0.1.x   | Yes       |

## Reporting a Vulnerability

If you discover a security vulnerability in OpenTrader, please report it responsibly:

1. **Do NOT open a public issue.**
2. Use [GitHub Private Vulnerability Reporting](https://github.com/adarshbattu109/opentrader/security/advisories/new)
   to submit a report.
3. Include: description, reproduction steps, impact assessment, and suggested fix (if any).

### Response Timeline

- **Acknowledgment:** Within 72 hours
- **Assessment:** Within 7 days
- **Fix/Disclosure:** Within 90 days (coordinated disclosure)

## Scope

OpenTrader evaluates trading strategies and, in this version, records mock orders to a CSV.
It does **not** place real orders. That is the single most important fact in this document,
and the threat model changes completely the day it stops being true.

### Credentials

- **`DHAN_ACCESS_TOKEN` is a bearer credential for a real brokerage account.** It is read from
  `.env.local`, which is gitignored. Never commit it, never paste it into an issue or a
  stack trace, and revoke it in the Dhan dashboard if it leaks. Depending on the permissions
  granted, a leaked token can read your holdings and place orders against your money — not
  just this app's data. It is not comparable to an API key for a public data source.
- **`.env.local` is the only place credentials belong.** `helpers/env_helpers.py` does not fall
  back to a default for any secret, and `require()` exits with the missing variable's name
  rather than proceeding with `None`. If you add a broker, follow that pattern: a missing
  credential must stop the program, never silently disable a safety check.
- **`.env.example` is committed and must stay valueless.** It documents variable names and how
  to obtain them. Putting a real token there is the most likely way this project leaks one.
- **Rotate anything that has ever been in a shell history, a screenshot, or a log.**

### Money-path correctness is a security property

For a trading system, a logic bug and a vulnerability are the same category of problem: both
cause unauthorised loss of funds. We treat the following as security-relevant, not just
quality-relevant, and they are not simplified away:

- **`Decimal` for money, never `float`.** `mock_ledger.to_money()` uses `Decimal(str(v))` and
  never `Decimal(float)`, so a price does not arrive as `1241.7999999999999`. Report any path
  where a price or P&L becomes a binary float after the signal stage.
- **Warmup enforcement.** `engine.run()` refuses to trade a frame shorter than
  `3 × longest_indicator_period` instead of evaluating conditions against half-formed
  indicators. Silently trading un-warmed data produces confident, wrong signals — the most
  dangerous failure mode this project has.
- **Conservative ambiguity resolution.** When a bar's range contains both the stop and the
  target, the ledger books the **loss**. OHLC data cannot tell us the intrabar sequence, so the
  optimistic read would inflate every backtest. A change that reverses this is a
  breaking change to the results, not an optimisation.
- **Exit-before-entry ordering** in `step()` prevents a position from being re-entered on the
  same bar that closed it.

### Deliberate gaps you must know about before risking money

- **No cost model.** Commission, slippage, STT, stamp duty, exchange fees and GST are **not**
  modelled. Reported P&L is therefore optimistic by an amount that grows with trade frequency.
  A strategy that looks marginally profitable here is likely unprofitable in reality. Do not
  size positions off these numbers.
- **No SEBI algo compliance.** India's retail-algo framework requires broker-registered
  strategies, exchange-issued Algo IDs on tagged orders, and a static IP registered with the
  broker. None of that is implemented, because nothing is transmitted. **Do not wire a real
  order-placement call into this code and run it against a live account** — that is both a
  financial risk and a regulatory one. See `docs/OpenTrader_Design.md` for where this belongs
  in the phased plan.
- **No position reconciliation.** `MockLedger` is the only record of state and it is in-memory
  plus a CSV. It cannot detect a divergence between what it believes it holds and what a
  broker actually holds, because it never asks. The moment real orders exist, this becomes the
  highest-priority missing component.
- **No authentication or authorisation anywhere.** There is no server and no network listener;
  anyone with shell access to the machine has full access to the strategies, the trade log and
  `.env.local`. File permissions are your only control.
- **`--poll` runs unattended with no kill switch.** There is no max-loss circuit breaker, no
  daily trade cap and no remote stop. Today that only wastes CPU. With real orders it would be
  an unbounded-loss defect.
- **Third-party data is trusted.** `tvdatafeed` scrapes an unofficial TradingView endpoint and
  `dhanhq` is a vendor SDK. Bars are used as received, without sanity checks on gaps, spikes,
  splits or adjustments. A bad upstream bar produces a bad signal. Corporate actions are not
  handled at all.
- **Strategy JSON is trusted input.** `load_strategy()` validates indicator names, operator
  names and references, so an unknown key fails loudly rather than silently — but it is a
  schema check, not a sandbox. Do not run strategy files from people you would not trust with
  the account, and note that `json.loads` on a hostile multi-megabyte file is still a local
  resource-exhaustion vector.

### Data at rest

- **`trades/` is gitignored** and holds your strategy's entries, exits and P&L. On a real
  account this is financial-position data — treat it accordingly and do not attach it to
  issues.
- **`src/logs/` is gitignored** and records signals and fills. Keep credentials out of it; if
  you add a broker adapter, never log the request headers.
- **`src/db/` is reserved** for SQLite and is unused in this version.

### Supply chain

Runtime dependencies are kept minimal and monitored with Dependabot and `pip-audit` in CI.
Note that `tvdatafeed` is installed **from a git ref, not PyPI** — it is unpublished, so it is
pinned by URL in `pyproject.toml` and receives no PyPI advisory coverage. Review its diffs
before bumping.

## Non-Goals

- OpenTrader is not a broker, an exchange gateway or a SEBI-compliant algo platform.
- OpenTrader does not protect you from a losing strategy. A correct engine faithfully executes
  a bad idea.
- Backtest results are not a return forecast and are not defensible as investment advice.
  Nothing in this repository is a recommendation to buy or sell any security.
