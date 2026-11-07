"""Allow ``python -m mini_harness`` to run the CLI."""

import sys
from pathlib import Path

# A direct script run (``uv run __main__.py``) has no package context. Add the
# chapter directory so ``mini_harness`` is importable; module runs skip this.
if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from mini_harness.cli import main

raise SystemExit(main())
