---
name: Bug Report
about: Report something that isn't working as expected
labels: bug
---

## Description

<!-- Clear description of the bug -->

## Steps to Reproduce

1.
2.
3.

## Strategy File

<!-- Paste the strategy JSON that triggers it, or say which one in strategies/ -->

```json

```

## Command

<!-- e.g. uv run python -m opentrader.backtest strategies/ema_cross.json --interval 15m -->

```

```

## Expected Behavior

<!-- What you expected to happen. For a wrong-signal report, say which bar and why —
     "entry on 2026-02-11 but ema9 was still below ema21" beats "signals look wrong". -->

## Actual Behavior

<!-- What actually happened (include the stacktrace, and the relevant lines from
     src/logs/ — check them for anything you'd rather not share first) -->

## Environment

- Python version:
- OpenTrader version / commit:
- OS:
- Data source: `tv` / `dhan`
- Interval and bar count:

<!-- Do NOT paste DHAN_ACCESS_TOKEN, DHAN_CLIENT_ID, .env.local, or a trades/*.csv from
     a real account. Redact account identifiers from any log you attach. -->
