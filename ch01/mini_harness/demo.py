"""demo.py - show the path policy accepting normal work and refusing escapes.

Run from ``ch01/``:

    python -m mini_harness.demo

Every refusal is a ``PolicyError`` with a stable ``PATH`` code. Later tools turn
that exception into an observation for the model, so a refusal is data, not a
crash.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

from .path_policy import PathPolicy, PolicyError


def show(label: str, action) -> None:
    """Run one path-policy call and print an allowed or refused result."""
    try:
        resolved = action()
    except PolicyError as exc:
        # PolicyError.__str__ already begins with "PATH: ".
        print(f"[blocked] {label}: {exc}")
    except OSError as exc:
        # A policy pass can still fail later at the OS layer. Keep the demo
        # running so one bad case does not hide the rest.
        print(f"[os-error] {label}: {type(exc).__name__}: {exc}")
    else:
        # ``relative`` is the model-facing spelling; ``absolute`` is the file
        # the OS will actually open after symlink resolution.
        print(f"[allowed] {label}: {resolved.relative} -> {resolved.absolute}")


def main() -> int:
    """Create a throwaway lab and exercise the policy from both sides."""
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

        print("workspace root:", policy.real_root)
        print()

        show("read notes.txt", lambda: policy.resolve_read("notes.txt"))
        show("read ../outside.txt", lambda: policy.resolve_read("../outside.txt"))
        show(
            "read prefix sibling",
            lambda: policy.resolve_read("../workspace-evil/secret.txt"),
        )
        show(
            "read absolute inside",
            lambda: policy.resolve_read(str(workspace / "notes.txt")),
        )
        show(
            "read absolute outside",
            lambda: policy.resolve_read(str(outside)),
        )

        if symlink_supported:
            show("read symlink escape", lambda: policy.resolve_read("link.txt"))
        else:
            print("[skip] read symlink escape: OS did not allow creating a symlink")

        show("write notes.txt", lambda: policy.resolve_write("notes.txt"))
        show(
            "write nested new path",
            lambda: policy.resolve_write("deep/new/file.txt"),
        )
        show("write absolute", lambda: policy.resolve_write(str(outside)))
        show("write ../outside.txt", lambda: policy.resolve_write("../outside.txt"))
        show("write reserved CON.txt", lambda: policy.resolve_write("CON.txt"))
        show("read NUL byte", lambda: policy.resolve_read("bad\x00name"))

        print()
        print("One policy, every tool. That is the Stage 1 rule.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
