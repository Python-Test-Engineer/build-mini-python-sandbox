"""docker_runner.py - run one argv command inside a hardened container.

Stage 3's local runner is good hygiene: no shell, an allowlist, a clean
environment, a timeout and output caps. It is still the same user on the same
kernel. A command can read the user's SSH keys or open a network connection.

This module moves the command into a container built for one purpose:

* **no network** (``--network none``);
* **read-only root filesystem** (``--read-only``) with small writable tmpfs
  mounts only where a process normally needs scratch space;
* **no Linux capabilities** (``--cap-drop ALL``) and no privilege escalation
  (``--security-opt no-new-privileges``);
* **resource limits**: memory, swap, CPUs, pids and open files;
* **a non-root user** inside the container;
* **the workspace is the only bind mount**;
* **Docker's default seccomp profile** still applies (we do not disable it).

This is a much stronger boundary than a path policy, but it is not magic. A
container shares the host kernel. Keep the image patched, keep the daemon
private, and never add ``--privileged`` or a Docker socket mount.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import threading
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Mapping, Sequence

from .path_policy import PathPolicy, PolicyError


# ---------------------------------------------------------------------------
# Errors and results
# ---------------------------------------------------------------------------


class DockerError(Exception):
    """A stable Docker-layer refusal or failure.

    Codes:

    - ``DOCKER_MISSING``: the CLI or daemon is not available.
    - ``BUILD_FAILED``: ``docker build`` did not succeed.
    - ``RUN_FAILED``: the container could not be started.
    - ``ARGS`` / ``CWD`` / ``ENV``: invalid input from the tool layer.
    - ``CONFIG``: the runner's own configuration is invalid.
    """

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message

    def __str__(self) -> str:
        return f"{self.code}: {self.message}"


@dataclass(frozen=True)
class DockerConfig:
    """The container contract.

    Defaults are intentionally conservative. The workspace is mounted
    read-write because the final coding agent must edit files; every other
    writable location is a size-limited tmpfs. If a task only needs to read,
    set ``workspace_mode='ro'``.
    """

    image: str = "mini-harness-python:latest"
    user: str = "1000:1000"
    memory: str = "256m"
    cpus: str = "1.0"
    pids_limit: int = 64
    nofile_limit: int = 64
    timeout_seconds: float = 20.0
    max_output_bytes: int = 200_000
    workspace_mode: str = "rw"          # "rw" or "ro"
    tmpfs_size: str = "32m"
    network: str = "none"
    read_only_root: bool = True
    init: bool = True                   # run a tiny init as PID 1
    extra_env: Mapping[str, str] = field(default_factory=dict)

    def validate(self) -> None:
        """Reject configuration that would silently weaken the contract."""
        if not self.image or any(ch in self.image for ch in "\x00\r\n"):
            raise DockerError("CONFIG", "image must be a non-empty single line")
        if self.workspace_mode not in ("rw", "ro"):
            raise DockerError("CONFIG", "workspace_mode must be 'rw' or 'ro'")
        if self.network != "none":
            # The book deliberately does not support a network-enabled mode.
            # Adding one should be a reviewed decision, not a config flag that
            # someone flips by accident.
            raise DockerError("CONFIG", "only network='none' is supported")
        if not self.read_only_root:
            raise DockerError("CONFIG", "the root filesystem must be read-only")
        if self.pids_limit <= 0 or self.nofile_limit <= 0:
            raise DockerError("CONFIG", "pids and nofile limits must be positive")
        if not self.user or ":" not in self.user:
            raise DockerError("CONFIG", "user must be uid:gid")
        if self.timeout_seconds <= 0:
            raise DockerError("CONFIG", "timeout must be positive")


@dataclass(frozen=True)
class RunResult:
    """The result of one container run."""

    argv: tuple[str, ...]
    container_name: str
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
    """A capped byte sink that keeps draining its pipe."""

    def __init__(self, limit: int) -> None:
        self.limit = limit
        self.data = bytearray()
        self.truncated = False

    def add(self, chunk: bytes) -> None:
        """Store bytes up to the cap; keep draining after it is reached."""
        room = self.limit - len(self.data)
        if room <= 0:
            self.truncated = True
            return
        take = min(room, len(chunk))
        self.data.extend(chunk[:take])
        if take < len(chunk):
            self.truncated = True

    def text(self) -> str:
        """Decode for display, replacing invalid UTF-8."""
        return bytes(self.data).decode("utf-8", errors="replace")


def _pump(stream, capture: _Capture) -> None:
    """Read a pipe until EOF; always drain so the child cannot block."""
    try:
        while True:
            chunk = stream.read(8192)
            if not chunk:
                break
            capture.add(chunk)
    except (OSError, ValueError):
        pass
    finally:
        try:
            stream.close()
        except OSError:
            pass


# ---------------------------------------------------------------------------
# Docker runner
# ---------------------------------------------------------------------------

_ENV_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


class DockerRunner:
    """Build and run the sandbox image with a fixed hardening recipe."""

    def __init__(
        self,
        root: Path | str,
        *,
        config: DockerConfig | None = None,
        docker: str | None = None,
    ) -> None:
        self.path_policy = PathPolicy(root)
        self.root = self.path_policy.real_root
        self.config = config or DockerConfig()
        self.config.validate()

        # Resolve the CLI once. ``shutil.which`` is fine here because the
        # program is not model-controlled; the allowlist concern from Stage 3
        # was about names supplied by the model.
        self.docker = docker or shutil.which("docker") or "docker"

        # A short cache avoids running ``docker version`` before every tool
        # call while still allowing a user to start Docker after the process
        # begins. ``check_available`` can be called again explicitly.
        self._availability: bool | None = None

    # -- availability ------------------------------------------------------

    def check_available(self) -> bool:
        """Return True when the CLI can reach a Docker daemon.

        ``docker version`` is used instead of checking for the binary alone:
        a laptop can have the CLI installed while Docker Desktop is stopped.
        """
        if shutil.which(self.docker) is None and not os.path.isfile(self.docker):
            self._availability = False
            return False

        try:
            completed = subprocess.run(
                [self.docker, "version", "--format", "{{.Server.Version}}"],
                capture_output=True,
                text=True,
                timeout=8,
                check=False,
            )
        except (OSError, subprocess.SubprocessError):
            self._availability = False
            return False

        self._availability = completed.returncode == 0
        return self._availability

    def require_available(self) -> None:
        """Raise DOCKER_MISSING when the daemon is not usable."""
        if self._availability is True:
            return
        if not self.check_available():
            raise DockerError(
                "DOCKER_MISSING",
                "Docker CLI/daemon is not available; install Docker and start it",
            )

    # -- build -------------------------------------------------------------

    def build(
        self,
        context: Path | str,
        *,
        dockerfile: str | None = None,
        tag: str | None = None,
        no_cache: bool = False,
        timeout: float = 600.0,
    ) -> str:
        """Build the sandbox image and return the build output.

        Building is deliberately a separate, explicit operation. A tool call
        from the model should not be able to rebuild its own jail.
        """
        self.require_available()
        image = tag or self.config.image

        command = [self.docker, "build", "-t", image]
        if dockerfile:
            command.extend(["-f", dockerfile])
        if no_cache:
            command.append("--no-cache")
        command.append(os.fspath(context))

        try:
            completed = subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=timeout,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            raise DockerError("BUILD_FAILED", f"docker build timed out: {exc}") from exc
        except OSError as exc:
            raise DockerError("DOCKER_MISSING", f"could not run docker: {exc}") from exc

        output = (completed.stdout or "") + (completed.stderr or "")
        if completed.returncode != 0:
            raise DockerError(
                "BUILD_FAILED",
                f"docker build exited {completed.returncode}:\n{output[-4000:]}",
            )
        return output

    def image_exists(self, image: str | None = None) -> bool:
        """Check for a local image without pulling from a registry."""
        self.require_available()
        name = image or self.config.image
        try:
            completed = subprocess.run(
                [self.docker, "image", "inspect", name],
                capture_output=True,
                text=True,
                timeout=10,
                check=False,
            )
        except (OSError, subprocess.SubprocessError):
            return False
        return completed.returncode == 0

    # -- run ---------------------------------------------------------------

    def build_command(
        self,
        argv: Sequence[str],
        *,
        cwd: str = ".",
        name: str | None = None,
        env: Mapping[str, str] | None = None,
    ) -> list[str]:
        """Construct the full ``docker run`` argv without executing it.

        Keeping command construction separate makes the security flags
        testable on a machine without Docker. The tests assert every boundary
        flag; a refactor that removes one should fail loudly.
        """
        arguments = self._validate_argv(argv)
        container_cwd = self._container_cwd(cwd)
        container_name = name or f"mini-harness-{uuid.uuid4().hex[:12]}"

        command = [
            self.docker,
            "run",
            "--rm",
            "--name",
            container_name,
            "--network",
            "none",
            "--read-only",
            "--cap-drop",
            "ALL",
            "--security-opt",
            "no-new-privileges",
            "--pids-limit",
            str(self.config.pids_limit),
            "--memory",
            self.config.memory,
            "--memory-swap",
            self.config.memory,
            "--cpus",
            self.config.cpus,
            "--ulimit",
            f"nofile={self.config.nofile_limit}:{self.config.nofile_limit}",
            "--user",
            self.config.user,
            "--workdir",
            container_cwd,
            "--tmpfs",
            f"/tmp:rw,noexec,nosuid,size={self.config.tmpfs_size}",
            "--tmpfs",
            f"/run:rw,noexec,nosuid,size=8m",
            "--volume",
            f"{self.root}:/workspace:{self.config.workspace_mode}",
            "--env",
            "HOME=/tmp",
            "--env",
            "PYTHONIOENCODING=utf-8",
            "--env",
            "PYTHONDONTWRITEBYTECODE=1",
            "--env",
            "PYTHONNOUSERSITE=1",
            "--ipc",
            "none",
            "--stop-timeout",
            "2",
        ]

        if self.config.init:
            # ``--init`` runs a small reaper as PID 1 so orphaned grandchildren
            # do not linger inside the container.
            command.append("--init")

        # Extra environment is explicit and validated. The runner never passes
        # the host environment through.
        extra = dict(self.config.extra_env)
        if env:
            extra.update(env)
        for key in sorted(extra):
            self._validate_env(key, extra[key])
            command.extend(["--env", f"{key}={extra[key]}"])

        command.append(self.config.image)
        command.extend(arguments)
        return command

    def run(
        self,
        argv: Sequence[str],
        *,
        cwd: str = ".",
        env: Mapping[str, str] | None = None,
        name: str | None = None,
    ) -> RunResult:
        """Run one command in a fresh container and capture bounded output."""
        self.require_available()

        container_name = name or f"mini-harness-{uuid.uuid4().hex[:12]}"
        command = self.build_command(argv, cwd=cwd, name=container_name, env=env)
        arguments = tuple(str(item) for item in argv)

        started = time.monotonic()
        try:
            process = subprocess.Popen(
                command,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                close_fds=True,
                start_new_session=(os.name != "nt"),
            )
        except FileNotFoundError as exc:
            raise DockerError("DOCKER_MISSING", f"docker not found: {exc}") from exc
        except OSError as exc:
            raise DockerError("RUN_FAILED", f"could not start docker: {exc}") from exc

        out_capture = _Capture(self.config.max_output_bytes)
        err_capture = _Capture(self.config.max_output_bytes)
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
            process.wait(timeout=self.config.timeout_seconds)
        except subprocess.TimeoutExpired:
            timed_out = True
            # Removing by name is more reliable than killing the CLI alone:
            # the daemon owns the container and will keep it running otherwise.
            self._remove_container(container_name)
            try:
                process.kill()
            except OSError:
                pass
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                pass

        out_thread.join(timeout=5)
        err_thread.join(timeout=5)
        duration = time.monotonic() - started

        return RunResult(
            argv=arguments,
            container_name=container_name,
            returncode=process.returncode,
            stdout=out_capture.text().replace("\r\n", "\n"),
            stderr=err_capture.text().replace("\r\n", "\n"),
            timed_out=timed_out,
            truncated=out_capture.truncated or err_capture.truncated,
            duration_seconds=duration,
        )

    # -- helpers -----------------------------------------------------------

    def _validate_argv(self, argv: Sequence[str]) -> list[str]:
        """Reject malformed argv before it reaches the Docker CLI."""
        if isinstance(argv, (str, bytes)):
            raise DockerError("ARGS", "argv must be a list, not a string")
        arguments = list(argv)
        if not arguments:
            raise DockerError("ARGS", "argv must not be empty")
        for argument in arguments:
            if not isinstance(argument, str):
                raise DockerError("ARGS", "every argv element must be a string")
            if "\x00" in argument:
                raise DockerError("ARGS", "argument contains a NUL byte")
            if len(argument) > 8192:
                raise DockerError("ARGS", "argument is too long")
        return arguments

    def _container_cwd(self, cwd: str) -> str:
        """Translate a workspace-relative cwd into ``/workspace/...``."""
        if not isinstance(cwd, str):
            raise DockerError("CWD", "cwd must be a string")
        try:
            resolved = self.path_policy.resolve_read(cwd)
        except PolicyError as exc:
            raise DockerError("CWD", str(exc)) from exc

        if not resolved.absolute.is_dir():
            raise DockerError("CWD", f"not a folder: {cwd}")

        if resolved.relative == ".":
            return "/workspace"
        return f"/workspace/{resolved.relative}"

    @staticmethod
    def _validate_env(key: str, value: str) -> None:
        """Allow simple environment names and reject control characters."""
        if not isinstance(key, str) or not _ENV_NAME.match(key):
            raise DockerError("ENV", f"invalid environment name: {key!r}")
        if not isinstance(value, str):
            raise DockerError("ENV", f"environment value for {key} must be a string")
        if any(ch in value for ch in "\x00\r\n"):
            raise DockerError("ENV", f"environment value for {key} contains a control character")

    def _remove_container(self, name: str) -> None:
        """Best-effort cleanup after a timeout."""
        try:
            subprocess.run(
                [self.docker, "rm", "-f", name],
                capture_output=True,
                text=True,
                timeout=15,
                check=False,
            )
        except (OSError, subprocess.SubprocessError):
            pass
