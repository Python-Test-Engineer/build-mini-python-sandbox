"""Allow ``python -m mini_harness`` to run the CLI."""

from .cli import main

raise SystemExit(main())
