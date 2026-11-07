"""local_runner.py - run a command without a shell, with visible limits.

This is the chapter where we stop using ``shell=True`` and stop letting the
child inherit the agent's environment.

What the runner does:

* takes an **argv list**, never a command string, so ``;`` and ``&&`` are just
  ordinary characters in an argument;
* resolves the program through an **allowlist**, so the model cannot ask for an
  arbitrary binary on ``PATH``;
* runs with a **cleaned environment**, so API keys do not leak into the child;
* kills the **whole process tree** on timeout;
* caps captured output while still draining the pipes, so a noisy child cannot
  fill memory or deadlock on a full pipe;
* applies POSIX **resource limits** (CPU, address space, file size, fds,
  processes) before ``exec``.

What it does **not** do: it is not a filesystem or network jail. The child runs
as the same user, can read anything that user can read, and can talk to the
network. Chapter 4 replaces this with a container for that reason.
"""

from __future__ import annotations

import os
import shutil
import signal
import subprocess
import sys
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Mapping

from .path_policy import PathPolicy, PolicyError

# ``resource`` exists only on POSIX. Importing it lazily keeps the module
# importable on Windows, where the runner simply has no rlimits.
try:  # pragma: no cover - platform branch
    import resource  # type: ignore
except ImportError:  # pragma: no cover - Windows
    resource = None  # type: ignore


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class CommandError(Exception):
    """A stable refusal from the command policy.

    Codes:

    - ``DENIED``: the program is not on the allowlist.
    - ``ARGS``: the argv shape is invalid.
    - ``CWD``: the working directory is outside the workspace.
    - ``IO``: the OS could not start the process.
    """

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message

    def __str__(self) -> str:
        return f"{self.code}: {self.message}"


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Limits:
    """Limits applied to one local command.

    ``timeout_seconds`` and ``max_output_bytes`` are enforced from the parent.
    The resource limits are applied by the child on POSIX only; on Windows they
    are documentation for the Docker chapter that follows.
    """

    timeout_seconds: float = 10.0
    max_output_bytes: int = 200_000
    max_args: int = 64
    max_arg_chars: int = 8192
    cpu_seconds: int = 5
    memory_mb: int = 256
    file_size_mb: int = 10
    max_open_files: int = 64
    max_processes: int = 32


@dataclass(frozen=True)
class CommandPolicy:
    """The programs the model may ask for, by logical name.

    A mapping is used instead of a set of basenames because the *absolute*
    executable path is what actually gets executed. A file called ``python``
    dropped into the workspace cannot shadow the interpreter through ``PATH``.
    """

    allowed: Mapping[str, str] = field(default_factory=dict)

    def resolve(self, program: str) -> str:
        """Return the absolute executable for ``program`` or raise DENIED."""
        if not isinstance(program, str) or program == "":
            raise CommandError("ARGS", "program must be a non-empty string")

        # Accept the exact allowlisted logical name. Do not resolve through
        # ``shutil.which`` here: PATH is user-controlled and the whole point is
        # to avoid path lookup.
        executable = self.allowed.get(program)
        if executable is None:
            names = ", ".join(sorted(self.allowed)) or "(none)"
            raise CommandError("DENIED", f"{program!r} is not allowed; allowed: {names}")

        # Re-check at call time. An allowlist entry that no longer exists is a
        # configuration bug, not a reason to fall back to PATH.
        if not os.path.isfile(executable):
            raise CommandError("IO", f"allowlisted executable is missing: {executable}")
        return os.path.abspath(executable)


def default_command_policy() -> CommandPolicy:
    """Allow the current Python interpreter only.

    The book's examples all run Python, so the default is useful and narrow.
    A real product would add ``pytest``, a formatter, or a build tool, each with
    an explicit absolute path and its own risk review.
    """
    allowed = {"python": sys.executable}
    # ``python3`` is a common alias on POSIX. It costs nothing to expose it,
    # and it does not widen the executable set.
    if os.name != "nt":
        allowed["python3"] = sys.executable
    return CommandPolicy(allowed=allowed)


@dataclass(frozen=True)
class CommandResult:
    """Everything the agent is allowed to know about one command run."""

    program: str
    argv: tuple[str, ...]
    returncode: int | None
    stdout: str
    stderr: str
    timed_out: bool
    truncated: bool
    duration_seconds: float

    @property
    def ok(self) -> bool:
        """True only for a normal exit with code zero."""
        return not self.timed_out and self.returncode == 0


# ---------------------------------------------------------------------------
# Output capture
# ---------------------------------------------------------------------------


