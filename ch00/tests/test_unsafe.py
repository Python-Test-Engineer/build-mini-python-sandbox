"""Tests that document the broken behaviour of Stage 0.

The tests pass because they assert the *known* bad outcomes. That sounds
backwards, but it is useful: the suite is an executable threat model. When
chapter 1 changes the policy, these expectations are replaced by the opposite
ones ("the escape must be refused").

Read these tests top to bottom as a list of attacks that a naive file tool
does not stop. Each one shows:

* what the attacker (or a confused model) asks for,
* what actually happens in Stage 0, and
* why the behaviour is unsafe.

Run from ``ch00/``:

    python -m pytest -v
"""

from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

# Make the chapter root importable when unittest is started from anywhere.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from mini_harness.unsafe import read_file, run_shell  # noqa: E402


class NaiveFenceTests(unittest.TestCase):
    """Each test creates its own tiny lab so tests cannot interfere."""

    def setUp(self) -> None:
        # ``enterContext`` is available in Python 3.11+ and cleans up even if
        # the test fails. The project targets 3.11 or newer.
        self.temp = self.enterContext(tempfile.TemporaryDirectory(prefix="sandbox-test-"))
        self.base = Path(self.temp)

        # A workspace holds files the model is *supposed* to see.
        self.workspace = self.base / "workspace"
        self.workspace.mkdir()
        (self.workspace / "notes.txt").write_text("inside\n", encoding="utf-8")

    def test_inside_read_still_works(self) -> None:
        """The fence should not be so strict that normal work fails.

        This is a "control" test: before proving that bad reads escape, we
        confirm the happy path works. A security fix that breaks ordinary file
        access is not a good fix, so this expectation survives every chapter.
        """
        self.assertEqual(read_file(self.workspace, "notes.txt"), "inside\n")

    def test_plain_dotdot_is_blocked(self) -> None:
        """abspath collapses ``..``, so the simple attack is caught.

        ``read_file`` calls ``os.path.abspath``, which turns
        ``workspace/../outside.txt`` into the real sibling path. The naive
        ``startswith(workspace)`` check then fails, so this attack is refused.
        Keep this test passing: it is the *minimum* bar, not the full solution.
        """
        outside = self.base / "outside.txt"
        outside.write_text("secret\n", encoding="utf-8")

        # The attacker asks for a parent-relative path; we expect a refusal.
        with self.assertRaises(ValueError):
            read_file(self.workspace, "../outside.txt")

    def test_prefix_sibling_escapes(self) -> None:
        """``workspace-evil`` passes ``startswith("workspace")``.

        This is the first real flaw. The check is a *string prefix* test on the
        path, and a sibling directory whose name merely starts with
        ``workspace`` shares that prefix. The read succeeds and leaks a file
        that was never in the workspace.

        The test asserts the bad outcome on purpose: Stage 0 is the "before"
        picture. Chapter 1 replaces this test with an ``assertRaises`` version.
        """
        sibling = self.base / "workspace-evil"
        sibling.mkdir()
        (sibling / "secret.txt").write_text("sibling secret\n", encoding="utf-8")

        # Notice the leak: this returns data from outside the workspace.
        leaked = read_file(self.workspace, "../workspace-evil/secret.txt")
        self.assertEqual(leaked, "sibling secret\n")

    def test_symlink_escape(self) -> None:
        """A symlink inside the workspace can point anywhere.

        A name-only check cannot see where a link leads. ``link.txt`` lives in
        the workspace, so any lexical test passes, but the OS follows it to a
        file outside. Only resolving the *real* path (``realpath``) catches
        this.
        """
        outside = self.base / "outside-secret.txt"
        outside.write_text("outside secret\n", encoding="utf-8")
        link = self.workspace / "link.txt"

        try:
            os.symlink(outside, link)
        except (OSError, NotImplementedError) as exc:
            # Windows may need Developer Mode or admin rights for symlinks.
            # Skipping keeps the suite green without pretending the attack
            # was tested.
            self.skipTest(f"symlinks unavailable on this machine: {exc}")

        # The link name is inside the workspace, but the data is outside.
        leaked = read_file(self.workspace, "link.txt")
        self.assertEqual(leaked, "outside secret\n")

    def test_shell_runs_without_a_jail(self) -> None:
        """A shell command runs, inherits the environment and has no timeout.

        Stage 0 does not sandbox commands at all. It uses the host shell, so
        the child sees the parent's environment (including any API keys) and
        can run forever. Later chapters replace this with an argv allowlist, a
        scrubbed environment, a timeout and (in chapter 4) a container.
        """
        completed = run_shell(self.workspace, "echo hello")

        # The command succeeds, proving there is no policy in front of it.
        self.assertEqual(completed.returncode, 0)
        self.assertIn("hello", completed.stdout)


if __name__ == "__main__":
    unittest.main()
