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
import tempfile
from pathlib import Path

from .unsafe import read_file, run_shell


def _try(label: str, action) -> None:
    """Run one demo action and print a compact, non-fatal result line."""
    try:
        result = action()
    except Exception as exc:  # noqa: BLE001 - the demo is about failures
        print(f"[blocked] {label}: {type(exc).__name__}: {exc}")
        return

    # Collapse newlines so one finding stays on one line.
    text = str(result).replace("\n", "\\n")
    print(f"[leaked ] {label}: {text[:120]}")


def main() -> int:
    """Create a throwaway lab and demonstrate the escape paths."""
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

        print("workspace:", workspace)
        print()

        _try("read inside workspace", lambda: read_file(workspace, "notes.txt"))
        _try("plain ../ traversal", lambda: read_file(workspace, "../outside-secret.txt"))
        _try("prefix sibling", lambda: read_file(workspace, "../workspace-evil/secret.txt"))

        if symlink_supported:
            _try("symlink inside workspace", lambda: read_file(workspace, "innocent-link.txt"))
        else:
            print("[skip   ] symlink escape: OS did not allow creating a symlink")

        # The shell helper is not a jail either. Keep the command harmless.
        command = "echo shell-ran-with-inherited-env"
        completed = run_shell(workspace, command)
        print(f"[shell  ] exit={completed.returncode} stdout={completed.stdout.strip()!r}")

        print()
        print("Lesson: prefix checks spell paths; the kernel opens files.")
        print("Next: ch01 replaces this with a real path policy.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
