"""command_tool.py - the model-facing wrapper around CommandRunner.

The tool accepts one shape only:

    {"argv": ["python", "-c", "print('hello')"]}

There is no ``shell`` option and no command string. If the model wants a pipe,
it has to run a program that creates one, and that program must be on the
allowlist. This is stricter than a typical coding agent on purpose: the local
runner is a convenience layer, not a security boundary.
"""

from __future__ import annotations

from typing import Any

from .local_runner import CommandError, CommandResult, CommandRunner


def format_result(result: CommandResult) -> str:
    """Render a completed command as a compact observation.

    Empty streams are labelled instead of rendered as an ambiguous blank line.
    The timeout and truncation flags are always visible so the model cannot
    mistake a partial result for a complete one.
    """
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


def run_command_tool(runner: CommandRunner, args: dict[str, Any]) -> str:
    """Validate ``argv``, run it, and return an observation string."""
    argv = args.get("argv")

    if not isinstance(argv, list) or not argv:
        return "ERROR[ARGS]: argv must be a non-empty list of strings"
    if not all(isinstance(item, str) for item in argv):
        return "ERROR[ARGS]: every argv element must be a string"

    program, *rest = argv
    cwd = args.get("cwd", ".")
    if not isinstance(cwd, str):
        return "ERROR[ARGS]: cwd must be a string"

    try:
        result = runner.run(program, rest, cwd=cwd)
    except CommandError as exc:
        # This covers DENIED, CWD and ARGS refusals from the runner.
        return f"ERROR[{exc.code}]: {exc.message}"

    body = format_result(result)

    if result.timed_out:
        return f"ERROR[TIMEOUT]: command exceeded its time limit\n{body}"
    if result.returncode != 0:
        return f"ERROR[EXIT]: command failed\n{body}"
    return f"OK\n{body}"
