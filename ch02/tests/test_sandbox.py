"""Tests for the Stage 2 sandbox and file-tool observation layer.

Run from ``ch02/``:

    python -m pytest -v
"""

from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from mini_harness.file_tools import run_tool
from mini_harness.sandbox import Limits, Sandbox, SandboxError


class SandboxTests(unittest.TestCase):
    """Each test gets a fresh root so files cannot leak between tests."""

    def setUp(self) -> None:
        self.temp = self.enterContext(tempfile.TemporaryDirectory(prefix="sandbox-test-"))
        self.root = Path(self.temp) / "workspace"
        self.root.mkdir()
        (self.root / "notes.txt").write_bytes(b"alpha\nbeta\n")
        (self.root / "src").mkdir()
        (self.root / "src" / "app.py").write_bytes(b"print('hi')\n")
        self.outside = Path(self.temp) / "outside.txt"
        self.outside.write_text("outside\n", encoding="utf-8")
        self.sandbox = Sandbox(self.root)

    def test_read_text(self) -> None:
        self.assertEqual(self.sandbox.read_text("notes.txt"), "alpha\nbeta\n")

    def test_read_preserves_crlf(self) -> None:
        (self.root / "crlf.txt").write_bytes(b"a\r\nb\r\n")
        self.assertEqual(self.sandbox.read_text("crlf.txt"), "a\r\nb\r\n")

    def test_read_missing(self) -> None:
        with self.assertRaises(SandboxError) as caught:
            self.sandbox.read_text("missing.txt")
        self.assertEqual(caught.exception.code, "NOT_FOUND")

    def test_read_directory(self) -> None:
        with self.assertRaises(SandboxError) as exc:
            self.sandbox.read_text("src")
        self.assertEqual(exc.exception.code, "IS_DIR")

    def test_read_too_large(self) -> None:
        limited = Sandbox(self.root, limits=Limits(max_read_bytes=3))
        with self.assertRaises(SandboxError) as exc:
            limited.read_text("notes.txt")
        self.assertEqual(exc.exception.code, "TOO_LARGE")

    def test_read_escape(self) -> None:
        with self.assertRaises(SandboxError) as exc:
            self.sandbox.read_text("../outside.txt")
        self.assertEqual(exc.exception.code, "PATH")

    def test_list_dir(self) -> None:
        entries = self.sandbox.list_dir(".")
        names = [entry.name for entry in entries]
        self.assertEqual(names, ["notes.txt", "src"])
        kinds = {entry.name: entry.kind for entry in entries}
        self.assertEqual(kinds["src"], "dir")
        self.assertEqual(kinds["notes.txt"], "file")

    def test_list_is_sorted_and_capped(self) -> None:
        limited = Sandbox(self.root, limits=Limits(max_dir_entries=1))
        entries = limited.list_dir(".")
        self.assertEqual(len(entries), 1)

    def test_list_file_rejected(self) -> None:
        with self.assertRaises(SandboxError) as exc:
            self.sandbox.list_dir("notes.txt")
        self.assertEqual(exc.exception.code, "NOT_DIR")

    def test_write_and_read_back(self) -> None:
        self.sandbox.write_text("new/file.txt", "hello\n")
        self.assertEqual(self.sandbox.read_text("new/file.txt"), "hello\n")

    def test_write_is_atomic_and_leaves_no_temp(self) -> None:
        self.sandbox.write_text("new/file.txt", "hello\n")
        leftovers = list(self.root.rglob(".sandbox-*.tmp"))
        self.assertEqual(leftovers, [])

    def test_write_create_only(self) -> None:
        with self.assertRaises(SandboxError) as exc:
            self.sandbox.write_text("notes.txt", "replace\n", overwrite=False)
        self.assertEqual(exc.exception.code, "EXISTS")

    def test_write_to_directory_rejected(self) -> None:
        with self.assertRaises(SandboxError) as exc:
            self.sandbox.write_text("src", "x")
        self.assertEqual(exc.exception.code, "IS_DIR")

    def test_write_too_large(self) -> None:
        limited = Sandbox(self.root, limits=Limits(max_write_bytes=3))
        with self.assertRaises(SandboxError) as exc:
            limited.write_text("x.txt", "four")
        self.assertEqual(exc.exception.code, "TOO_LARGE")

    def test_write_escape(self) -> None:
        with self.assertRaises(SandboxError) as exc:
            self.sandbox.write_text("../escape.txt", "x")
        self.assertEqual(exc.exception.code, "PATH")

    def test_edit_unique(self) -> None:
        updated = self.sandbox.edit_text("notes.txt", "alpha", "alpha2")
        self.assertEqual(updated, "alpha2\nbeta\n")
        self.assertEqual(self.sandbox.read_text("notes.txt"), "alpha2\nbeta\n")

    def test_edit_missing_text(self) -> None:
        with self.assertRaises(SandboxError) as exc:
            self.sandbox.edit_text("notes.txt", "gamma", "delta")
        self.assertEqual(exc.exception.code, "NO_MATCH")

    def test_edit_ambiguous_text(self) -> None:
        (self.root / "repeat.txt").write_bytes(b"x\nx\n")
        with self.assertRaises(SandboxError) as exc:
            self.sandbox.edit_text("repeat.txt", "x", "y")
        self.assertEqual(exc.exception.code, "AMBIGUOUS")

    def test_edit_replace_all(self) -> None:
        (self.root / "repeat.txt").write_bytes(b"x\nx\n")
        updated = self.sandbox.edit_text("repeat.txt", "x", "y", count=0)
        self.assertEqual(updated, "y\ny\n")

    def test_delete_file(self) -> None:
        self.sandbox.delete_file("notes.txt")
        self.assertFalse((self.root / "notes.txt").exists())

    def test_delete_directory_rejected(self) -> None:
        with self.assertRaises(SandboxError) as exc:
            self.sandbox.delete_file("src")
        self.assertEqual(exc.exception.code, "IS_DIR")

    def test_delete_missing(self) -> None:
        with self.assertRaises(SandboxError) as exc:
            self.sandbox.delete_file("missing.txt")
        self.assertEqual(exc.exception.code, "NOT_FOUND")

    def test_symlink_write_rejected(self) -> None:
        link = self.root / "link.txt"
        try:
            os.symlink(self.outside, link)
        except (OSError, NotImplementedError) as exc:
            self.skipTest(f"symlinks unavailable: {exc}")
        with self.assertRaises(SandboxError) as caught:
            self.sandbox.write_text("link.txt", "x")
        self.assertEqual(caught.exception.code, "PATH")


