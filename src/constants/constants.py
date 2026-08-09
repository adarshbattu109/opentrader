"""Fixed values shared across modules. Nothing here changes at runtime."""

# tvdatafeed interval strings accepted on the CLI -> attribute name on
# tvDatafeed.Interval. Kept as strings so constants/ imports no third-party code.
INTERVALS = {
    "1m": "in_1_minute",
    "5m": "in_5_minute",
    "15m": "in_15_minute",
    "1h": "in_1_hour",
    "1d": "in_daily",
}

# NSE regular session, Asia/Kolkata. Used by the live poller to stop at close.
MARKET_OPEN = "09:15"
MARKET_CLOSE = "15:30"
TIMEZONE = "Asia/Kolkata"

# POC exit priority: a bar that straddles both books the loss.
EXIT_REASONS = ("stop_loss", "target")

# An EMA has no NaN warmup, so bars are skipped by count instead (engine.warmup_bars).
WARMUP_MULTIPLIER = 3
