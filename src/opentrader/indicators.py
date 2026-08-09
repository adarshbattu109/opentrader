"""Plain indicator functions over a pandas Series. POC scope (§2.3, §4 step 2).

Hardcoded, not a generic engine. Add a function here when a strategy needs it.
"""

import pandas as pd


def ema(s: pd.Series, period: int) -> pd.Series:
    return s.ewm(span=period, adjust=False).mean()


def rsi(s: pd.Series, period: int = 14) -> pd.Series:
    """Wilder's RSI (smoothing alpha = 1/period, not a simple rolling mean)."""
    delta = s.diff()
    gain = delta.clip(lower=0).ewm(alpha=1 / period, adjust=False).mean()
    loss = (-delta).clip(lower=0).ewm(alpha=1 / period, adjust=False).mean()
    # loss == 0 -> ratio inf -> rsi 100, which is the correct limit.
    return 100 - 100 / (1 + gain / loss)
