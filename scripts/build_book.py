#!/usr/bin/env python3
"""Build a single book manuscript from the chapter and manual Markdown files.

The repository keeps every chapter as its own file so a reader can run one
stage without loading the whole book. The PDF exporter, however, wants one
long-form Markdown file with:

  * one ``#`` title;
  * ``##`` chapters (each starts on a new page in the PDF);
  * ``###`` sections (nested bookmarks).

This script concatenates the sources and demotes every source heading by one
level so that invariant holds. It never edits the source files.

Usage:
    python scripts/build_book.py [output.md]

The default output is ``book.md`` at the repository root.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = ROOT / "book.md"

# The order is the reading order of the finished book. README becomes the
# introduction; the numbered chapters follow; the manuals are appendices.
SOURCES = [
    ("README.md", "Introduction", "readme"),
    ("ch00/CHAPTER.md", None, "chapter"),
    ("ch01/CHAPTER.md", None, "chapter"),
    ("ch02/CHAPTER.md", None, "chapter"),
    ("ch03/CHAPTER.md", None, "chapter"),
    ("ch04/CHAPTER.md", None, "chapter"),
    ("ch05/CHAPTER.md", None, "chapter"),
    ("THREAT_MODEL.md", "Appendix A — Threat model", "manual"),
    ("OPERATIONS.md", "Appendix B — Operations runbook", "manual"),
    ("plan.md", "Appendix C — Build contract", "manual"),
    ("function_reference.md", "Appendix D — Function reference", "manual"),
]

# One or more leading hashes followed by a space. We only touch headings at
# the start of a line, never inline ``#`` characters.
HEADING_RE = re.compile(r"^(#{1,6})(\s+)")

# A fenced code block can contain shell comments that look like headings
# (``## from the repository root``). Those must not be demoted. Track fences
# by marker character and length so nested-looking blocks stay intact.
FENCE_RE = re.compile(r"^\s{0,3}(`{3,}|~{3,})")


def demote_headings(text: str) -> str:
    """Add one ``#`` to every real Markdown heading, skipping code fences.

    A chapter file starts at ``# Chapter 0``. In the combined book that must
    become ``## Chapter 0`` so the PDF exporter treats it as a chapter. Its
    ``##`` sections become ``###`` and are nested under it in the outline.
    """
    output: list[str] = []
    fence_char: str | None = None
    fence_length = 0

    for line in text.splitlines():
        fence = FENCE_RE.match(line)
        if fence:
            marker = fence.group(1)
            if fence_char is None:
                fence_char = marker[0]
                fence_length = len(marker)
            elif marker[0] == fence_char and len(marker) >= fence_length:
                fence_char = None
                fence_length = 0
            output.append(line)
            continue

        if fence_char is not None:
            # Inside a code block: never treat ``#`` as a heading.
            output.append(line)
            continue

        match = HEADING_RE.match(line)
        if match and len(match.group(1)) < 6:
            output.append("#" + line)
        else:
            output.append(line)

    return "\n".join(output)



def count_h1_outside_fences(text: str) -> int:
    """Count real level-1 headings, ignoring shell comments in code fences."""
    count = 0
    fence_char: str | None = None
    fence_length = 0
    for line in text.splitlines():
        fence = FENCE_RE.match(line)
        if fence:
            marker = fence.group(1)
            if fence_char is None:
                fence_char = marker[0]
                fence_length = len(marker)
            elif marker[0] == fence_char and len(marker) >= fence_length:
                fence_char = None
                fence_length = 0
            continue
        if fence_char is None and line.startswith("# "):
            count += 1
    return count

def strip_first_h1(text: str) -> str:
    """Remove the source's own top-level title.

    For README we supply the book title separately, so keeping README's
    ``# Build a Mini Python Sandbox`` would create a duplicate document title.
    """
    lines = text.splitlines()
    for index, line in enumerate(lines):
        if line.startswith("# "):
            del lines[index]
            return "\n".join(lines).lstrip("\n")
    return text


def read_source(path: Path) -> str:
    """Read UTF-8 and normalise trailing whitespace at the end of the file."""
    return path.read_text(encoding="utf-8").rstrip() + "\n"


def build() -> str:
    """Return the complete combined Markdown document."""
    parts: list[str] = []

    # Front matter. The italic kicker is styled by the PDF stylesheet; the
    # first paragraph is the lede.
    parts.append(
        "*Mini Python Sandbox · the path policy, the command runner, the container*\n\n"
        "# Build a Mini Python Sandbox\n\n"
        "A short, runnable book about turning model tool calls into bounded, "
        "auditable operating-system actions. Six standalone Python stages move "
        "from a deliberately broken fence to a hardened Docker container.\n"
    )

    for relative_path, forced_title, kind in SOURCES:
        path = ROOT / relative_path
        if not path.exists():
            raise SystemExit(f"missing source: {path}")

        body = read_source(path)

        if kind == "readme":
            body = strip_first_h1(body)
            body = demote_headings(body)
            # README's ``##`` sections become ``###`` under this introduction.
            title = forced_title or "Introduction"
            parts.append(f"## {title}\n\n{body}")
            continue

        if kind in {"chapter", "manual"}:
            # Chapter/manual files already have a useful H1 title. Demoting it
            # to H2 makes it a chapter in the combined book. If a source ever
            # loses its H1, fall back to the explicit title.
            if forced_title and not re.search(r"^#\s+", body, re.MULTILINE):
                body = f"# {forced_title}\n\n{body}"
            parts.append(demote_headings(body).strip())
            continue

        raise SystemExit(f"unknown source kind: {kind}")

    # A horizontal rule makes the boundary between appendices visible even in
    # readers that ignore page-break CSS.
    return "\n\n---\n\n".join(parts).rstrip() + "\n"


def build_html_source() -> str:
    """Build the source shape the HTML reading-guide converter expects.

    That converter treats every level-1 heading as a numbered section and every
    level-2 heading as a nested entry. The original chapter files already have
    that shape, so this variant keeps their headings untouched. README's title
    is replaced by ``# Introduction`` to avoid a duplicate page title.
    """
    parts: list[str] = []

    readme = read_source(ROOT / "README.md")
    readme = strip_first_h1(readme)
    parts.append("# Introduction\n\n" + readme)

    for relative_path, _forced_title, kind in SOURCES[1:]:
        path = ROOT / relative_path
        if not path.exists():
            raise SystemExit(f"missing source: {path}")
        parts.append(read_source(path).strip())

    return "\n\n---\n\n".join(parts).rstrip() + "\n"


def main(argv: list[str]) -> int:
    """Write the combined manuscript and report the result."""
    output = Path(argv[1]).resolve() if len(argv) > 1 else DEFAULT_OUTPUT

    manuscript = build()
    output.write_text(manuscript, encoding="utf-8")

    # A second source shape is kept for the HTML reading guide. It uses one
    # H1 per chapter, which is what the sidebar converter numbers as sections.
    html_output = output.with_name(output.stem + "_html.md")
    html_source = build_html_source()
    html_output.write_text(html_source, encoding="utf-8")

    # A quick sanity check for the PDF source: only the document title should
    # be H1. Code fences are skipped by the counter.
    h1_count = count_h1_outside_fences(manuscript)
    print(f"wrote {output}")
    print(f"lines: {len(manuscript.splitlines())}")
    print(f"h1 headings: {h1_count} (expected 1)")
    print(f"wrote {html_output}")
    print(f"html source lines: {len(html_source.splitlines())}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
