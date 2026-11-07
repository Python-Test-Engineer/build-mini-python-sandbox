"""path_policy.py - one place that answers "where may this path point?".

The sandbox is only as good as its path handling. Every tool (list, read,
write, edit, delete) must ask the *same* object the *same* question. If each
tool invents its own ``startswith`` check, one of them will be wrong.

This module has no file-content logic. It resolves names, applies platform
rules, and returns canonical paths that the file tools can safely use.

The central idea is:

    A path is safe only if the *real* file it resolves to is inside the
    *real* workspace root.

"Real" means ``os.path.realpath`` has followed every symlink/junction. A
lexical ``..`` collapse is not enough: it cannot see that
``workspace/link`` points at ``/home/me/.ssh``.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class PolicyError(Exception):
    """A refusal from the path policy, distinct from an OS I/O failure.

    ``code`` is stable and greppable. Tools convert this exception into a
    visible observation such as ``PATH: path escapes workspace: ../x``. They
    never let it crash the agent loop.
    """

    code = "PATH"

    def __init__(self, message: str, requested: str | None = None) -> None:
        super().__init__(message)
        # Keep the original request beside the reason so an audit log can show
        # exactly what the model asked for.
        self.requested = requested
        self.reason = message

    def __str__(self) -> str:
        """Render the stable form used in tool observations."""
        return f"{self.code}: {self.reason}"


# ---------------------------------------------------------------------------
# Platform rules
# ---------------------------------------------------------------------------

# Windows device names are reserved even when an extension follows, e.g.
# ``CON.txt``. We reject them on every platform so a workspace moved between
# Linux and Windows cannot suddenly change meaning.
_WINDOWS_RESERVED = {
    "CON", "PRN", "AUX", "NUL",
    *(f"COM{i}" for i in range(1, 10)),
    *(f"LPT{i}" for i in range(1, 10)),
}

# ``C:foo`` is drive-relative: it means "foo in the current directory of drive
# C", not "C:\foo". It is a classic way to escape naive path checks.
_DRIVE_RELATIVE = re.compile(r"^[A-Za-z]:(?![\\/])")

# ``C:\foo`` or ``C:/foo`` is a drive-absolute path.
_DRIVE_ABSOLUTE = re.compile(r"^[A-Za-z]:[\\/]")

# Two leading separators mean a UNC path (``\\server\share``) on Windows, and
# a network-style path on POSIX. Neither belongs in a workspace-relative name.
_UNC = re.compile(r"^(\\\\|//)")

# Control characters, especially NUL, can truncate a path inside a lower layer
# of the stack. Reject the whole class instead of only ``\x00``.
_CONTROL_CHARS = re.compile(r"[\x00-\x1f\x7f]")

# Environment variables can expand to an absolute path. We expand them for
# convenience, then still run the result through containment. Only these two
# spellings are supported; arbitrary shell expansion is not a path policy.
_PERCENT_VAR = re.compile(r"%([A-Za-z_][A-Za-z0-9_]*)%")
_POSIX_VAR = re.compile(r"\$(?:\{([A-Za-z_][A-Za-z0-9_]*)\}|([A-Za-z_][A-Za-z0-9_]*))")


# ---------------------------------------------------------------------------
# Result object
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ResolvedPath:
    """The result of a successful policy check.

    Attributes:
        requested: The exact string the caller supplied, kept for logs.
        absolute:  The canonical absolute path after symlink resolution. This
                   is the path tools should actually open/create.
        relative:  The path relative to the workspace root, always using ``/``
                   so model-visible output is stable across platforms.
    """

    requested: str
    absolute: Path
    relative: str


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------


def expand_variables(text: str, env: Mapping[str, str] | None = None) -> str:
    """Expand ``~``, ``%VAR%`` and ``$VAR`` forms, textually.

    This is convenience for the model, not a security boundary. Whatever the
    expansion produces is validated afterwards by :meth:`PathPolicy._resolve`.
    """
    values = os.environ if env is None else env

    # ``~`` is only special at the start of the string.
    if text == "~":
        text = os.path.expanduser("~")
    elif text.startswith("~/") or text.startswith("~\\"):
        text = os.path.expanduser("~") + text[1:]

    # Windows-style variables first, then POSIX-style. A variable that is not
    # present is left untouched; it will be treated as a literal name.
    text = _PERCENT_VAR.sub(
        lambda match: values.get(match.group(1), match.group(0)), text
    )
    text = _POSIX_VAR.sub(
        lambda match: values.get(match.group(1) or match.group(2), match.group(0)),
        text,
    )
    return text


def _comparison_form(path: Path) -> str:
    """Return a form suitable for case-insensitive comparison on Windows.

    ``os.path.normcase`` lower-cases and swaps separators on Windows and is a
    no-op on POSIX, which is exactly the platform behaviour we want.
    """
    return os.path.normcase(os.path.abspath(os.fspath(path)))


def _realpath_best(path: Path) -> Path:
    """Resolve the deepest existing ancestor, then reattach the missing tail.

    ``os.path.realpath`` only sees the filesystem that exists. A write target
    such as ``workspace/new/dir/file.txt`` usually does not exist yet. Walking
    up to the nearest existing parent lets us resolve symlinked *parents*
    (``workspace/link-to-outside/new.txt``) and still return a canonical path
    for the part that has not been created.
    """
    current = Path(os.path.abspath(os.fspath(path)))
    missing: list[str] = []

    # Walk up until something exists. Guard against a broken parent chain.
    while not current.exists():
        parent = current.parent
        if parent == current:
            break
        missing.append(current.name)
        current = parent

    # realpath may still fail on unusual filesystems; fall back to the lexical
    # path rather than crashing the policy.
    try:
        resolved = Path(os.path.realpath(os.fspath(current)))
    except OSError:
        resolved = current

    # Reattach the missing components in their original order.
    for part in reversed(missing):
        resolved = resolved / part
    return Path(os.path.abspath(os.fspath(resolved)))


def realpath_best(path: Path) -> Path:
    """Public wrapper used by tools that need a canonical path on its own."""
    return _realpath_best(path)


def _check_reserved_name(segment: str, requested: str) -> None:
    """Reject Windows device names and trailing dots/spaces.

    Trailing spaces and dots are silently stripped by Windows, so
    ``secret.txt.`` and ``secret.txt`` can name the same file. Rejecting them
    avoids a policy check that sees one name while the OS opens another.
    """
    # ``.`` and ``..`` are navigation tokens, not filenames. They are handled
    # by the containment check after the path is normalised.
    if not segment or segment in (".", ".."):
        return

    # A colon is a Windows drive separator or an NTFS alternate data stream.
    # The only colon-bearing segment we accept is a drive prefix such as "C:".
    if ":" in segment:
        if not (os.name == "nt" and re.fullmatch(r"[A-Za-z]:", segment)):
            raise PolicyError(f"path segment contains a colon: {segment!r}", requested)

    if os.name == "nt" and (segment.endswith(".") or segment.endswith(" ")):
        raise PolicyError(f"path segment ends with a dot or space: {segment!r}", requested)

    # The part before the first dot is the device name. ``CON.txt`` is still
    # the console device on Windows.
    stem = segment.split(".", 1)[0].upper()
    if stem in _WINDOWS_RESERVED:
        raise PolicyError(f"reserved device name: {segment!r}", requested)


def _normalise_separators(text: str) -> str:
    """Treat backslash as a separator for policy checks on every platform.

    On POSIX a backslash can be a legal filename character, but the harness is
    cross-platform and the model often writes Windows-style paths. Treating
    both separators the same makes the policy's answer identical everywhere:
    ``..\\secret`` is rejected on Linux too, instead of becoming a strange but
    harmless filename.
    """
    return text.replace("\\", "/")


def _is_absolute_text(text: str) -> bool:
    """Return True for any absolute spelling we recognise on any platform."""
    return bool(
        os.path.isabs(text)
        or _DRIVE_ABSOLUTE.match(text)
        or text.startswith("/")
        or text.startswith("\\")
    )


# ---------------------------------------------------------------------------
# The policy
# ---------------------------------------------------------------------------


class PathPolicy:
    """Resolve workspace names and refuse anything outside the real root.

    ``resolve_read`` and ``resolve_write`` share all of the same validation.
    The only differences are policy choices:

    * reads may be absolute as long as the resolved file is inside the root;
    * writes must be relative, because a write should be an intentional
      workspace action, never an absolute overwrite of a system file;
    * writes may not pass through a symlink, because a symlink is easy to
      plant and hard to reason about.
    """

    def __init__(self, root: Path | str, *, create: bool = True) -> None:
        """Create the policy and canonicalise the workspace root.

        ``root`` itself may be a symlink. We store both the lexical root (for
        creating the folder) and the real root (for containment checks). All
        containment checks compare real paths.
        """
        if root is None or str(root).strip() == "":
            raise PolicyError("workspace root is required")

        self.root = Path(os.path.abspath(os.path.expanduser(os.fspath(root))))
        if create:
            self.root.mkdir(parents=True, exist_ok=True)

        if not self.root.is_dir():
            raise PolicyError(f"workspace root is not a directory: {self.root}")

        # Resolve the root once. If the root itself is a symlink, everything
        # inside it is compared against the real destination.
        self.real_root = Path(os.path.realpath(self.root))

    # -- public API --------------------------------------------------------

    def resolve_read(self, requested: str) -> ResolvedPath:
        """Validate a read target and return its canonical absolute path."""
        return self._resolve(requested, for_write=False)

    def resolve_write(self, requested: str) -> ResolvedPath:
        """Validate a write target. The target may not exist yet."""
        return self._resolve(requested, for_write=True)

    def is_inside(self, path: Path | str) -> bool:
        """True when ``path`` is the root or a descendant, using real paths."""
        target = _realpath_best(Path(os.fspath(path)))
        return self._contains(real_target=target)

    def relative(self, absolute: Path) -> str:
        """Format a canonical path for the model, using forward slashes."""
        relative = os.path.relpath(os.fspath(absolute), os.fspath(self.real_root))
        if relative == ".":
            return "."
        # On Windows relpath returns backslashes; the model-facing form should
        # not change when the host OS changes.
        return relative.replace(os.sep, "/")

    # -- internals ---------------------------------------------------------

    def _contains(self, *, real_target: Path) -> bool:
        """Compare canonical paths with a real common-path check.

        ``commonpath`` is stronger than ``startswith``: ``/ws-evil`` is not a
        child of ``/ws``. On Windows we compare case-folded forms because the
        filesystem is normally case-insensitive. ``commonpath`` also raises
        ``ValueError`` for paths on different drives, which is a refusal.
        """
        root = _comparison_form(self.real_root)
        target = _comparison_form(real_target)
        try:
            common = os.path.commonpath([root, target])
        except ValueError:
            return False
        return common == root

    def _resolve(self, requested: str, *, for_write: bool = False) -> ResolvedPath:
        """The single implementation behind both public resolve methods."""
        if not isinstance(requested, str):
            raise PolicyError("path must be a string", requested=None)

        # Empty strings and whitespace-only names are never meaningful. We do
        # not ``strip()`` the accepted value: a trailing space is a real
        # filename character on POSIX and a Windows hazard.
        if requested.strip() == "":
            raise PolicyError("path is required", requested)

        if _CONTROL_CHARS.search(requested):
            raise PolicyError("path contains a control character", requested)

        # Expand convenience syntax before validation. Expansion may introduce
        # absolute paths; those are checked by the rules below.
        expanded = expand_variables(requested)

        # UNC paths and drive-relative forms are ambiguous across platforms.
        # Reject them outright instead of trying to normalise them.
        if _UNC.match(expanded):
            raise PolicyError(f"UNC paths are not allowed: {requested}", requested)
        if _DRIVE_RELATIVE.match(expanded):
            raise PolicyError(
                f"drive-relative paths are not allowed: {requested}", requested
            )

        # Writes are workspace-relative by design. Reads may be absolute, but
        # they must still resolve inside the root.
        if for_write and _is_absolute_text(expanded):
            raise PolicyError(
                f"writes must be relative to the workspace: {requested}", requested
            )

        # A Windows drive-absolute path is only meaningful on Windows. On
        # POSIX it would be interpreted as a relative name containing a colon,
        # which is confusing and not portable. Refuse it instead.
        if _DRIVE_ABSOLUTE.match(expanded) and os.name != "nt":
            raise PolicyError(
                f"Windows absolute paths are not allowed here: {requested}", requested
            )

        # Build the lexical candidate from the separator-normalised form. This
        # means ``..\secret`` is treated as traversal on every platform,
        # rather than as a harmless filename on POSIX.
        normalised = _normalise_separators(expanded)
        if for_write:
            # A relative path is joined to the lexical root, not the real root,
            # so the returned path stays inside the workspace as the user sees
            # it. Containment is still checked against the real root below.
            target = Path(os.path.abspath(os.path.join(os.fspath(self.root), normalised)))
        elif _is_absolute_text(normalised):
            target = Path(os.path.abspath(normalised))
        else:
            target = Path(os.path.abspath(os.path.join(os.fspath(self.root), normalised)))

        # Check every segment we can see lexically before touching the disk.
        # This rejects reserved names even when the target does not exist.
        for segment in normalised.split("/"):
            _check_reserved_name(segment, requested)

        # Resolve symlinks/junctions in the deepest existing prefix.
        real_target = _realpath_best(target)

        if not self._contains(real_target=real_target):
            raise PolicyError(f"path escapes workspace: {requested}", requested)

        if for_write:
            # Pretend a write is safe unless the final path is the root. A
            # directory is not a file target.
            if real_target == self.real_root:
                raise PolicyError("refusing to write to the workspace root", requested)

            # A symlink at the final component would normally be replaced by
            # our atomic writer, but tools other than the writer may follow it.
            # Refusing here makes the rule independent of the tool.
            if target.is_symlink() or real_target.is_symlink():
                raise PolicyError(
                    f"refusing to write through a symlink: {requested}", requested
                )

        relative = os.path.relpath(os.fspath(real_target), os.fspath(self.real_root))
        relative = "." if relative == "." else relative.replace(os.sep, "/")

        return ResolvedPath(
            requested=requested,
            absolute=real_target,
            relative=relative,
        )
