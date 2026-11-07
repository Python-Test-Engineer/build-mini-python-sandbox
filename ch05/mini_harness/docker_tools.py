"""docker_tools.py - the model-facing command tool for the container.

The model supplies an argv list. It never supplies a shell string. The
``DockerRunner`` builds the hardened ``docker run`` command and the result is
rendered as one observation, with timeout and truncation visible.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .docker_runner import DockerError, DockerRunner, RunResult


@dataclass(frozen=True)
class DockerToolSpec:
    """Prompt-visible contract for the container command tool."""

    name: str
    description: str
    args: tuple[str, ...]


RUN_COMMAND_SPEC = DockerToolSpec(
    "run_command",
    "Run an argv command inside a no-network, read-only-root Docker sandbox. "
    "The workspace is mounted at /workspace. Use Python or other tools present "
    "in the sandbox image; do not use shell syntax.",
    ("argv", "cwd"),
)


def format_result(result: RunResult) -> str:
    """Render a container result as a bounded, readable observation."""
    status = "TIMEOUT" if result.timed_out else f"exit={result.returncode}"
    header = f"{status} in {result.duration_seconds:.2f}s"
    if result.truncated:
        header += " (output truncated)"

    stdout = result.stdout if result.stdout else "(empty)"
    stderr = result.stderr if result.stderr else "(empty)"

    return (
        f"{header}\n"
        f"--- stdout ---\n{stdout}\n"
        f"--- stderr ---\n{stderr}"
    )


def run_command_tool(runner: DockerRunner, args: dict[str, Any]) -> str:
    """Validate ``argv``, run it in a container, and return an observation."""
    argv = args.get("argv")
    if not isinstance(argv, list) or not argv:
        return "ERROR[ARGS]: argv must be a non-empty list of strings"
    if not all(isinstance(item, str) for item in argv):
        return "ERROR[ARGS]: every argv element must be a string"

    cwd = args.get("cwd", ".")
    if not isinstance(cwd, str):
        return "ERROR[ARGS]: cwd must be a string"

    try:
        result = runner.run(argv, cwd=cwd)
    except DockerError as exc:
        return f"ERROR[{exc.code}]: {exc.message}"

    body = format_result(result)
    if result.timed_out:
        return f"ERROR[TIMEOUT]: command exceeded its time limit\n{body}"
    if result.returncode != 0:
        return f"ERROR[EXIT]: command failed\n{body}"
    return f"OK\n{body}"
