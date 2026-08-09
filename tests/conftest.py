"""Put the repo root on sys.path so tests can import `app`.

`src/` is on the path via the installed package, but `app/` sits at the repo
root, which a src-layout install does not add -- src/cli/dispatch.py does the
same insert for the console script. Off __file__ rather than cwd so it does not
matter where pytest was invoked from.
"""

import sys
from pathlib import Path

if (root := str(Path(__file__).resolve().parents[1])) not in sys.path:
    sys.path.insert(0, root)
