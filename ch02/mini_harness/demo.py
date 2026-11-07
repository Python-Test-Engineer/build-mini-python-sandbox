"""demo.py - drive the file tools through the sandbox.

Run from ``ch02/``:

    python -m mini_harness.demo

The demo creates a temporary workspace, performs normal work, then asks for
three operations that must fail. Every result, good or bad, is the exact text a
model would see in its observation.
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

# A direct script run (``uv run demo.py``) has no package context. Add the
# chapter directory so ``mini_harness`` is importable; module runs skip this.
if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from mini_harness.file_tools import run_tool
from mini_harness.sandbox import Limits, Sandbox
from mini_harness.ui import UI


def show(ui: UI, label: str, sandbox: Sandbox, tool: str, args: dict) -> None:
    """Run one tool call and show a compact observation card."""
    result = run_tool(sandbox, tool, args)
    ui.result(label, result)


def main() -> int:
    """Exercise every file tool against a throwaway workspace."""
    ui = UI(accent="green", title="Stage 2 - The sandbox and file tools")
    ui.header(
        subtitle="Bound the bytes, the writes, and the errors.",
        badge="every result is an observation",
    )

    with tempfile.TemporaryDirectory(prefix="sandbox-ch02-") as temp:
        workspace = Path(temp) / "workspace"
        workspace.mkdir()
        (workspace / "notes.txt").write_text("alpha\nbeta\n", encoding="utf-8")
        (workspace / "src").mkdir()
        (workspace / "src" / "app.py").write_text("print('hi')\n", encoding="utf-8")

        # A deliberately small limit so the demo can show TOO_LARGE without
        # creating a huge file.
        sandbox = Sandbox(workspace, limits=Limits(max_read_bytes=1024, max_write_bytes=1024))

        ui.section("normal work")
        show(ui, "list workspace", sandbox, "list_files", {"path": "."})
        show(ui, "read notes", sandbox, "read_file", {"path": "notes.txt"})
        show(
            ui,
            "write a new file",
            sandbox,
            "write_file",
            {"path": "todo.md", "content": "- ship the sandbox\n"},
        )
        show(
            ui,
            "edit the new file",
            sandbox,
            "edit_file",
            {"path": "todo.md", "old_text": "ship", "new_text": "test"},
        )
        show(ui, "read it back", sandbox, "read_file", {"path": "todo.md"})

        ui.explain(
            "normal work",
            "The sandbox lists the workspace, reads notes, writes todo.md, "
            "edits one word, and reads the result back.",
            "Every file tool goes through the same PathPolicy and Limits "
            "object. A useful sandbox must still allow ordinary work; the "
            "boundary is the cap and the policy, not a refusal of everything.",
        )

        ui.section("the refusals")
        show(
            ui,
            "escape with ..",
            sandbox,
            "read_file",
            {"path": "../outside.txt"},
        )
        show(
            ui,
            "absolute path",
            sandbox,
            "read_file",
            {"path": "/etc/passwd"},
        )
        show(
            ui,
            "write too large",
            sandbox,
            "write_file",
            {"path": "big.txt", "content": "x" * 2000},
        )
        show(
            ui,
            "delete a folder",
            sandbox,
            "delete_file",
            {"path": "src"},
        )

        ui.explain(
            "the refusals",
            "An escape, an absolute read, an oversized write and a folder "
            "delete each return a stable ERROR[CODE] string.",
            "The model gets a refusal it can reason about, not a traceback. "
            "The session can choose another action, and the host path never "
            "appears in the observation.",
        )

        ui.done("The model sees ERROR[...] strings; the session keeps going.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
