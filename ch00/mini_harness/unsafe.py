"""unsafe.py - the first, broken fence around the workspace.

A very common first attempt at sandboxing looks like this:

    target = os.path.abspath(os.path.join(root, user_path))
    if target.startswith(root):
        return open(target)

It blocks the obvious ``../../etc/passwd`` spelling, which makes the demo feel
safe, but it has three holes that matter:

1. **Symlinks.** ``workspace/link -> /home/me/.ssh`` is still "inside" the
   workspace as a string, even though opening it reads a file far away.
2. **Prefix siblings.** ``/tmp/workspace-evil`` starts with ``/tmp/workspace``
   as a string, so a sibling folder passes the check.
3. **Commands.** Running through a shell inherits the environment, has no
   timeout, no output cap and no kernel limit. It can outlive the agent.

This module is intentionally unsafe. The tests in ``tests/test_unsafe.py``
prove the holes instead of hiding them, so the next chapter has a concrete
target to fix.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import Union

# ``PathLike`` keeps the helpers friendly to both strings and pathlib objects.
PathLike = Union[str, os.PathLike[str]]


def _naive_inside(root: str, candidate: str) -> bool:
    """Return True when ``candidate`` starts with ``root`` as text.

    This is the bug, stated plainly. Path containment is not a string prefix
    relationship. We keep it in its own function so the tests can point at it.
    """
    return candidate.startswith(root)


def _join(root: str, relative: str) -> str:
    """Join and normalise a user-supplied path against the workspace root.

    ``os.path.abspath`` collapses ``.`` and ``..``. That makes the obvious
    traversal spelling look harmless, which is exactly why a string-prefix
    check is so tempting. It does not resolve symlinks.
    """
    return os.path.abspath(os.path.join(root, relative))


def read_file(root: PathLike, relative: str) -> str:
    """Read a file the naive way.

    Raises ``ValueError`` only when the *string* check fails. Escapes through
    symlinks and prefix-sibling folders are allowed, because this stage is the
    "before" picture.
    """
    root_text = os.path.abspath(os.fspath(root))
    target = _join(root_text, relative)

    if not _naive_inside(root_text, target):
        # This catches plain ``..`` traversal, but nothing else.
        raise ValueError(f"path escapes workspace: {relative}")

    # No size cap, no encoding decision, no symlink check. Read it all.
    return Path(target).read_text(encoding="utf-8", errors="replace")


def list_files(root: PathLike, relative: str = ".") -> list[str]:
    """List one directory using the same naive containment rule.

    The return value is sorted so demos and tests are deterministic. We do not
    recurse: recursion would multiply the same bug without teaching anything
    new at this stage.
    """
    root_text = os.path.abspath(os.fspath(root))
    target = _join(root_text, relative)

    if not _naive_inside(root_text, target):
        raise ValueError(f"path escapes workspace: {relative}")

    # ``iterdir`` can raise if the target is missing, which is fine here; the
    # caller sees a normal OSError.
    return sorted(entry.name for entry in Path(target).iterdir())


def run_shell(root: PathLike, command: str, timeout: float | None = None) -> subprocess.CompletedProcess[str]:
    """Run a command through the platform shell, with no real jail.

    Problems, all of them deliberate:

    * ``shell=True`` lets one tool call become many commands (``;``, ``&&``).
    * The parent environment is inherited, including secrets such as API keys.
    * ``timeout`` defaults to ``None``: a command may run forever.
    * Output is captured completely in memory, so a noisy command can exhaust
      the agent process before anyone reads the result.
    * There is no CPU, memory, process or file-size limit.

    Chapter 3 replaces this with an argv-based runner. Chapter 4 moves the
    whole thing into a container.
    """
    return subprocess.run(
        command,
        shell=True,
        cwd=os.fspath(root),
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )
