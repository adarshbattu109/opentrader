"""Every path the project writes to or reads from. Import these, don't rebuild them.

All paths are relative to the repo root -- run commands from there
(`uv run python -m opentrader.backtest ...`) and they resolve correctly.
"""

from pathlib import Path

STRATEGIES_DIR = Path("strategies")
TRADES_DIR = Path("trades")
LOGS_DIR = Path("src/logs")
DB_DIR = Path("src/db")

ENV_LOCAL = Path(".env.local")
ENV_EXAMPLE = Path(".env.example")


def trade_log(strategy_name: str) -> Path:
    TRADES_DIR.mkdir(parents=True, exist_ok=True)
    return TRADES_DIR / f"{strategy_name}.csv"


def session_log(strategy_name: str) -> Path:
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    return LOGS_DIR / f"{strategy_name}.log"
