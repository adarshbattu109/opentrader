"""Subcommand routing. No network -- every subcommand target is replaced with a spy.

`app.server` only imports when the repo root is on sys.path, which dispatch.py
arranges from the working directory. That means these tests, like the console
script, assume they are run from the repo root.

uv run pytest
"""

import sys
from importlib import import_module
from pathlib import Path

import pytest

from cli import dispatch, prompts


def test_runs_from_the_repo_root():
    """Everything below depends on it; fail with the reason rather than an ImportError."""
    assert (Path.cwd() / "pyproject.toml").exists(), (
        f"run pytest from the repo root, not {Path.cwd()}"
    )


@pytest.mark.parametrize("name", list(dispatch.COMMANDS))
def test_every_command_target_is_importable_and_has_main(name):
    """A typo in COMMANDS would only surface when a user runs that subcommand."""
    module, desc = dispatch.COMMANDS[name]
    assert callable(import_module(module).main), f"{name} -> {module} has no callable main"
    assert desc, f"{name} needs a usage description"


def test_bare_argv_opens_the_interactive_picker(monkeypatch):
    """Bare `opentrader` prompts instead of printing a flag list -- and does not exit."""
    called = []
    monkeypatch.setattr(sys, "argv", ["opentrader"])
    monkeypatch.setattr("cli.prompts.main", lambda: called.append(True))

    dispatch.main()

    assert called == [True], "bare argv must hand off to cli.prompts.main"


@pytest.mark.parametrize("flag", ["--help", "-h"])
def test_help_prints_usage_without_exiting(flag, monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["opentrader", flag])

    dispatch.main()

    out = capsys.readouterr().out
    assert "usage: opentrader" in out
    for name in dispatch.COMMANDS:
        assert name in out, f"{name} missing from usage"


def test_unknown_subcommand_exits_non_zero_naming_it(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["opentrader", "wibble"])

    with pytest.raises(SystemExit) as exc:
        dispatch.main()

    # SystemExit(str) -> exit code 1 with the message on stderr.
    assert exc.value.code != 0
    assert "wibble" in str(exc.value), "the message must name the bad command"
    assert "usage: opentrader" in str(exc.value)


def test_subcommand_is_stripped_before_the_driver_parses(monkeypatch):
    """The driver must see its own flags only, or argparse rejects 'backtest'."""
    seen = []
    monkeypatch.setattr(sys, "argv", ["opentrader", "backtest", "s.json", "--bars", "10"])
    monkeypatch.setattr("opentrader.backtest.main", lambda: seen.append(list(sys.argv)))

    dispatch.main()

    assert seen == [["opentrader", "s.json", "--bars", "10"]], seen


def test_usage_lists_every_command_with_its_description():
    for name, (_, desc) in dispatch.COMMANDS.items():
        assert name in dispatch.USAGE
        assert desc in dispatch.USAGE


def test_picker_modes_match_the_dispatch_targets():
    """Both routes must reach the same drivers, or the TUI can drift from the CLI."""
    assert prompts.MODES["backtest"] == dispatch.COMMANDS["backtest"][0]
    assert prompts.MODES["live"] == dispatch.COMMANDS["live"][0]


# build_argv is the whole TUI-to-CLI contract: answers in, the exact command line
# the driver's argparse would have seen out. Pure, so it needs no prompts.


def test_build_argv_backtest():
    answers = {
        "strategy": "strategies/ema_cross.json",
        "mode": "backtest",
        "interval": "15m",
        "bars": 2000,
    }
    assert prompts.build_argv(answers) == [
        "opentrader",
        "strategies/ema_cross.json",
        "--interval",
        "15m",
        "--bars",
        "2000",
    ]


def test_build_argv_backtest_stringifies_the_bar_count():
    """InquirerPy's number prompt answers with a string; argv must stay all strings."""
    argv = prompts.build_argv(
        {"strategy": "s.json", "mode": "backtest", "interval": "1d", "bars": "500"}
    )
    assert argv == ["opentrader", "s.json", "--interval", "1d", "--bars", "500"]
    assert all(isinstance(a, str) for a in argv)


def test_build_argv_live_once():
    assert prompts.build_argv(
        {"strategy": "s.json", "mode": "live", "interval": "5m", "source": "tv", "once": True}
    ) == ["opentrader", "s.json", "--interval", "5m", "--source", "tv", "--once"]


def test_build_argv_live_poll():
    """Not --once -> a poll interval instead, never both."""
    argv = prompts.build_argv(
        {
            "strategy": "s.json",
            "mode": "live",
            "interval": "1m",
            "source": "dhan",
            "once": False,
            "poll": 60,
        }
    )
    assert argv == ["opentrader", "s.json", "--interval", "1m", "--source", "dhan", "--poll", "60"]
    assert "--once" not in argv
