"""Tests that document the broken behaviour of Stage 0.

The tests pass because they assert the *known* bad outcomes. That sounds
backwards, but it is useful: the suite is an executable threat model. When
chapter 1 changes the policy, these expectations are replaced by the opposite
ones ("the escape must be refused").

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
        self.workspace = self.base / "workspace"
        self.workspace.mkdir()
        (self.workspace / "notes.txt").write_text("inside\n", encoding="utf-8")

    def test_inside_read_still_works(self) -> None:
        """The fence should not be so strict that normal work fails."""
        self.assertEqual(read_file(self.workspace, "notes.txt"), "inside\n")

    def test_plain_dotdot_is_blocked(self) -> None:
        """abspath collapses ``..``, so the simple attack is caught."""
        outside = self.base / "outside.txt"
        outside.write_text("secret\n", encoding="utf-8")
        with self.assertRaises(ValueError):
            read_file(self.workspace, "../outside.txt")

    def test_prefix_sibling_escapes(self) -> None:
        """``workspace-evil`` passes ``startswith("workspace")``."""
        sibling = self.base / "workspace-evil"
        sibling.mkdir()
        (sibling / "secret.txt").write_text("sibling secret\n", encoding="utf-8")

        leaked = read_file(self.workspace, "../workspace-evil/secret.txt")
        self.assertEqual(leaked, "sibling secret\n")

    def test_symlink_escape(self) -> None:
        """A symlink inside the workspace can point anywhere."""
        outside = self.base / "outside-secret.txt"
        outside.write_text("outside secret\n", encoding="utf-8")
        link = self.workspace / "link.txt"
        try:
            os.symlink(outside, link)
        except (OSError, NotImplementedError) as exc:
            self.skipTest(f"symlinks unavailable on this machine: {exc}")

        leaked = read_file(self.workspace, "link.txt")
        self.assertEqual(leaked, "outside secret\n")

    def test_shell_runs_without_a_jail(self) -> None:
        """A shell command runs, inherits the environment and has no timeout."""
        completed = run_shell(self.workspace, "echo hello")
        self.assertEqual(completed.returncode, 0)
        self.assertIn("hello", completed.stdout)


if __name__ == "__main__":
    unittest.main()
