"""Tests for the Stage 1 path policy.

Run from ``ch01/``:

    python -m pytest -v

The tests cover the cases that make path handling hard: symlinks, Windows
drive and UNC forms, reserved names, and the difference between a lexical
prefix check and a real filesystem boundary. Tests that need symlink support
skip themselves on platforms where creating a link is not permitted.
"""

from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from mini_harness.path_policy import (  # noqa: E402
    PathPolicy,
    PolicyError,
    expand_variables,
)


class PathPolicyTests(unittest.TestCase):
    """Each test gets a fresh workspace and a sibling outside it."""

    def setUp(self) -> None:
        self.temp = self.enterContext(tempfile.TemporaryDirectory(prefix="policy-test-"))
        self.base = Path(self.temp)
        self.workspace = self.base / "workspace"
        self.workspace.mkdir()
        (self.workspace / "notes.txt").write_text("inside\n", encoding="utf-8")
        (self.workspace / "sub").mkdir()
        (self.workspace / "sub" / "nested.txt").write_text("nested\n", encoding="utf-8")
        self.outside = self.base / "outside.txt"
        self.outside.write_text("outside\n", encoding="utf-8")
        self.sibling = self.base / "workspace-evil"
        self.sibling.mkdir()
        (self.sibling / "secret.txt").write_text("sibling\n", encoding="utf-8")
        self.policy = PathPolicy(self.workspace)

    def make_symlink(self, target: str, link_name: str) -> None:
        """Create a symlink or skip the test when the OS refuses."""
        try:
            os.symlink(target, self.workspace / link_name)
        except (OSError, NotImplementedError) as exc:
            self.skipTest(f"symlinks unavailable: {exc}")

    def test_inside_read(self) -> None:
        resolved = self.policy.resolve_read("notes.txt")
        self.assertEqual(resolved.relative, "notes.txt")
        self.assertEqual(resolved.absolute, (self.workspace / "notes.txt").resolve())

    def test_nested_read(self) -> None:
        resolved = self.policy.resolve_read("sub/nested.txt")
        self.assertEqual(resolved.relative, "sub/nested.txt")

    def test_dotdot_rejected(self) -> None:
        with self.assertRaises(PolicyError):
            self.policy.resolve_read("../outside.txt")

    def test_prefix_sibling_rejected(self) -> None:
        with self.assertRaises(PolicyError):
            self.policy.resolve_read("../sibling/secret.txt")

    def test_absolute_inside_allowed(self) -> None:
        resolved = self.policy.resolve_read(str(self.workspace / "notes.txt"))
        self.assertEqual(resolved.relative, "notes.txt")

    def test_absolute_outside_rejected(self) -> None:
        with self.assertRaises(PolicyError):
            self.policy.resolve_read(str(self.outside))

    def test_symlink_file_outside_rejected(self) -> None:
        self.make_symlink(str(self.outside), "leak.txt")
        with self.assertRaises(PolicyError):
            self.policy.resolve_read("leaky-link.txt")

    def test_symlink_directory_outside_rejected(self) -> None:
        outside_dir = self.base / "outside-dir"
        outside_dir.mkdir()
        (outside_dir / "secret.txt").write_text("x\n", encoding="utf-8")
        self.make_symlink(str(outside_dir), "outside-dir-link")
        with self.assertRaises(PolicyError):
            self.policy.resolve_read("outside-dir-link/secret.txt")

    def test_symlink_inside_is_readable(self) -> None:
        self.make_symlink(str(self.workspace / "notes.txt"), "inside-link.txt")
        resolved = self.policy.resolve_read("inside-link.txt")
        self.assertEqual(resolved.relative, "notes.txt")

    def test_write_relative_allowed(self) -> None:
        resolved = self.policy.resolve_write("new.txt")
        self.assertEqual(resolved.relative, "new.txt")

    def test_write_creates_no_file_by_itself(self) -> None:
        self.policy.resolve_write("does-not-exist.txt")
        self.assertFalse((self.workspace / "does-not-exist.txt").exists())

    def test_write_nested_nonexistent_allowed(self) -> None:
        resolved = self.policy.resolve_write("deep/new/file.txt")
        self.assertEqual(resolved.relative, "deep/new/file.txt")

    def test_write_absolute_rejected(self) -> None:
        with self.assertRaises(PolicyError):
            self.policy.resolve_write(str(self.outside))

    def test_write_dotdot_rejected(self) -> None:
        with self.assertRaises(PolicyError):
            self.policy.resolve_write("../outside.txt")

    def test_write_symlink_rejected(self) -> None:
        self.make_symlink(str(self.outside), "write-link.txt")
        with self.assertRaises(PolicyError):
            self.policy.resolve_write("write-link.txt")

    def test_write_root_rejected(self) -> None:
        with self.assertRaises(PolicyError):
            self.policy.resolve_write(".")

    def test_reserved_names_rejected(self) -> None:
        for name in ("CON", "con.txt", "NUL", "LPT1.log"):
            with self.subTest(name=name):
                with self.assertRaises(PolicyError):
                    self.policy.resolve_write(name)

    def test_control_character_rejected(self) -> None:
        with self.assertRaises(PolicyError):
            self.policy.resolve_read("bad\x00name")

    def test_alternate_data_stream_rejected(self) -> None:
        # ``file.txt:stream`` is an NTFS alternate data stream on Windows and
        # an ambiguous name elsewhere. Refuse it consistently.
        with self.assertRaises(PolicyError):
            self.policy.resolve_write("notes.txt:hidden")

    def test_unc_rejected(self) -> None:
        with self.assertRaises(PolicyError):
            self.policy.resolve_read(r"\\server\share\file")

    def test_drive_relative_rejected(self) -> None:
        with self.assertRaises(PolicyError):
            self.policy.resolve_read(r"C:temp\file")

    def test_empty_rejected(self) -> None:
        with self.assertRaises(PolicyError):
            self.policy.resolve_read("   ")

    def test_backslash_traversal_rejected_everywhere(self) -> None:
        with self.assertRaises(PolicyError):
            self.policy.resolve_read(r"..\outside.txt")

    def test_is_inside(self) -> None:
        self.assertTrue(self.policy.is_inside(self.workspace / "notes.txt"))
        self.assertFalse(self.policy.is_inside(self.outside))

    def test_relative_format_uses_forward_slashes(self) -> None:
        resolved = self.policy.resolve_read("sub/nested.txt")
        self.assertNotIn("\\", resolved.relative)

    def test_expand_variables(self) -> None:
        env = {"HOME": "/home/demo", "USERPROFILE": r"C:\Users\demo", "NAME": "x"}
        self.assertEqual(expand_variables("$NAME/file", env), "x/file")
        self.assertEqual(expand_variables("${NAME}/file", env), "x/file")
        self.assertEqual(expand_variables("%NAME%/file", env), "x/file")
        self.assertEqual(expand_variables("$MISSING/file", env), "$MISSING/file")


if __name__ == "__main__":
    import unittest as _unittest

    _unittest.main()
