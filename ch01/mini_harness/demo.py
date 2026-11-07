"""demo.py - show the path policy accepting normal work and refusing escapes.

Run from ``ch01/``:

    python -m mini_harness.demo

Every refusal is a ``PolicyError`` with a stable ``PATH`` code. Later tools turn
that exception into an observation for the model, so a refusal is data, not a
crash.
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

from mini_harness.path_policy import PathPolicy, PolicyError
from mini_harness.ui import UI


def show(ui: UI, label: str, action) -> None:
    """Run one path-policy call and show an allowed or refused result card."""
    try:
        resolved = action()
    except PolicyError as exc:
        # PolicyError.__str__ already begins with "PATH: ".
        ui.result(label, str(exc), kind="error")
    except OSError as exc:
        # A policy pass can still fail later at the OS layer. Keep the demo
        # running so one bad case does not hide the rest.
        ui.result(label, f"{type(exc).__name__}: {exc}", kind="warning")
    else:
        # ``relative`` is the model-facing spelling; ``absolute`` is the file
        # the OS will actually open after symlink resolution.
        ui.result(
            label,
            f"{resolved.relative} -> {resolved.absolute}",
            kind="success",
        )


def main() -> int:
    """Create a throwaway lab and exercise the policy from both sides."""
    ui = UI(accent="cyan", title="Stage 1 - One path policy")
    ui.header(
        subtitle="Stop comparing spellings. Compare real filesystem paths.",
        badge="one policy - every tool",
    )

    with tempfile.TemporaryDirectory(prefix="sandbox-ch01-") as temp:
        base = Path(temp)

        workspace = base / "workspace"
        workspace.mkdir()
        (workspace / "notes.txt").write_text("inside\n", encoding="utf-8")

        # A sibling whose name starts with the workspace name. Stage 0's
        # prefix check allowed this; a real path policy must not.
        sibling = base / "workspace-evil"
        sibling.mkdir()
        (sibling / "secret.txt").write_text("sibling secret\n", encoding="utf-8")

        outside = base / "outside.txt"
        outside.write_text("outside secret\n", encoding="utf-8")

        # A symlink inside the workspace whose target is outside it.
        link = workspace / "link.txt"
        symlink_supported = True
        try:
            os.symlink(outside, link)
        except (OSError, NotImplementedError):
            symlink_supported = False

        policy = PathPolicy(workspace)

        ui.note("Workspace root", str(policy.real_root), kind="info")
        ui.section("reads")

        show(ui, "read notes.txt", lambda: policy.resolve_read("notes.txt"))
        show(ui, "read ../outside.txt", lambda: policy.resolve_read("../outside.txt"))
        show(
            ui,
            "read prefix sibling",
            lambda: policy.resolve_read("../workspace-evil/secret.txt"),
        )
        show(
            ui,
            "read absolute inside",
            lambda: policy.resolve_read(str(workspace / "notes.txt")),
        )
        show(
            ui,
            "read absolute outside",
            lambda: policy.resolve_read(str(outside)),
        )

        if symlink_supported:
            show(ui, "read symlink escape", lambda: policy.resolve_read("link.txt"))
        else:
            ui.note(
                "Skip",
                "read symlink escape: OS did not allow creating a symlink",
                kind="skip",
            )

        ui.explain(
            "reads",
            "A normal read and an absolute read inside the root are allowed. "
            "Traversal, the prefix sibling and the symlink target are refused.",
            "The policy resolves the real path and compares path boundaries "
            "with commonpath. It answers 'which file will the kernel open?', "
            "not 'does this string start with the workspace?'",
        )

        ui.section("writes and platform spellings")
        show(ui, "write notes.txt", lambda: policy.resolve_write("notes.txt"))
        show(
            ui,
            "write nested new path",
            lambda: policy.resolve_write("deep/new/file.txt"),
        )
        show(ui, "write absolute", lambda: policy.resolve_write(str(outside)))
        show(ui, "write ../outside.txt", lambda: policy.resolve_write("../outside.txt"))
        show(ui, "write reserved CON.txt", lambda: policy.resolve_write("CON.txt"))
        show(ui, "read NUL byte", lambda: policy.resolve_read("bad\x00name"))

        ui.explain(
            "writes and platform spellings",
            "Reads may be absolute inside the root, but writes must be "
            "relative. Absolute writes, escaping writes, reserved device "
            "names and control characters are refused.",
            "A write is an intentional workspace action, not an absolute "
            "overwrite. Normalising separators and platform spellings first "
            "makes the same policy hold on Windows and Linux.",
        )

        ui.done("One policy, every tool. That is the Stage 1 rule.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
