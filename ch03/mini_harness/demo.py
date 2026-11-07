"""demo.py - run commands locally with an allowlist, clean env and limits.

Run from ``ch03/``:

    python -m mini_harness.demo

The final section deliberately proves that this is *not* a filesystem jail: the
child Python process can still read a file outside the workspace. That is the
motivation for the Docker chapter, not a bug to patch here.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

from .command_tool import run_command_tool
from .local_runner import CommandRunner, Limits


def show(label: str, observation: str) -> None:
    """Print one command observation with indentation."""
    print(f"\n{label}\n  {observation.replace(chr(10), chr(10) + '  ')}")


def main() -> int:
    """Exercise the runner's normal path and each refusal path."""
    with tempfile.TemporaryDirectory(prefix="sandbox-ch03-") as temp:
        workspace = Path(temp) / "workspace"
        workspace.mkdir()
        (workspace / "data.txt").write_text("inside data\n", encoding="utf-8")

        # A file the command should not be able to reach once we have a real
        # container. For now the local runner can still read it.
        outside = Path(temp) / "outside.txt"
        outside.write_text("outside data\n", encoding="utf-8")

        # A sentinel secret in the parent environment. The child must not see
        # it because ``_clean_environment`` builds a small env from scratch.
        os.environ["BOOK_SECRET_SENTINEL"] = "do-not-leak"

        runner = CommandRunner(
            workspace,
            limits=Limits(timeout_seconds=2.0, max_output_bytes=300),
        )

        show(
            "normal command",
            run_command_tool(
                runner,
                {"argv": ["python", "-c", "print('hello from child')"]},
            ),
        )
        show(
            "environment is scrubbed",
            run_command_tool(
                runner,
                {
                    "argv": [
                        "python",
                        "-c",
                        "import os; print(os.environ.get('BOOK_SECRET_SENTINEL', 'MISSING'))",
                    ]
                },
            ),
        )
        show(
            "program not on allowlist",
            run_command_tool(runner, {"argv": ["sh", "-c", "echo nope"]}),
        )
        show(
            "timeout kills the tree",
            run_command_tool(
                runner,
                {"argv": ["python", "-c", "import time; time.sleep(5)"]},
            ),
        )
        show(
            "output cap",
            run_command_tool(
                runner,
                {"argv": ["python", "-c", "print('x' * 5000)"]},
            ),
        )
        show(
            "working directory escape",
            run_command_tool(
                runner,
                {"argv": ["python", "-c", "print('no')"], "cwd": "../.."},
            ),
        )

        # This command intentionally reads outside the workspace. It succeeds,
        # which is the honest lesson of Stage 3.
        show(
            "local runner is not a filesystem jail",
            run_command_tool(
                runner,
                {
                    "argv": [
                        "python",
                        "-c",
                        f"print(open({str(outside)!r}).read().strip())",
                    ]
                },
            ),
        )

        print(
            "\nLesson: argv + allowlist + clean env + timeout are good hygiene,\n"
            "but the child still runs as you. Stage 4 adds the container wall."
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
