"""Interactive picker for the two drivers. Prompts, then hands off -- no logic of its own.

Every answer is turned into the argv the equivalent command line would have used
and the existing driver `main()` runs it. That keeps one code path: anything you
can do here you can do with flags, and the TUI cannot drift from the CLI.
"""

import json
import sys

from InquirerPy import inquirer
from InquirerPy.base.control import Choice
from InquirerPy.validator import EmptyInputValidator

from constants.constants import INTERVALS, MARKET_CLOSE, MARKET_OPEN
from constants.filepaths import STRATEGIES_DIR

MODES = {
    "backtest": "opentrader.backtest",
    "live": "opentrader.live_paper",
    "serve": "app.server",
}


def _strategy_choices() -> list[Choice]:
    """One entry per strategy file, labelled with what it actually trades."""
    choices = []
    for path in sorted(STRATEGIES_DIR.glob("*.json")):
        try:
            s = json.loads(path.read_text())
            entry = s["entry"]
            label = (
                f"{path.stem:<18} {s['symbol']:<10} {entry['left']} {entry['op']} {entry['right']}"
            )
        except (json.JSONDecodeError, KeyError) as exc:
            # A broken file should be visible and skippable, not crash the menu.
            label = f"{path.stem:<18} [unreadable: {type(exc).__name__}]"
        choices.append(Choice(value=str(path), name=label))
    return choices


def _has_dhan_credentials() -> bool:
    from helpers.env_helpers import load_env

    env = load_env()
    return bool(env.get("DHAN_CLIENT_ID") and env.get("DHAN_ACCESS_TOKEN"))


def build_argv(answers: dict) -> list[str]:
    """Answers -> the argv the driver's argparse expects. Pure; tested."""
    if answers["mode"] == "serve":
        # The UI picks its own strategy from a menu, so it takes no path here.
        return ["opentrader", "--port", str(answers["port"])]

    argv = ["opentrader", answers["strategy"], "--interval", answers["interval"]]
    if answers["mode"] == "backtest":
        return argv + ["--bars", str(answers["bars"])]

    argv += ["--source", answers["source"]]
    if answers.get("once"):
        return argv + ["--once"]
    return argv + ["--poll", str(answers["poll"])]


def ask() -> dict:
    """Run the prompts. Returns the answer dict."""
    answers: dict = {}

    answers["mode"] = inquirer.select(
        message="Mode:",
        choices=[
            Choice("backtest", name="backtest   replay historical bars"),
            Choice("live", name="live       poll a live feed (mock orders only)"),
            Choice("serve", name="serve      open the chart UI in a browser"),
            Choice("quit", name="quit       exit"),
        ],
        default="backtest",
        instruction="(arrows to move, enter to pick, ctrl-c to quit)",
    ).execute()

    if answers["mode"] == "quit":
        return answers

    if answers["mode"] == "serve":
        answers["port"] = inquirer.number(
            message="Port:",
            default=8000,
            min_allowed=1024,
            max_allowed=65535,
            validate=EmptyInputValidator(),
        ).execute()
        return answers

    choices = _strategy_choices()
    if not choices:
        sys.exit(f"no strategy files found in {STRATEGIES_DIR}/")

    answers["strategy"] = inquirer.select(
        message="Strategy:",
        choices=choices,
    ).execute()

    answers["interval"] = inquirer.select(
        message="Bar interval:",
        choices=list(INTERVALS),
        default="1d" if answers["mode"] == "backtest" else "5m",
    ).execute()

    if answers["mode"] == "backtest":
        answers["bars"] = inquirer.number(
            message="How many bars:",
            default=500,
            min_allowed=1,
            max_allowed=20000,
            validate=EmptyInputValidator(),
        ).execute()
        return answers

    has_creds = _has_dhan_credentials()
    answers["source"] = inquirer.select(
        message="Data source:",
        choices=[
            Choice("tv", name="tv     tvdatafeed, no credentials"),
            Choice(
                "dhan",
                name="dhan   broker last-price"
                + ("" if has_creds else "   [DHAN_* missing from .env.local]"),
            ),
        ],
        default="tv",
        long_instruction=(
            "" if has_creds else "dhan exits asking for credentials until .env.local is filled in"
        ),
    ).execute()

    answers["once"] = inquirer.confirm(
        message=f"Single tick now? (no = poll until {MARKET_CLOSE} IST)",
        default=True,
    ).execute()

    if not answers["once"]:
        answers["poll"] = inquirer.number(
            message="Seconds between polls:",
            default=60,
            min_allowed=5,
            max_allowed=3600,
            validate=EmptyInputValidator(),
        ).execute()
    return answers


def main() -> None:
    from importlib import import_module

    print(f"OpenTrader — mock orders only. Market hours {MARKET_OPEN}-{MARKET_CLOSE} IST.\n")
    try:
        answers = ask()
    except KeyboardInterrupt:
        sys.exit("\ncancelled.")
    if not answers.get("mode"):
        sys.exit("cancelled.")
    if answers["mode"] == "quit":
        return
    if answers["mode"] != "serve" and not answers.get("strategy"):
        sys.exit("cancelled.")

    argv = build_argv(answers)
    # Show the equivalent command so the TUI teaches the CLI rather than hiding it.
    print(f"\n$ opentrader {answers['mode']} {' '.join(argv[1:])}\n")
    sys.argv = argv
    import_module(MODES[answers["mode"]]).main()


if __name__ == "__main__":
    main()
