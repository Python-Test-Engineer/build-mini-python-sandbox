"""demo.py - show the three holes in the naive fence.

Run from ``ch00/``:

    python -m mini_harness.demo

The demo uses a temporary folder, never your real home directory. It creates a
"workspace", a sibling folder, and (when the OS allows it) a symlink that points
outside the workspace. Then it reads all of them with the naive helper.

The point is not that the helper is bad at reading files. The point is that a
string prefix check answers the wrong question: it checks the spelling of a path
instead of the identity of the file the OS will actually open.
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

# A direct script run (``uv run demo.py``) has no package context. Add the
# chapter directory so ``mini_harness`` is importable; module runs skip this.
if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from mini_harness.ui import UI
from mini_harness.unsafe import read_file, run_shell


def _try(ui: UI, label: str, action) -> None:
    """Run one demo action and show a compact, non-fatal result card."""
    try:
        result = action()
    except Exception as exc:  # noqa: BLE001 - the demo is about failures
        ui.result(label, f"{type(exc).__name__}: {exc}", kind="success")
        return

    # Collapse newlines so one finding stays on one line.
    text = str(result).replace("\n", "\\n")
    ui.result(label, text[:120], kind="error")


def main() -> int:
    """Create a throwaway lab and demonstrate the escape paths."""
    ui = UI(accent="red", title="Stage 0 - The naive fence")
    ui.header(
        subtitle="A string prefix is not a containment check.",
        badge="deliberately unsafe - throwaway workspace only",
    )

    with tempfile.TemporaryDirectory(prefix="sandbox-ch00-") as temp:
        base = Path(temp)

        # The workspace the agent is supposed to see.
        workspace = base / "workspace"
        workspace.mkdir()
        (workspace / "notes.txt").write_text("inside: hello\n", encoding="utf-8")

        # A sibling whose name starts with the workspace name. The naive
        # string check cannot tell ``workspace`` from ``workspace-evil``.
        sibling = base / "workspace-evil"
        sibling.mkdir()
        (sibling / "secret.txt").write_text("sibling secret\n", encoding="utf-8")

        # A file outside the workspace, plus a symlink to it inside. The
        # symlink's *name* is inside; its *target* is not.
        outside = base / "outside-secret.txt"
        outside.write_text("outside secret\n", encoding="utf-8")
        link = workspace / "innocent-link.txt"
        symlink_supported = True
        try:
            os.symlink(outside, link)
        except (OSError, NotImplementedError):
            # Windows without Developer Mode cannot create symlinks. The
            # prefix-sibling hole still demonstrates the problem.
            symlink_supported = False

        ui.note("Workspace", str(workspace), kind="info")
        ui.explain(
            "the setup",
            "The lab has a workspace, a sibling folder called workspace-evil, "
            "and a symlink inside the workspace that points to a file outside.",
            "Each escape below starts from a path that looks legitimate. The "
            "question is not how the path is spelled, but which file the OS "
            "will actually open.",
        )
        ui.section("the three holes")

        _try(ui, "read inside workspace", lambda: read_file(workspace, "notes.txt"))
        _try(ui, "plain ../ traversal", lambda: read_file(workspace, "../outside-secret.txt"))
        _try(ui, "prefix sibling", lambda: read_file(workspace, "../workspace-evil/secret.txt"))

        if symlink_supported:
            _try(ui, "symlink inside workspace", lambda: read_file(workspace, "innocent-link.txt"))
        else:
            ui.note(
                "Skip",
                "symlink escape: OS did not allow creating a symlink",
                kind="skip",
            )

        ui.explain(
            "the string check",
            "The inside read works. The '../' traversal is blocked, but the "
            "prefix sibling and the symlink both return data from outside the "
            "workspace.",
            "The check compares the path string with the workspace prefix. "
            "'workspace-evil' shares that prefix, and a symlink keeps its inside "
            "name while pointing outside.",
        )

        # The shell helper is not a jail either. Keep the command harmless.
        ui.section("the shell helper")
        command = "echo shell-ran-with-inherited-env"
        completed = run_shell(workspace, command)
        ui.note(
            "Shell",
            f"exit={completed.returncode} stdout={completed.stdout.strip()!r}",
            kind="warning",
        )
        ui.explain(
            "the shell helper",
            "The command runs through the platform shell and inherits the "
            "parent environment. There is no timeout and no output cap.",
            "One tool call can become many commands, and the child can see "
            "every secret in the parent environment. Stage 3 replaces this "
            "with an argv allowlist and explicit limits.",
        )

        ui.done(
            "Lesson: prefix checks spell paths; the kernel opens files. "
            "Next: ch01 replaces this with a real path policy."
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
