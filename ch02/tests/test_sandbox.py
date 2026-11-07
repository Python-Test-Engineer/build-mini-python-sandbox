"""Tests for the Stage 2 sandbox and file-tool observation layer.

Run from ``ch02/``:

    python -m pytest -v

There are two layers under test:

* ``Sandbox`` - the policy-checked file operations. It raises ``SandboxError``
  with a stable ``code`` when something is refused or fails.
* ``run_tool`` - the model-facing adapter. It must catch those errors and
  return *strings*, because an agent loop should never crash on a bad tool
  call.

Most tests aim at one specific rule, so when one fails you can read its name
and know which contract broke.
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
        # Private temporary root: every test starts from an identical workspace.
        self.temp = self.enterContext(tempfile.TemporaryDirectory(prefix="sandbox-test-"))
        self.root = Path(self.temp) / "workspace"
        self.root.mkdir()

        # Fixtures used by reads, listings and edits.
        (self.root / "notes.txt").write_bytes(b"alpha\nbeta\n")
        (self.root / "src").mkdir()
        (self.root / "src" / "app.py").write_bytes(b"print('hi')\n")

        # A file outside the workspace for escape tests.
        self.outside = Path(self.temp) / "outside.txt"
        self.outside.write_text("outside\n", encoding="utf-8")

        self.sandbox = Sandbox(self.root)

    # -- reads -------------------------------------------------------------

    def test_read_text(self) -> None:
        """Reading a normal text file returns the exact decoded contents."""
        self.assertEqual(self.sandbox.read_text("notes.txt"), "alpha\nbeta\n")

    def test_read_preserves_crlf(self) -> None:
        """Reads must not silently translate CRLF line endings.

        We read bytes and decode them ourselves so the model sees the file as it
        really is. Text-mode translation would rewrite ``\\r\\n`` and change the
        data a tool later edits.
        """
        (self.root / "crlf.txt").write_bytes(b"a\r\nb\r\n")
        self.assertEqual(self.sandbox.read_text("crlf.txt"), "a\r\nb\r\n")

    def test_read_missing(self) -> None:
        """A missing file is a ``NOT_FOUND`` error, not an OS traceback.

        Stable codes let the tool layer explain the problem to the model without
        leaking Python exception classes.
        """
        with self.assertRaises(SandboxError) as caught:
            self.sandbox.read_text("missing.txt")
        self.assertEqual(caught.exception.code, "NOT_FOUND")

    def test_read_directory(self) -> None:
        """Reading a directory as text is refused with ``IS_DIR``."""
        with self.assertRaises(SandboxError) as exc:
            self.sandbox.read_text("src")
        self.assertEqual(exc.exception.code, "IS_DIR")

    def test_read_too_large(self) -> None:
        """The byte limit is enforced before the whole file is consumed.

        A tiny limit proves the cap works without allocating a large test file.
        ``TOO_LARGE`` is a policy decision, separate from any OS error.
        """
        limited = Sandbox(self.root, limits=Limits(max_read_bytes=3))
        with self.assertRaises(SandboxError) as exc:
            limited.read_text("notes.txt")
        self.assertEqual(exc.exception.code, "TOO_LARGE")

    def test_read_escape(self) -> None:
        """A read outside the workspace becomes a ``PATH`` refusal.

        This checks that the sandbox delegates to the path policy and re-labels
        the failure with its own stable code.
        """
        with self.assertRaises(SandboxError) as exc:
            self.sandbox.read_text("../outside.txt")
        self.assertEqual(exc.exception.code, "PATH")

    # -- listings ----------------------------------------------------------

    def test_list_dir(self) -> None:
        """Listings are sorted and say whether each entry is a file or dir.

        Sorting makes output deterministic for tests and prompts. The ``kind``
        field saves the model from guessing based only on a name.
        """
        entries = self.sandbox.list_dir(".")
        names = [entry.name for entry in entries]
        self.assertEqual(names, ["notes.txt", "src"])

        kinds = {entry.name: entry.kind for entry in entries}
        self.assertEqual(kinds["src"], "dir")
        self.assertEqual(kinds["notes.txt"], "file")

    def test_list_is_sorted_and_capped(self) -> None:
        """The entry cap stops a huge directory from flooding the transcript.

        With two entries and a limit of one, we expect exactly one result.
        """
        limited = Sandbox(self.root, limits=Limits(max_dir_entries=1))
        entries = limited.list_dir(".")
        self.assertEqual(len(entries), 1)

    def test_list_file_rejected(self) -> None:
        """Listing a regular file is a ``NOT_DIR`` error."""
        with self.assertRaises(SandboxError) as exc:
            self.sandbox.list_dir("notes.txt")
        self.assertEqual(exc.exception.code, "NOT_DIR")

    # -- writes ------------------------------------------------------------

    def test_write_and_read_back(self) -> None:
        """Writes create missing parent directories and can be read back."""
        self.sandbox.write_text("new/file.txt", "hello\n")
        self.assertEqual(self.sandbox.read_text("new/file.txt"), "hello\n")

    def test_write_is_atomic_and_leaves_no_temp(self) -> None:
        """Writes go through a temp file that is cleaned up on success.

        Atomic writes prevent a crash from leaving a half-written file. The
        test also confirms the temporary file is not left lying in the
        workspace after the rename.
        """
        self.sandbox.write_text("new/file.txt", "hello\n")
        leftovers = list(self.root.rglob(".sandbox-*.tmp"))
        self.assertEqual(leftovers, [])

    def test_write_create_only(self) -> None:
        """``overwrite=False`` fails with ``EXISTS`` instead of clobbering.

        Create-only mode is what lets a tool avoid destroying an existing file
        when the model believes it is making a new one.
        """
        with self.assertRaises(SandboxError) as exc:
            self.sandbox.write_text("notes.txt", "replace\n", overwrite=False)
        self.assertEqual(exc.exception.code, "EXISTS")

    def test_write_to_directory_rejected(self) -> None:
        """A write whose target is a directory is refused with ``IS_DIR``."""
        with self.assertRaises(SandboxError) as exc:
            self.sandbox.write_text("src", "x")
        self.assertEqual(exc.exception.code, "IS_DIR")

    def test_write_too_large(self) -> None:
        """Writes above the byte limit are refused before touching the disk."""
        limited = Sandbox(self.root, limits=Limits(max_write_bytes=3))
        with self.assertRaises(SandboxError) as exc:
            limited.write_text("x.txt", "four")
        self.assertEqual(exc.exception.code, "TOO_LARGE")

    def test_write_escape(self) -> None:
        """A write outside the workspace is a ``PATH`` refusal."""
        with self.assertRaises(SandboxError) as exc:
            self.sandbox.write_text("../escape.txt", "x")
        self.assertEqual(exc.exception.code, "PATH")

    # -- edits -------------------------------------------------------------

    def test_edit_unique(self) -> None:
        """An edit replaces exactly one unique occurrence and persists it.

        We check both the returned text and a fresh read, proving the change was
        actually written rather than only returned.
        """
        updated = self.sandbox.edit_text("notes.txt", "alpha", "alpha2")
        self.assertEqual(updated, "alpha2\nbeta\n")
        self.assertEqual(self.sandbox.read_text("notes.txt"), "alpha2\nbeta\n")

    def test_edit_missing_text(self) -> None:
        """Editing text that is not present fails with ``NO_MATCH``.

        The model gets a clear reason instead of a silent no-op.
        """
        with self.assertRaises(SandboxError) as exc:
            self.sandbox.edit_text("notes.txt", "gamma", "delta")
        self.assertEqual(exc.exception.code, "NO_MATCH")

    def test_edit_ambiguous_text(self) -> None:
        """Repeated old text is refused unless the caller opts into ``count=0``.

        Ambiguity is dangerous: replacing "the first match" may change the wrong
        place. The default is therefore to refuse with ``AMBIGUOUS``.
        """
        (self.root / "repeat.txt").write_bytes(b"x\nx\n")
        with self.assertRaises(SandboxError) as exc:
            self.sandbox.edit_text("repeat.txt", "x", "y")
        self.assertEqual(exc.exception.code, "AMBIGUOUS")

    def test_edit_replace_all(self) -> None:
        """``count=0`` explicitly means "replace every occurrence"."""
        (self.root / "repeat.txt").write_bytes(b"x\nx\n")
        updated = self.sandbox.edit_text("repeat.txt", "x", "y", count=0)
        self.assertEqual(updated, "y\ny\n")

    # -- deletes -----------------------------------------------------------

    def test_delete_file(self) -> None:
        """Deleting a regular file removes it from disk."""
        self.sandbox.delete_file("notes.txt")
        self.assertFalse((self.root / "notes.txt").exists())

    def test_delete_directory_rejected(self) -> None:
        """Directories are not deleted by the file tool (``IS_DIR``).

        Recursive deletion is a separate, much more dangerous operation and is
        deliberately not part of this small tool set.
        """
        with self.assertRaises(SandboxError) as exc:
            self.sandbox.delete_file("src")
        self.assertEqual(exc.exception.code, "IS_DIR")

    def test_delete_missing(self) -> None:
        """Deleting a missing file is ``NOT_FOUND``, not a crash."""
        with self.assertRaises(SandboxError) as exc:
            self.sandbox.delete_file("missing.txt")
        self.assertEqual(exc.exception.code, "NOT_FOUND")

    # -- symlinks ----------------------------------------------------------

    def test_symlink_write_rejected(self) -> None:
        """Writing through a symlink is refused to prevent redirected overwrites.

        The link sits inside the workspace but points outside. A normal path
        check would allow the name; the sandbox refuses symlink targets on
        writes specifically.
        """
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
        # The tool layer is tested against the same kind of private workspace.
        self.temp = self.enterContext(tempfile.TemporaryDirectory(prefix="tools-test-"))
        self.root = Path(self.temp) / "workspace"
        self.root.mkdir()
        (self.root / "notes.txt").write_bytes(b"alpha\nbeta\n")
        self.sandbox = Sandbox(self.root)

    def test_list_files_observation(self) -> None:
        """A successful listing is a human-readable string for the model."""
        result = run_tool(self.sandbox, "list_files", {"path": "."})
        self.assertIn("file notes.txt", result)

    def test_read_file_has_line_numbers(self) -> None:
        """Reads are rendered with line numbers so the model can refer to lines.

        ``old_text`` edits become easier to target when the model can see the
        same numbering it uses when talking about the file.
        """
        result = run_tool(self.sandbox, "read_file", {"path": "notes.txt"})
        self.assertIn("1 | alpha", result)
        self.assertIn("2 | beta", result)

    def test_read_empty_file(self) -> None:
        """An empty file produces a clear marker instead of a blank string.

        A blank observation is ambiguous (did the read work?). The explicit
        ``(empty file)`` text avoids that confusion.
        """
        (self.root / "empty.txt").write_bytes(b"")
        result = run_tool(self.sandbox, "read_file", {"path": "empty.txt"})
        self.assertEqual(result, "(empty file)")

    def test_write_observation(self) -> None:
        """A successful write reports the byte count and target name."""
        result = run_tool(
            self.sandbox,
            "write_file",
            {"path": "new.txt", "content": "hello"},
        )
        self.assertEqual(result, "OK: wrote 5 bytes to new.txt")

    def test_edit_observation(self) -> None:
        """A successful edit is reported as an ``OK: edited ...`` line."""
        result = run_tool(
            self.sandbox,
            "edit_file",
            {"path": "notes.txt", "old_text": "alpha", "new_text": "gamma"},
        )
        self.assertIn("OK: edited notes.txt", result)

    def test_delete_observation(self) -> None:
        """A successful delete is reported with the removed file name."""
        result = run_tool(self.sandbox, "delete_file", {"path": "notes.txt"})
        self.assertEqual(result, "OK: deleted notes.txt")

    def test_unknown_tool(self) -> None:
        """Unknown tool names become ``ERROR[UNKNOWN_TOOL]`` observations.

        The model can call any name in its prompt, including typos. A visible
        error keeps the loop alive and teaches the model what failed.
        """
        result = run_tool(self.sandbox, "nope", {})
        self.assertTrue(result.startswith("ERROR[UNKNOWN_TOOL]"))

    def test_missing_argument(self) -> None:
        """Missing required arguments become ``ERROR[ARGS]``, not a KeyError."""
        result = run_tool(self.sandbox, "read_file", {})
        self.assertIn("ERROR[ARGS]", result)

    def test_path_error_is_observation(self) -> None:
        """A policy refusal is rendered as a readable observation string.

        This is the key contract of the adapter: a denied escape must look like
        normal tool output so the agent loop can continue and react to it.
        """
        result = run_tool(self.sandbox, "read_file", {"path": "../outside.txt"})
        self.assertEqual(result, "ERROR[PATH]: path escapes workspace: ../outside.txt")

    def test_internal_error_is_observation(self) -> None:
        """Arguments of the wrong type are rejected before any I/O happens.

        ``read_file`` with a non-string path is caught by argument checking, not
        by an exception escaping the tool. The model sees ``ERROR[ARGS]``.
        """
        result = run_tool(self.sandbox, "read_file", {"path": 42})
        self.assertIn("ERROR[ARGS]", result)


if __name__ == "__main__":
    unittest.main()