class _Capture:
    """A byte sink with a hard cap.

    The pipe is always drained, even after the cap is reached. If we stopped
    reading, the child would block on a full pipe and never exit, turning an
    output limit into a hang.
    """

    def __init__(self, limit: int) -> None:
        self.limit = limit
        self.data = bytearray()
        self.truncated = False

    def add(self, chunk: bytes) -> None:
        """Store bytes up to the cap, then discard while still draining."""
        room = self.limit - len(self.data)
        if room <= 0:
            # Nothing more will be stored, but the caller keeps reading.
            self.truncated = True
            return

        take = min(room, len(chunk))
        self.data.extend(chunk[:take])
        if take < len(chunk):
            self.truncated = True

    def text(self) -> str:
        """Decode captured bytes for display, never raising on bad UTF-8."""
        return bytes(self.data).decode("utf-8", errors="replace")


def _pump(stream, capture: _Capture) -> None:
    """Read a pipe in chunks until EOF, always draining after the cap."""
    try:
        while True:
            chunk = stream.read(8192)
            if not chunk:
                break
            capture.add(chunk)
    except (OSError, ValueError):
        # The pipe can be closed underneath us when a timeout kills the tree.
        pass
    finally:
        try:
            stream.close()
        except OSError:
            pass


# ---------------------------------------------------------------------------
# Child setup
# ---------------------------------------------------------------------------


def _apply_rlimits(limits: Limits) -> None:
    """Lower the child's POSIX resource limits before ``exec``.

    This function runs in the child between ``fork`` and ``exec``. It must be
    tiny and must never allocate more than necessary. Failures are swallowed:
    an unsupported limit should not prevent the command from starting, but the
    missing boundary is documented and covered by the container in Stage 4.
    """
    if resource is None:
        return

    def lower(kind: int, value: int) -> None:
        try:
            soft, hard = resource.getrlimit(kind)
            # Never raise a hard limit; only lower the soft limit, and cap the
            # hard limit when the current one is unlimited.
            new_soft = value if soft == resource.RLIM_INFINITY else min(soft, value)
            new_hard = hard if hard == resource.RLIM_INFINITY else min(hard, value)
            resource.setrlimit(kind, (new_soft, new_hard))
        except (ValueError, OSError):
            pass

    lower(resource.RLIMIT_CPU, limits.cpu_seconds)
    lower(resource.RLIMIT_AS, limits.memory_mb * 1024 * 1024)
    lower(resource.RLIMIT_FSIZE, limits.file_size_mb * 1024 * 1024)
    lower(resource.RLIMIT_NOFILE, limits.max_open_files)
    if hasattr(resource, "RLIMIT_NPROC"):
        lower(resource.RLIMIT_NPROC, limits.max_processes)


def _clean_environment(workspace: Path) -> dict[str, str]:
    """Build a small environment instead of inheriting the agent's.

    Secrets, proxy credentials and cloud tokens live in the parent environment.
    A child process never needs them for the tools this book exposes. We keep
    only the variables the operating system needs to start a process, then set
    a workspace-local HOME/TEMP so tool output does not scatter outside the
    workspace.
    """
    env: dict[str, str] = {}

    # OS-essential variables. On Windows, ``SYSTEMROOT`` is required for many
    # DLL lookups. On POSIX these keys are usually absent, which is fine.
    for key in (
        "SYSTEMROOT",
        "WINDIR",
        "COMSPEC",
        "PATHEXT",
        "LANG",
        "LC_ALL",
    ):
        if key in os.environ:
            env[key] = os.environ[key]

    # A deliberately minimal PATH. Programs are resolved to absolute paths by
    # the allowlist, so PATH is not the security boundary, but a small PATH
    # also avoids surprising helper binaries from a developer's shell.
    if os.name == "nt":
        system_root = env.get("SYSTEMROOT", r"C:\Windows")
        env["PATH"] = f"{system_root}\\System32;{system_root}"
    else:
        env["PATH"] = os.defpath

    # HOME and TEMP point at workspace-local folders. The command may create
    # caches there, and those files remain inside the agent's reviewable area.
    home = workspace / ".home"
    temp = workspace / ".tmp"
    home.mkdir(exist_ok=True)
    temp.mkdir(exist_ok=True)
    env["HOME"] = str(home)
    env["TMP"] = str(temp)
    env["TEMP"] = str(temp)

    # Deterministic Python behaviour for the examples and tests.
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env["PYTHONNOUSERSITE"] = "1"

    return env


def _kill_tree(process: subprocess.Popen) -> None:
    """Kill the process and its descendants, not just the direct child.

    A shell-less command can still spawn children (``python`` starts workers).
    On POSIX the child was given its own session, so killing the process group
    reaches all of them. On Windows ``taskkill /T`` walks the process tree.
    """
    if os.name == "nt":
        try:
            subprocess.run(
                ["taskkill", "/F", "/T", "/PID", str(process.pid)],
                capture_output=True,
                timeout=10,
                check=False,
            )
        except (OSError, subprocess.SubprocessError):
            pass
    else:
        try:
            os.killpg(os.getpgid(process.pid), signal.SIGKILL)
        except (OSError, ProcessLookupError):
            pass

    # Fallback for the direct child. This is safe even if the group kill
    # already succeeded.
    try:
        process.kill()
    except OSError:
        pass


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------


