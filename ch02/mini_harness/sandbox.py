"""sandbox.py - the object every file tool must go through.

The path policy answers "is this name allowed?". The sandbox adds the rest of
the file contract:

* size limits, so one read cannot exhaust memory;
* directory-entry limits, so a listing cannot fill the transcript;
* atomic writes, so a crash cannot leave a half-written file;
* "no symlink writes", so a planted link cannot redirect an edit;
* a stable error vocabulary that tools can show the model.

The sandbox does **not** try to be an OS jail. A Python process with the same
user can still race paths, read ``/proc``, or call ``os.system``. It is a
policy layer for well-behaved tools. Chapter 4 adds the kernel boundary.
"""

from __future__ import annotations

import os
import stat
import tempfile
from dataclasses import dataclass
from pathlib import Path

from .path_policy import PathPolicy, PolicyError, ResolvedPath

# ---------------------------------------------------------------------------
# Errors and results
# ---------------------------------------------------------------------------


class SandboxError(Exception):
    """A refusal or operational failure with a stable, model-friendly code.

    Codes used in this book:

    - ``PATH``: the path policy rejected the target.
    - ``NOT_FOUND``: the target does not exist.
    - ``IS_DIR`` / ``NOT_DIR``: the caller asked for the wrong file type.
    - ``TOO_LARGE``: a size or count limit was exceeded.
    - ``EXISTS``: ``write_text`` was asked to create-only and the file exists.
    - ``NO_MATCH`` / ``AMBIGUOUS``: an edit's old text was missing or repeated.
    - ``IO``: the OS failed for a reason not covered above.
    """

    def __init__(self, code: str, message: str, path: str | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.path = path

    def __str__(self) -> str:
        """Render the form tools return to the model."""
        return f"{self.code}: {self.message}"


@dataclass(frozen=True)
class Limits:
    """Caps that keep one tool call from dominating the agent's resources.

    These are policy choices, not security boundaries. Change them deliberately
    and record the change in the operations manual.
    """

    max_read_bytes: int = 2 * 1024 * 1024       # 2 MiB per file read
    max_write_bytes: int = 1 * 1024 * 1024      # 1 MiB per file write
    max_dir_entries: int = 500                  # entries returned by one list
    max_line_bytes: int = 4000                  # truncate a very long line


@dataclass(frozen=True)
class DirEntry:
    """One safe, model-facing directory entry."""

    name: str
    kind: str          # "file", "dir", "link" or "other"
    size: int | None   # only for regular files; None otherwise


# ---------------------------------------------------------------------------
# Sandbox
# ---------------------------------------------------------------------------


class Sandbox:
    """A policy-checked workspace with bounded text operations."""

    def __init__(self, root: Path | str, *, limits: Limits | None = None) -> None:
        self.policy = PathPolicy(root)
        self.limits = limits or Limits()
        # Store the canonical root as a convenience for callers and tests.
        self.root = self.policy.real_root

    # -- reads -------------------------------------------------------------

    def read_text(self, relative: str) -> str:
        """Read a UTF-8 text file inside the workspace.

        The byte limit is checked from ``stat`` *before* reading, then the file
        is read as bytes and decoded. Reading bytes avoids newline translation
        (so a round-trip edit cannot silently change ``\\r\\n``) and lets the
        limit apply to the exact data the process receives.
        """
        resolved = self._resolve_read(relative)

        try:
            info = resolved.absolute.stat()
        except FileNotFoundError as exc:
            raise SandboxError("NOT_FOUND", "no such file", relative) from exc

        if stat.S_ISDIR(info.st_mode):
            raise SandboxError("IS_DIR", "is a folder", relative)
        if not stat.S_ISREG(info.st_mode):
            raise SandboxError("IO", "not a regular file", relative)
        if info.st_size > self.limits.max_read_bytes:
            raise SandboxError(
                "TOO_LARGE",
                f"file is {info.st_size} bytes; limit is {self.limits.max_read_bytes}",
                relative,
            )

        try:
            data = resolved.absolute.read_bytes()
        except OSError as exc:
            raise SandboxError("IO", str(exc), relative) from exc

        # Decode as UTF-8 with replacement. A coding agent should not crash on
        # a stray byte; the model can still see the rest of the file.
        return data.decode("utf-8", errors="replace")

    def list_dir(self, relative: str = ".") -> list[DirEntry]:
        """List one directory, sorted, with a hard cap on entries.

        Symlinks are reported as ``link`` and are **not** followed here. The
        policy has already resolved the requested directory; individual
        entries are only metadata. Following every link during a listing would
        turn one tool call into an unbounded walk.
        """
        resolved = self._resolve_read(relative)

        try:
            info = resolved.absolute.stat()
        except FileNotFoundError as exc:
            raise SandboxError("NOT_FOUND", "no such folder", relative) from exc

        if not stat.S_ISDIR(info.st_mode):
            raise SandboxError("NOT_DIR", "not a folder", relative)

        entries: list[DirEntry] = []
        try:
            iterator = resolved.absolute.iterdir()
            for entry in iterator:
                if len(entries) >= self.limits.max_dir_entries:
                    # Stop quietly. The caller can list a narrower folder.
                    break

                kind = "other"
                size: int | None = None

                # lstat does not follow a symlink, so a link to an inaccessible
                # target cannot make the listing fail.
                try:
                    entry_info = entry.lstat()
                    mode = entry_info.st_mode
                    if stat.S_ISLNK(mode):
                        kind = "link"
                    elif stat.S_ISDIR(mode):
                        kind = "dir"
                    elif stat.S_ISREG(mode):
                        kind = "file"
                        size = entry_info.st_size
                except OSError:
                    # A race (the entry disappeared) should not abort the whole
                    # listing. Report it as "other" with unknown size.
                    kind = "other"

                entries.append(DirEntry(name=entry.name, kind=kind, size=size))
        except OSError as exc:
            raise SandboxError("IO", str(exc), relative) from exc

        return sorted(entries, key=lambda item: item.name)

    # -- writes ------------------------------------------------------------

    def write_text(
        self,
        relative: str,
        content: str,
        *,
        overwrite: bool = True,
    ) -> ResolvedPath:
        """Write UTF-8 text atomically inside the workspace.

        Atomic means: write a temporary file in the *same directory*, flush it,
        then rename it over the target with ``os.replace``. A reader either
        sees the old file or the new one, never a half-written file.

        ``overwrite=False`` gives create-only semantics, which is useful for
        tools that should not clobber an existing file by accident.
        """
        if not isinstance(content, str):
            raise SandboxError("IO", "content must be text")

        encoded = content.encode("utf-8")
        if len(encoded) > self.limits.max_write_bytes:
            raise SandboxError(
                "TOO_LARGE",
                f"content is {len(encoded)} bytes; limit is {self.limits.max_write_bytes}",
            )

        resolved = self._resolve_write(relative)
        target = resolved.absolute

        if target.exists():
            if target.is_dir():
                raise SandboxError("IS_DIR", "refusing to overwrite a folder", relative)
            if not overwrite:
                raise SandboxError("EXISTS", "file already exists", relative)

        # Create parents one level at a time and re-run the policy after each
        # step. A path that was safe before mkdir should still be safe after;
        # re-checking narrows the race window and catches mistakes early.
        self._ensure_parent(resolved)

        try:
            # NamedTemporaryFile gives a unique name in the destination
            # directory, which is required for an atomic replace on the same
            # filesystem.
            handle = tempfile.NamedTemporaryFile(
                mode="wb",
                dir=os.fspath(target.parent),
                prefix=".sandbox-",
                suffix=".tmp",
                delete=False,
            )
            temp_name = handle.name
            try:
                handle.write(encoded)
                handle.flush()
                os.fsync(handle.fileno())
            finally:
                handle.close()

            # Restrict permissions on POSIX. On Windows the call is a no-op for
            # these bits, so it is safe to attempt it.
            try:
                os.chmod(temp_name, 0o600)
            except OSError:
                pass

            os.replace(temp_name, target)
        except OSError as exc:
            # Best-effort cleanup: never leave the temporary file behind.
            try:
                if "temp_name" in locals() and os.path.exists(temp_name):
                    os.unlink(temp_name)
            except OSError:
                pass
            raise SandboxError("IO", str(exc), relative) from exc

        return resolved

    def edit_text(
        self,
        relative: str,
        old: str,
        new: str,
        *,
        count: int = 1,
    ) -> str:
        """Replace text in a file and return the new content.

        By default the old text must appear exactly once. That makes an edit
        predictable: if the model copied the wrong snippet, the tool refuses
        instead of silently changing three places. Passing ``count=0`` means
        "replace every occurrence"; the caller must opt in explicitly.
        """
        if old == "":
            raise SandboxError("IO", "old text must not be empty", relative)

        current = self.read_text(relative)
        occurrences = current.count(old)

        if occurrences == 0:
            raise SandboxError("NO_MATCH", "old text not found", relative)
        if count == 1 and occurrences != 1:
            raise SandboxError(
                "AMBIGUOUS",
                f"old text appears {occurrences} times; make it unique or pass count=0",
                relative,
            )

        updated = current.replace(old, new, count if count > 0 else -1)
        self.write_text(relative, updated)
        return updated

    def delete_file(self, relative: str) -> ResolvedPath:
        """Delete a regular file, never a directory or a symlink.

        Deleting a directory recursively is deliberately out of scope. A tool
        that can erase a tree is a much larger blast radius than one that can
        erase one file, and the agent can always ask for files one by one.
        """
        resolved = self._resolve_write(relative)
        target = resolved.absolute

        try:
            info = target.lstat()
        except FileNotFoundError as exc:
            raise SandboxError("NOT_FOUND", "no such file", relative) from exc

        if stat.S_ISDIR(info.st_mode):
            raise SandboxError("IS_DIR", "refusing to delete a folder", relative)
        if not stat.S_ISREG(info.st_mode):
            raise SandboxError("IO", "refusing to delete a non-regular file", relative)

        try:
            target.unlink()
        except OSError as exc:
            raise SandboxError("IO", str(exc), relative) from exc

        return resolved

    # -- internals ---------------------------------------------------------

    def _resolve_read(self, relative: str) -> ResolvedPath:
        """Translate a policy refusal into the sandbox's error vocabulary."""
        try:
            return self.policy.resolve_read(relative)
        except PolicyError as exc:
            raise SandboxError("PATH", exc.reason, relative) from exc

    def _resolve_write(self, relative: str) -> ResolvedPath:
        """Write-side policy wrapper with the same error translation."""
        try:
            return self.policy.resolve_write(relative)
        except PolicyError as exc:
            raise SandboxError("PATH", exc.reason, relative) from exc

    def _ensure_parent(self, resolved: ResolvedPath) -> None:
        """Create missing parent folders, re-checking the policy each step.

        The target itself may not exist, but its parent must. We walk from the
        root toward the target and call ``mkdir`` only for components that are
        missing. After each creation we resolve the same relative path again,
        so a symlink or junction planted during the operation is noticed.
        """
        parent = resolved.absolute.parent
        root = self.root

        # ``relative_to`` is safe here because resolve_write already proved
        # containment. It also gives us the components without string surgery.
        try:
            parts = parent.relative_to(root).parts
        except ValueError as exc:
            raise SandboxError("PATH", "parent escapes workspace", resolved.requested) from exc

        current = root
        for part in parts:
            current = current / part
            if current.exists():
                if not current.is_dir():
                    raise SandboxError("NOT_DIR", "parent is not a folder", resolved.requested)
                continue

            try:
                current.mkdir()
            except OSError as exc:
                raise SandboxError("IO", str(exc), resolved.requested) from exc

        # Re-resolve after possible filesystem changes. This is still not a
        # complete defence against a concurrent attacker; the container is.
        try:
            self.policy.resolve_write(resolved.requested)
        except PolicyError as exc:
            raise SandboxError("PATH", exc.reason, resolved.requested) from exc
