"""demo.py - drive the file tools through the sandbox.

Run from ``ch02/``:

    python -m mini_harness.demo

The demo creates a temporary workspace, performs normal work, then asks for
three operations that must fail. Every result, good or bad, is the exact text a
model would see in its observation.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from .file_tools import run_tool
from .sandbox import Limits, Sandbox


def show(label: str, sandbox: Sandbox, tool: str, args: dict) -> None:
    """Run one tool call and print a compact observation."""
    result = run_tool(sandbox, tool, args)
    # Indent multi-line results so the demo stays readable.
    rendered = result.replace("\n", "\n         ")
    print(f"{label}\n  -> {rendered}")


def main() -> int:
    """Exercise every file tool against a throwaway workspace."""
    with tempfile.TemporaryDirectory(prefix="sandbox-ch02-") as temp:
        workspace = Path(temp) / "workspace"
        workspace.mkdir()
        (workspace / "notes.txt").write_text("alpha\nbeta\n", encoding="utf-8")
        (workspace / "src").mkdir()
        (workspace / "src" / "app.py").write_text("print('hi')\n", encoding="utf-8")

        # A deliberately small limit so the demo can show TOO_LARGE without
        # creating a huge file.
        sandbox = Sandbox(workspace, limits=Limits(max_read_bytes=1024, max_write_bytes=1024))

        show("list workspace", sandbox, "list_files", {"path": "."})
        show("read notes", sandbox, "read_file", {"path": "notes.txt"})
        show(
            "write a new file",
            sandbox,
            "write_file",
            {"path": "todo.md", "content": "- ship the sandbox\n"},
        )
        show(
            "edit the new file",
            sandbox,
            "edit_file",
            {"path": "todo.md", "old_text": "ship", "new_text": "test"},
        )
        show("read it back", sandbox, "read_file", {"path": "todo.md"})

        print()
        print("Now the refusals:\n")
        show(
            "escape with ..",
            sandbox,
            "read_file",
            {"path": "../outside.txt"},
        )
        show(
            "absolute path",
            sandbox,
            "read_file",
            {"path": "/etc/passwd"},
        )
        show(
            "write too large",
            sandbox,
            "write_file",
            {"path": "big.txt", "content": "x" * 2000},
        )
        show(
            "delete a folder",
            sandbox,
            "delete_file",
            {"path": "src"},
        )

        print()
        print("The model sees ERROR[...] strings; the session keeps going.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