class FileToolTests(unittest.TestCase):
    """The tool layer must return strings, never raise for expected failures."""

    def setUp(self) -> None:
        self.temp = self.enterContext(tempfile.TemporaryDirectory(prefix="tools-test-"))
        self.root = Path(self.temp) / "workspace"
        self.root.mkdir()
        (self.root / "notes.txt").write_bytes(b"alpha\nbeta\n")
        self.sandbox = Sandbox(self.root)

    def test_list_files_observation(self) -> None:
        result = run_tool(self.sandbox, "list_files", {"path": "."})
        self.assertIn("file notes.txt", result)

    def test_read_file_has_line_numbers(self) -> None:
        result = run_tool(self.sandbox, "read_file", {"path": "notes.txt"})
        self.assertIn("1 | alpha", result)
        self.assertIn("2 | beta", result)

    def test_read_empty_file(self) -> None:
        (self.root / "empty.txt").write_bytes(b"")
        result = run_tool(self.sandbox, "read_file", {"path": "empty.txt"})
        self.assertEqual(result, "(empty file)")

    def test_write_observation(self) -> None:
        result = run_tool(
            self.sandbox,
            "write_file",
            {"path": "new.txt", "content": "hello"},
        )
        self.assertEqual(result, "OK: wrote 5 bytes to new.txt")

    def test_edit_observation(self) -> None:
        result = run_tool(
            self.sandbox,
            "edit_file",
            {"path": "notes.txt", "old_text": "alpha", "new_text": "gamma"},
        )
        self.assertIn("OK: edited notes.txt", result)

    def test_delete_observation(self) -> None:
        result = run_tool(self.sandbox, "delete_file", {"path": "notes.txt"})
        self.assertEqual(result, "OK: deleted notes.txt")

    def test_unknown_tool(self) -> None:
        result = run_tool(self.sandbox, "nope", {})
        self.assertTrue(result.startswith("ERROR[UNKNOWN_TOOL]"))

    def test_missing_argument(self) -> None:
        result = run_tool(self.sandbox, "read_file", {})
        self.assertIn("ERROR[ARGS]", result)

    def test_path_error_is_observation(self) -> None:
        result = run_tool(self.sandbox, "read_file", {"path": "../outside.txt"})
        self.assertEqual(result, "ERROR[PATH]: path escapes workspace: ../outside.txt")

    def test_internal_error_is_observation(self) -> None:
        # ``read_file`` with a non-string path is rejected by argument checking,
        # not by an exception escaping the tool.
        result = run_tool(self.sandbox, "read_file", {"path": 42})
        self.assertIn("ERROR[ARGS]", result)


if __name__ == "__main__":
    unittest.main()
