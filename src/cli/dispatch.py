"""Subcommand routing for the `opentrader` command.

Dispatch only. Each subcommand's argument parsing stays in its own module, so
`python -m opentrader.backtest ...` keeps working exactly as before. Bare
`opentrader` opens the interactive picker rather than printing usage, since the
prompts are more useful to a first-time reader than a flag list.
"""

import sys
from importlib import import_module
from pathlib import Path

# `src/` is on sys.path via the installed package, but `app/` sits at the repo
# root and a console script does not add the working directory. Every path in
# this project is already repo-root-relative (constants/filepaths.py), so the
# working directory is the repo root by convention -- make that importable too.
if (root := str(Path.cwd())) not in sys.path:
    sys.path.insert(0, root)

COMMANDS = {
    "backtest": ("opentrader.backtest", "replay a strategy over historical bars"),
    "live": ("opentrader.live_paper", "run it against a live feed (mock orders only)"),
    "serve": ("app.server", "start the web UI for charting trades"),
    "pick": ("cli.prompts", "interactive picker (same as bare `opentrader`)"),
}

USAGE = "\n".join(
    [
        f"usage: opentrader [{'|'.join(COMMANDS)}] [options]",
        "",
        *(f"  {name:<9} {desc}" for name, (_, desc) in COMMANDS.items()),
        "",
        "Run `opentrader` with no arguments for an interactive picker.",
        "Run `opentrader <cmd> --help` for that command's options.",
        "",
        "examples:",
        "  opentrader backtest strategies/ema_cross.json",
        "  opentrader backtest strategies/rsi_oversold.json --interval 15m --bars 2000",
        "  opentrader live strategies/ema_cross.json --once",
        "  opentrader serve",
    ]
)


def main() -> None:
    if len(sys.argv) < 2:
        import_module("cli.prompts").main()
        return
    if sys.argv[1] in ("-h", "--help"):
        print(USAGE)
        return
    if sys.argv[1] not in COMMANDS:
        sys.exit(f"unknown command {sys.argv[1]!r}\n\n{USAGE}")
    module, _ = COMMANDS[sys.argv.pop(1)]
    import_module(module).main()


if __name__ == "__main__":
    main()
