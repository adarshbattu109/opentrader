"""FastAPI server for the chart UI.

Read-only over the same engine the CLI drives -- this serves results, it never
places an order. `uv run opentrader serve`, then open http://127.0.0.1:8000.
"""

import argparse
import json
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from constants.constants import INTERVALS
from constants.filepaths import STRATEGIES_DIR
from opentrader.backtest import fetch
from opentrader.engine import load_strategy, run

from .service import chart_payload

STATIC = Path(__file__).parent / "static"
# StaticFiles raises at import time on a missing directory, which would break
# `opentrader serve` on a fresh clone before the assets are in place.
STATIC.mkdir(exist_ok=True)

app = FastAPI(title="OpenTrader", docs_url="/api/docs")


@app.get("/api/strategies")
def list_strategies() -> dict:
    """Every strategy file on disk, with enough detail to label a menu entry."""
    items = []
    for path in sorted(STRATEGIES_DIR.glob("*.json")):
        try:
            s = json.loads(path.read_text())
            entry = s["entry"]
            items.append(
                {
                    "path": str(path),
                    "name": s["name"],
                    "symbol": s["symbol"],
                    "exchange": s["exchange"],
                    "entry": f"{entry['left']} {entry['op']} {entry['right']}",
                    "stop_loss_pct": s["stop_loss_pct"],
                    "risk_reward_ratio": s["risk_reward_ratio"],
                }
            )
        except (json.JSONDecodeError, KeyError) as exc:
            # Surface the broken file instead of dropping it silently.
            items.append({"path": str(path), "name": path.stem, "error": str(exc)})
    return {"strategies": items, "intervals": list(INTERVALS)}


@app.get("/api/backtest")
def backtest(strategy: str, interval: str = "1d", bars: int = 500) -> dict:
    """Run one backtest and return everything the chart needs."""
    if interval not in INTERVALS:
        raise HTTPException(400, f"unknown interval {interval!r}; have {list(INTERVALS)}")
    if not 1 <= bars <= 20000:
        raise HTTPException(400, "bars must be between 1 and 20000")

    # Only files the server already lists are runnable -- a path from the query
    # string must not reach the filesystem directly.
    allowed = {str(p) for p in STRATEGIES_DIR.glob("*.json")}
    if strategy not in allowed:
        raise HTTPException(404, f"no such strategy: {strategy}")

    try:
        strat = load_strategy(strategy)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc

    try:
        df = fetch(strat["symbol"], strat["exchange"], interval, bars)
    except SystemExit as exc:
        # fetch() exits for a dead symbol; a web request must answer, not die.
        raise HTTPException(502, str(exc)) from exc

    try:
        ledger = run(df, strat, verbose=False)
    except SystemExit as exc:
        raise HTTPException(422, str(exc)) from exc

    return chart_payload(df, strat, ledger, interval)


@app.get("/")
def index() -> FileResponse:
    return FileResponse(STATIC / "index.html")


app.mount("/static", StaticFiles(directory=STATIC), name="static")


def main() -> None:
    import uvicorn

    p = argparse.ArgumentParser(description="Serve the OpenTrader chart UI.")
    p.add_argument("--host", default="127.0.0.1", help="bind address")
    p.add_argument("--port", type=int, default=8000)
    p.add_argument("--reload", action="store_true")
    args = p.parse_args()

    print(f"OpenTrader UI -> http://{args.host}:{args.port}  (read-only, no orders)")
    uvicorn.run("app.server:app", host=args.host, port=args.port, reload=args.reload)


if __name__ == "__main__":
    main()
