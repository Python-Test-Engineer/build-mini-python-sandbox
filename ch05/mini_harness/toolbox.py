"""toolbox.py - one dispatch point for every tool the agent may call.

The toolbox is deliberately thin. File tools already have their own validation
and sandbox layer; the command tool has the Docker layer. The toolbox only:

* exposes a single tool list for the prompt/model;
* routes by name;
* keeps the "unknown tool" answer consistent.

It does not add a second policy. One policy per boundary is easier to audit.
"""

from __future__ import annotations

from typing import Any

from . import file_tools
from .docker_runner import DockerRunner
from .docker_tools import RUN_COMMAND_SPEC, run_command_tool
from .sandbox import Sandbox

# File tool names are derived from the existing specs so a new file tool
# cannot be added without also being visible here.
FILE_TOOL_NAMES = frozenset(spec.name for spec in file_tools.TOOL_SPECS)


class Toolbox:
    """Route model tool calls to the file sandbox or the Docker sandbox."""

    def __init__(self, sandbox: Sandbox, runner: DockerRunner) -> None:
        self.sandbox = sandbox
        self.runner = runner

    def specs(self) -> list[object]:
        """Return the combined tool contract for the prompt/model."""
        return [*file_tools.TOOL_SPECS, RUN_COMMAND_SPEC]

    def run(self, name: str, args: dict[str, Any] | None = None) -> str:
        """Execute one tool and return an observation string.

        Expected failures are observations. Unexpected failures are labelled
        ``INTERNAL`` and never escape into the agent loop.
        """
        arguments = {} if args is None else args

        try:
            if name == "run_command":
                return run_command_tool(self.runner, arguments)
            if name in FILE_TOOL_NAMES:
                return file_tools.run_tool(self.sandbox, name, arguments)
            return f"ERROR[UNKNOWN_TOOL]: no tool named {name!r}"
        except Exception as exc:  # noqa: BLE001 - the loop must not crash
            # File and command tools convert their own expected failures. This
            # is the last line of defence for a bug in either layer.
            return f"ERROR[INTERNAL]: {type(exc).__name__}: {exc}"
