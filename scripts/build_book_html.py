#!/usr/bin/env python3
"""Render ``book_html.md`` to the sidebar reading guide ``book.html``.

The HTML converter is a Node script from the ``make-html-from-md`` skill. It
expects document metadata in ``DOC_*`` environment variables. This wrapper keeps
the command identical on Windows, macOS and Linux and keeps the long metadata
block out of the README.

Run after ``python scripts/build_book.py``:

    python scripts/build_book_html.py

Requirements: Node.js on PATH. The HTML converter has no npm dependencies.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CONVERTER = ROOT / "scripts" / "md-to-html.mjs"
SOURCE = ROOT / "book_html.md"
OUTPUT = ROOT / "book.html"

# Metadata passed to the converter. Keep these in one place so a rebuild cannot
# drift from the title used by the PDF exporter.
METADATA = {
    "DOC_TITLE": "Build a Mini Python Sandbox",
    "DOC_H1": "Build a Mini Python Sandbox",
    "DOC_EYEBROW": "Mini Python Sandbox · six stages",
    "DOC_LEDE": (
        "A short, runnable book about turning model tool calls into bounded, "
        "auditable operating-system actions."
    ),
    "DOC_TOC_TITLE": "Build a Mini Python Sandbox",
    "DOC_SIDE_SUB": "The path policy, the command runner, the container, the audit trail.",
    "DOC_META": "6 chapters|4 appendices|Python 3.11+|pytest",
    "DOC_SIDE_FOOT": "Built from book_html.md<br>Six stages and four appendices",
    "DOC_SIDE_KICKER": "Mini Python Sandbox · reading guide",
    "DOC_COLOPHON": "Built from book_html.md · six stages · four appendices",
}


def main() -> int:
    """Check inputs, run the converter, and report the output size."""
    if shutil.which("node") is None:
        print("Node.js is required for the HTML reading guide.", file=sys.stderr)
        return 1
    if not CONVERTER.exists():
        print(f"missing converter: {CONVERTER}", file=sys.stderr)
        return 1
    if not SOURCE.exists():
        print(f"missing source: {SOURCE}; run scripts/build_book.py first", file=sys.stderr)
        return 1

    # Start from the caller's environment so PATH and proxy settings still work,
    # then add only the document metadata.
    env = os.environ.copy()
    env.update(METADATA)

    completed = subprocess.run(
        ["node", os.fspath(CONVERTER), os.fspath(SOURCE), os.fspath(OUTPUT)],
        env=env,
        check=False,
    )
    if completed.returncode != 0:
        return completed.returncode

    if completed.returncode != 0:
        return completed.returncode

    # The skill emits a self-contained page with inline CSS and JS. This repo's
    # EXPLAINERS.md standard uses shared assets, so swap the inline blocks for
    # the canonical stylesheet and behaviour script. The shared JS injects the
    # customiser itself; remove the generated copy to avoid duplicate controls.
    html = OUTPUT.read_text(encoding="utf-8")
    html = re.sub(
        r"<style>.*?</style>",
        '<link rel="stylesheet" href="assets/explainer.css">',
        html,
        count=1,
        flags=re.DOTALL,
    )

    main_end = html.find("</main>")
    body_end = html.find("</body>")
    if main_end == -1 or body_end == -1:
        print("could not find the generated page shell", file=sys.stderr)
        return 1

    # Keep the shell-closing </div>, drop the generated customiser markup and
    # inline scripts, then load the shared behaviour once.
    html = (
        html[: main_end + len("</main>")]
        + "\n</div>\n<script src=\"assets/explainer.js\"></script>\n"
        + html[body_end:]
    )

    OUTPUT.write_text(html, encoding="utf-8")

    size = OUTPUT.stat().st_size if OUTPUT.exists() else 0
    print(f"wrote {OUTPUT} ({size:,} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