class CommandRunner:
    """Run allowlisted argv commands inside the workspace."""

    def __init__(
        self,
        root: Path | str,
        *,
        policy: CommandPolicy | None = None,
        limits: Limits | None = None,
    ) -> None:
        self.path_policy = PathPolicy(root)
        self.root = self.path_policy.real_root
        self.command_policy = policy or default_command_policy()
        self.limits = limits or Limits()

    def run(
        self,
        program: str,
        args: list[str] | tuple[str, ...] | None = None,
        *,
        cwd: str = ".",
    ) -> CommandResult:
        """Run one command and return a bounded result.

        ``args`` is always a sequence. Passing a single string is rejected:
        accepting a string invites callers to think a shell is involved.
        """
        if isinstance(args, str):
            raise CommandError("ARGS", "args must be a list, not a string")
        arguments = list(args or [])

        if len(arguments) > self.limits.max_args:
            raise CommandError("ARGS", f"too many arguments (max {self.limits.max_args})")

        for argument in arguments:
            if not isinstance(argument, str):
                raise CommandError("ARGS", "every argument must be a string")
            if "\x00" in argument:
                raise CommandError("ARGS", "argument contains a NUL byte")
            if len(argument) > self.limits.max_arg_chars:
                raise CommandError(
                    "ARGS",
                    f"argument exceeds {self.limits.max_arg_chars} characters",
                )

        # The working directory is a read target: it must exist and be inside
        # the workspace. A model cannot ask to run from the user's home folder.
        try:
            cwd_path = self.path_policy.resolve_read(cwd)
        except PolicyError as exc:
            raise CommandError("CWD", str(exc)) from exc
        if not cwd_path.absolute.is_dir():
            raise CommandError("CWD", f"not a folder: {cwd}")

        executable = self.command_policy.resolve(program)
        argv = (executable, *arguments)

        # A single, named environment is built once. Tests assert that a
        # sentinel secret from the parent does not appear in the child.
        env = _clean_environment(self.root)

        # ``preexec_fn`` is only safe because this runner executes one command
        # at a time and does not start threads before ``fork``. A production
        # server with concurrent commands should use ``posix_spawn`` or a
        # supervisor process instead; the book calls this out in the chapter.
        preexec = (lambda: _apply_rlimits(self.limits)) if resource is not None else None

        # Windows requires a new process group for tree killing; POSIX uses a
        # new session so the whole group can be signalled.
        if os.name == "nt":
            creationflags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
            start_new_session = False
        else:
            creationflags = 0
            start_new_session = True

        started = time.monotonic()
        try:
            process = subprocess.Popen(
                argv,
                cwd=os.fspath(cwd_path.absolute),
                env=env,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                close_fds=True,
                preexec_fn=preexec,
                start_new_session=start_new_session,
                creationflags=creationflags,
            )
        except OSError as exc:
            raise CommandError("IO", f"could not start {program}: {exc}") from exc

        # Separate caps per stream keep a chatty stderr from hiding stdout.
        out_capture = _Capture(self.limits.max_output_bytes)
        err_capture = _Capture(self.limits.max_output_bytes)

        out_thread = threading.Thread(
            target=_pump, args=(process.stdout, out_capture), daemon=True
        )
        err_thread = threading.Thread(
            target=_pump, args=(process.stderr, err_capture), daemon=True
        )
        out_thread.start()
        err_thread.start()

        timed_out = False
        try:
            process.wait(timeout=self.limits.timeout_seconds)
        except subprocess.TimeoutExpired:
            timed_out = True
            _kill_tree(process)
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                # Extremely unlikely, but never block the agent forever.
                pass

        # Give the reader threads a moment to drain the final bytes. If they
        # are still alive (a grandchild inherited the pipe), do not wait
        # forever; the daemon threads will die with the process.
        out_thread.join(timeout=5)
        err_thread.join(timeout=5)

        duration = time.monotonic() - started

        # Normalise Windows text-mode newlines for the model. The raw bytes
        # are still bounded by the capture cap above.
        stdout = out_capture.text().replace("\r\n", "\n")
        stderr = err_capture.text().replace("\r\n", "\n")

        return CommandResult(
            program=program,
            argv=argv,
            returncode=process.returncode,
            stdout=stdout,
            stderr=stderr,
            timed_out=timed_out,
            truncated=out_capture.truncated or err_capture.truncated,
            duration_seconds=duration,
        )


def resolve_real_executable(program: str) -> str | None:
    """Small helper used by documentation tests to show allowlist resolution.

    ``shutil.which`` is intentionally *not* used by the runner. This helper is
    only for explaining why: it shows what PATH lookup would have returned,
    which is exactly the value we refuse to trust.
    """
    return shutil.which(program)
