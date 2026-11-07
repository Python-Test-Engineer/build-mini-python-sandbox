"""demo.py - run commands locally with an allowlist, clean env and limits.

Run from ``ch03/``:

    python -m mini_harness.demo

The final section deliberately proves that this is *not* a filesystem jail: the
child Python process can still read a file outside the workspace. That is the
motivation for the Docker chapter, not a bug to patch here.
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

# A direct script run (``uv run demo.py``) has no package context. Add the
# chapter directory so ``mini_harness`` is importable; module runs skip this.
if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from mini_harness.command_tool import run_command_tool
from mini_harness.local_runner import CommandRunner, Limits
from mini_harness.ui import UI


def show(ui: UI, label: str, observation: str) -> None:
    """Show one command observation as a colour-coded card."""
    ui.result(label, observation)


def main() -> int:
    """Exercise the runner's normal path and each refusal path."""
    ui = UI(accent="yellow", title="Stage 3 - Running code locally")
    ui.header(
        subtitle="Argv, a clean environment, a timeout and bounded output.",
        badge="hygiene is not a boundary",
    )

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

        ui.section("the seven controls")
        show(
            ui,
            "normal command",
            run_command_tool(
                runner,
                {"argv": ["python", "-c", "print('hello from child')"]},
            ),
        )
        show(
            ui,
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
            ui,
            "program not on allowlist",
            run_command_tool(runner, {"argv": ["sh", "-c", "echo nope"]}),
        )
        show(
            ui,
            "timeout kills the tree",
            run_command_tool(
                runner,
                {"argv": ["python", "-c", "import time; time.sleep(5)"]},
            ),
        )
        show(
            ui,
            "output cap",
            run_command_tool(
                runner,
                {"argv": ["python", "-c", "print('x' * 5000)"]},
            ),
        )
        show(
            ui,
            "working directory escape",
            run_command_tool(
                runner,
                {"argv": ["python", "-c", "print('no')"], "cwd": "../.."},
            ),
        )

        ui.explain(
            "the seven controls",
            "A normal command runs. The secret sentinel is absent, the "
            "non-allowlisted program is denied, the sleeping child is killed, "
            "output is capped, and the escaping cwd is refused.",
            "Argv, an absolute allowlist, a clean environment, a timeout, "
            "tree kill, output caps and rlimits remove the easy accidents. "
            "Each refusal is visible in the same observation shape.",
        )

        # This command intentionally reads outside the workspace. It succeeds,
        # which is the honest lesson of Stage 3.
        ui.section("the honest limit")
        show(
            ui,
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

        ui.explain(
            "the limit of the local runner",
            "The child process can still read a file outside the workspace.",
            "The runner controls how a program starts and how long it runs; "
            "it does not change which files or network the process can reach. "
            "That is why Stage 4 moves the command into a container.",
        )

        ui.done(
            "Lesson: argv + allowlist + clean env + timeout are good hygiene, "
            "but the child still runs as you. Stage 4 adds the container wall."
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
