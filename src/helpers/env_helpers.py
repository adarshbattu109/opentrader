"""Credential + env loading.

Reads .env.local, which is gitignored (§3: POC credentials = .env file).
"""

import os
from pathlib import Path

from constants.filepaths import ENV_LOCAL


def load_env(path: Path = ENV_LOCAL) -> dict[str, str]:
    """Parse KEY=value lines into os.environ. Existing env vars win.

    Deliberately not python-dotenv -- this is 10 lines and the POC has one
    consumer. Swap it in if quoting/interpolation rules ever get interesting.
    """
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key, value = key.strip(), value.strip().strip("'\"")
        values[key] = value
        os.environ.setdefault(key, value)
    return values


def require(key: str) -> str:
    """Fetch a credential or fail with a pointer to the setup file."""
    load_env()
    value = os.environ.get(key)
    if not value:
        raise SystemExit(f"missing {key}. Copy .env.example to .env.local and fill it in.")
    return value
