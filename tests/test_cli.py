"""Dispatcher checks. No network -- the subcommand target is replaced with a spy."""

import sys

import pytest

from cli import dispatch as cli


def test_every_command_target_is_importable_and_has_main():
    """A typo in COMMANDS would only surface when a user runs that subcommand."""
    from importlib import import_module

    for name, (module, desc) in cli.COMMANDS.items():
        assert callable(import_module(module).main), name
        assert desc, f"{name} needs a usage description"


def test_unknown_subcommand_exits_with_usage(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["opentrader", "wibble"])
    with pytest.raises(SystemExit) as exc:
        cli.main()
    # SystemExit(str) -> exit code 1 with the message on stderr.
    assert "usage: opentrader" in str(exc.value)
    assert "backtest" in str(exc.value) and "live" in str(exc.value)


def test_help_prints_usage_and_returns(monkeypatch, capsys):
    """--help is an answer, not an error: it prints and returns without exiting."""
    monkeypatch.setattr(sys, "argv", ["opentrader", "--help"])
    cli.main()
    out = capsys.readouterr().out
    assert "usage: opentrader" in out
    assert "backtest" in out and "live" in out


def test_bare_argv_opens_the_picker_instead_of_printing_usage(monkeypatch):
    """The TUI lives in cli.prompts now; spy on it so no prompt is drawn."""
    called = []
    monkeypatch.setattr(sys, "argv", ["opentrader"])
    monkeypatch.setattr("cli.prompts.main", lambda: called.append(True))
    cli.main()
    assert called == [True]


def test_subcommand_is_stripped_before_the_driver_parses(monkeypatch):
    """The driver must see its own flags only, or argparse rejects 'backtest'."""
    seen = []
    monkeypatch.setattr(sys, "argv", ["opentrader", "backtest", "s.json", "--bars", "10"])
    monkeypatch.setattr("opentrader.backtest.main", lambda: seen.append(list(sys.argv)))

    cli.main()

    assert seen == [["opentrader", "s.json", "--bars", "10"]], seen
