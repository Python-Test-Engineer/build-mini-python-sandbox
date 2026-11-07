"""Tests for the Stage 1 path policy.

Run from ``ch01/``:

    python -m pytest -v

The tests cover the cases that make path handling hard: symlinks, Windows
drive and UNC forms, reserved names, and the difference between a lexical
prefix check and a real filesystem boundary. Tests that need symlink support
skip themselves on platforms where creating a link is not permitted.

How to read these tests
-----------------------
Almost every test follows the same shape:

1. ``setUp`` creates a workspace plus decoy files *outside* it.
2. The test asks ``PathPolicy`` to resolve a name.
3. The test asserts either that a safe name was accepted, or that a dangerous
   name raised ``PolicyError``.

The important habit is that a refusal must be a ``PolicyError``, not a random
``FileNotFoundError``. A stable error type is what lets tools turn a refusal
into a visible, non-crashing observation for the model.
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
        # A private temporary directory makes the "outside" files real but
        # harmless, and guarantees one test cannot see another test's files.
        self.temp = self.enterContext(tempfile.TemporaryDirectory(prefix="policy-test-"))
        self.base = Path(self.temp)

        # The workspace: the only directory the policy should ever allow.
        self.workspace = self.base / "workspace"
        self.workspace.mkdir()
        (self.workspace / "notes.txt").write_text("inside\n", encoding="utf-8")
        (self.workspace / "sub").mkdir()
        (self.workspace / "sub" / "nested.txt").write_text("nested\n", encoding="utf-8")

        # Dangerous neighbours used by the escape tests.
        self.outside = self.base / "outside.txt"
        self.outside.write_text("outside\n", encoding="utf-8")

        # A sibling whose name *starts with* the workspace name. It is the
        # classic victim of a naive ``startswith(workspace)`` check.
        self.sibling = self.base / "workspace-evil"
        self.sibling.mkdir()
        (self.sibling / "secret.txt").write_text("sibling\n", encoding="utf-8")

        self.policy = PathPolicy(self.workspace)

    def make_symlink(self, target: str, link_name: str) -> None:
        """Create a symlink or skip the test when the OS refuses.

        Symlinks are central to the threat model, but some Windows setups
        disallow creating them without extra privileges. Skipping (instead of
        failing) keeps the suite usable on those machines while making the
        missing coverage visible in the pytest summary.
        """
        try:
            os.symlink(target, self.workspace / link_name)
        except (OSError, NotImplementedError) as exc:
            self.skipTest(f"symlinks unavailable: {exc}")

    # -- basic containment -------------------------------------------------

    def test_inside_read(self) -> None:
        """A plain relative name inside the workspace is accepted.

        We assert both the model-facing ``relative`` form (forward slashes,
        no leading ``./``) and the canonical ``absolute`` path. Tools open the
        absolute path; logs show the relative one.
        """
        resolved = self.policy.resolve_read("notes.txt")
        self.assertEqual(resolved.relative, "notes.txt")
        self.assertEqual(resolved.absolute, (self.workspace / "notes.txt").resolve())

    def test_nested_read(self) -> None:
        """Nested names work and keep their relative sub-path.

        Containment must still allow normal directories underneath the root;
        the policy only cares that the final real path stays inside.
        """
        resolved = self.policy.resolve_read("sub/nested.txt")
        self.assertEqual(resolved.relative, "sub/nested.txt")

    def test_dotdot_rejected(self) -> None:
        """``..`` must never climb out of the workspace.

        The policy resolves the real path and checks containment. Any attempt
        to leave via a parent reference is refused with ``PolicyError``.
        """
        with self.assertRaises(PolicyError):
            self.policy.resolve_read("../outside.txt")

    def test_prefix_sibling_rejected(self) -> None:
        """A sibling called ``workspace-evil`` must not pass a prefix check.

        This is the Stage 0 bug turned into a positive test: the resolved path
        is NOT inside the real workspace, even though its string starts with
        the workspace name.
        """
        with self.assertRaises(PolicyError):
            self.policy.resolve_read("../workspace-evil/secret.txt")

    # -- absolute forms ----------------------------------------------------

    def test_absolute_inside_allowed(self) -> None:
        """An absolute path that really points inside is fine.

        Absolute paths are not automatically hostile. If the real path is under
        the workspace, the policy normalises it to a relative name and allows
        it.
        """
        resolved = self.policy.resolve_read(str(self.workspace / "notes.txt"))
        self.assertEqual(resolved.relative, "notes.txt")

    def test_absolute_outside_rejected(self) -> None:
        """An absolute path outside the workspace is refused.

        This checks the same containment rule from the other direction: the
        caller cannot bypass the boundary merely by spelling the path absolutely.
        """
        with self.assertRaises(PolicyError):
            self.policy.resolve_read(str(self.outside))

    # -- symlinks ----------------------------------------------------------

    def test_symlink_file_outside_rejected(self) -> None:
        """A file symlink that points outside is refused.

        A lexical check sees only ``leak.txt`` inside the workspace. The policy
        calls ``realpath`` first, sees the target outside, and refuses.
        """
        self.make_symlink(str(self.outside), "leak.txt")
        with self.assertRaises(PolicyError):
            self.policy.resolve_read("leak.txt")

    def test_symlink_directory_outside_rejected(self) -> None:
        """A symlinked *directory* cannot be used to reach outside files.

        Resolving ``outside-dir-link/secret.txt`` follows the link in the middle
        of the path, not just the final component. The real target is outside,
        so the whole read is refused.
        """
        outside_dir = self.base / "outside-dir"
        outside_dir.mkdir()
        (outside_dir / "secret.txt").write_text("x\n", encoding="utf-8")
        self.make_symlink(str(outside_dir), "outside-dir-link")

        with self.assertRaises(PolicyError):
            self.policy.resolve_read("outside-dir-link/secret.txt")

    def test_symlink_inside_is_readable(self) -> None:
        """A symlink whose real target is inside remains usable.

        The rule is about the *destination*, not about links in general. This
        avoids breaking workspaces that use internal links for convenience.
        The returned relative path is the canonical target, not the link name.
        """
        self.make_symlink(str(self.workspace / "notes.txt"), "inside-link.txt")
        resolved = self.policy.resolve_read("inside-link.txt")
        self.assertEqual(resolved.relative, "notes.txt")

    # -- writes ------------------------------------------------------------

    def test_write_relative_allowed(self) -> None:
        """A new relative file name is allowed for writing."""
        resolved = self.policy.resolve_write("new.txt")
        self.assertEqual(resolved.relative, "new.txt")

    def test_write_creates_no_file_by_itself(self) -> None:
        """Resolving a write path is a *check*; it must not touch the disk.

        Keeping resolution side-effect free means a denied tool call cannot
        leave empty files behind, and the sandbox stays the only component that
        actually writes.
        """
        self.policy.resolve_write("does-not-exist.txt")
        self.assertFalse((self.workspace / "does-not-exist.txt").exists())

    def test_write_nested_nonexistent_allowed(self) -> None:
        """Write checks must allow directories that do not exist yet.

        The sandbox creates parent directories only after this check passes, so
        the policy must resolve the would-be location without requiring it to
        exist.
        """
        resolved = self.policy.resolve_write("deep/new/file.txt")
        self.assertEqual(resolved.relative, "deep/new/file.txt")

    def test_write_absolute_rejected(self) -> None:
        """Absolute write paths outside the workspace are refused."""
        with self.assertRaises(PolicyError):
            self.policy.resolve_write(str(self.outside))

    def test_write_dotdot_rejected(self) -> None:
        """Parent traversal is refused for writes as well as reads."""
        with self.assertRaises(PolicyError):
            self.policy.resolve_write("../outside.txt")

    def test_write_symlink_rejected(self) -> None:
        """Writing through an existing symlink is refused.

        Following a planted link could overwrite a file outside the workspace.
        Refusing symlink writes removes that redirect without affecting normal
        files.
        """
        self.make_symlink(str(self.outside), "write-link.txt")
        with self.assertRaises(PolicyError):
            self.policy.resolve_write("write-link.txt")

    def test_write_root_rejected(self) -> None:
        """The workspace root itself is not a valid file target.

        Writing to ``.`` would mean opening a directory, and deleting/editing
        the root is never a meaningful tool action. Refuse it early.
        """
        with self.assertRaises(PolicyError):
            self.policy.resolve_write(".")

    # -- hostile names -----------------------------------------------------

    def test_reserved_names_rejected(self) -> None:
        """Windows device names are refused on every platform.

        ``CON``, ``NUL`` and friends have special meaning on Windows even with
        an extension (``CON.txt``). Rejecting them everywhere keeps a workspace
        portable and prevents surprising device writes.
        """
        for name in ("CON", "con.txt", "NUL", "LPT1.log"):
            # ``subTest`` lets pytest report which name failed, while the loop
            # keeps the test compact.
            with self.subTest(name=name):
                with self.assertRaises(PolicyError):
                    self.policy.resolve_write(name)

    def test_control_character_rejected(self) -> None:
        """NUL and other control characters can truncate paths lower down.

        A path containing ``\\x00`` is ambiguous across layers. Rejecting the
        whole control-character class avoids relying on any single library's
        interpretation.
        """
        with self.assertRaises(PolicyError):
            self.policy.resolve_read("bad\x00name")

    def test_alternate_data_stream_rejected(self) -> None:
        """Colon suffixes are refused to block NTFS alternate data streams.

        ``file.txt:stream`` is an NTFS alternate data stream on Windows and an
        ambiguous name elsewhere. Refuse it consistently rather than letting
        platform behaviour differ.
        """
        with self.assertRaises(PolicyError):
            self.policy.resolve_write("notes.txt:hidden")

    def test_unc_rejected(self) -> None:
        """UNC paths (``\\\\server\\share``) are refused.

        They name a network location rather than a workspace file and cannot be
        meaningfully contained under the root.
        """
        with self.assertRaises(PolicyError):
            self.policy.resolve_read(r"\\server\share\file")

    def test_drive_relative_rejected(self) -> None:
        """Drive-relative names such as ``C:temp`` are refused.

        ``C:temp\\file`` means "temp on the current directory of drive C", not
        ``C:\\temp\\file``. It is a classic way to slip past naive path checks.
        """
        with self.assertRaises(PolicyError):
            self.policy.resolve_read(r"C:temp\file")

    def test_empty_rejected(self) -> None:
        """Whitespace-only names are not valid file targets.

        An empty name resolves to the workspace root, which is not a file. The
        policy rejects it so tools cannot accidentally operate on the directory.
        """
        with self.assertRaises(PolicyError):
            self.policy.resolve_read("   ")

    def test_backslash_traversal_rejected_everywhere(self) -> None:
        """Backslash traversal is refused even on POSIX.

        A model may emit Windows-style separators everywhere. The policy
        normalises both separators before checking, so ``..\\outside.txt`` is as
        unacceptable as ``../outside.txt``.
        """
        with self.assertRaises(PolicyError):
            self.policy.resolve_read(r"..\outside.txt")

    # -- helpers -----------------------------------------------------------

    def test_is_inside(self) -> None:
        """The helper agrees with the resolver about the boundary.

        ``is_inside`` is used by other components, so it must say "yes" for a
        real workspace file and "no" for a neighbouring file.
        """
        self.assertTrue(self.policy.is_inside(self.workspace / "notes.txt"))
        self.assertFalse(self.policy.is_inside(self.outside))

    def test_relative_format_uses_forward_slashes(self) -> None:
        """Model-facing paths always use ``/``, even on Windows.

        Stable separators make tool output and audit logs comparable across
        platforms, and prevent prompts from changing with the host OS.
        """
        resolved = self.policy.resolve_read("sub/nested.txt")
        self.assertNotIn("\\", resolved.relative)

    def test_expand_variables(self) -> None:
        """Variable expansion supports ``$VAR``, ``${VAR}`` and ``%VAR%``.

        Expansion is convenience for the model, not a security boundary. The
        important part is that an unknown variable is left untouched rather
        than silently becoming an empty string, which would change the path.
        """
        env = {"HOME": "/home/demo", "USERPROFILE": r"C:\Users\demo", "NAME": "x"}
        self.assertEqual(expand_variables("$NAME/file", env), "x/file")
        self.assertEqual(expand_variables("${NAME}/file", env), "x/file")
        self.assertEqual(expand_variables("%NAME%/file", env), "x/file")
        self.assertEqual(expand_variables("$MISSING/file", env), "$MISSING/file")


if __name__ == "__main__":
    import unittest as _unittest

    _unittest.main()
