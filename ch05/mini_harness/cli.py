"""cli.py - the offline end-to-end demo for the finished mini harness.

There is deliberately no API client in this book's repository. The sandbox is
the subject; a deterministic ``ScriptedModel`` keeps the demo runnable on a
plane, in CI, and on a laptop without a key.

A real deployment swaps ``ScriptedModel`` for an LLM adapter that implements
``Agent``'s ``Model`` protocol. The tools, the sandbox, the Docker boundary,
the step limit and the audit log stay exactly the same.
"""

from __future__ import annotations

import argparse
import tempfile
from pathlib import Path

from .agent import Agent, ModelReply, ScriptedModel
from .audit import AuditLog, AuditError
from .docker_runner import DockerError, DockerRunner
from .sandbox import Sandbox
from .toolbox import Toolbox

CHAPTER_DIR = Path(__file__).resolve().parents[1]
DOCKER_DIR = CHAPTER_DIR / "docker"


def _parser() -> argparse.ArgumentParser:
    """Build the CLI parser. Kept small on purpose."""
    parser = argparse.ArgumentParser(
        prog="python -m mini_harness",
        description="Mini Python coding harness with a Docker sandbox (offline demo).",
    )
    parser.add_argument(
        "--demo",
        action="store_true",
        help="run the scripted end-to-end demo (default)",
    )
    parser.add_argument(
        "--build",
        action="store_true",
        help="build the sandbox image before running the demo",
    )
    parser.add_argument(
        "--workspace",
        default=None,
        help="workspace folder to use; defaults to a temporary folder",
    )
    parser.add_argument(
        "--max-steps",
        type=int,
        default=8,
        help="hard cap on model/tool loop iterations",
    )
    return parser


def _print_run(result) -> None:
    """Print a compact transcript of one agent run."""
    for entry in result.transcript:
        role = entry.get("role")
        content = entry.get("content")

        if role == "user":
            print(f"TASK: {content}")
        elif role == "assistant" and isinstance(content, dict):
            tool = content.get("tool")
            args = content.get("args")
            print(f"\nCALL: {tool}({args})")
        elif role == "assistant":
            print(f"\nFINAL: {content}")
        elif role == "tool":
            # Show the whole observation, but keep long output readable.
            text = str(content)
            if len(text) > 1200:
                text = text[:1200] + "\n...[observation clipped in console]"
            print(f"OBSERVE [{entry.get('name')}]:\n{text}")

    print(f"\nstopped: {result.stopped} after {result.steps} step(s)")


def _demo_replies() -> list[ModelReply]:
    """The scripted task: write a file, read it, run it in the container."""
    return [
        ModelReply.call(
            "write_file",
            {
                "path": "hello.py",
                "content": "print('hello from the sandboxed harness')\n",
            },
        ),
        ModelReply.call("read_file", {"path": "hello.py"}),
        ModelReply.call("run_command", {"argv": ["python", "hello.py"], "cwd": "."}),
        ModelReply.final(
            "Wrote hello.py, read it back, and ran it through the Docker sandbox. "
            "If the run_command observation says DOCKER_MISSING, build the image and "
            "start Docker, then rerun with --build."
        ),
    ]


def run_demo(workspace: Path, *, build: bool, max_steps: int) -> int:
    """Run the fixed scenario against ``workspace`` and print the audit check."""
    sandbox = Sandbox(workspace)
    runner = DockerRunner(workspace)

    if build:
        try:
            output = runner.build(DOCKER_DIR)
        except DockerError as exc:
            print(f"build failed -> {exc}")
            return 1
        print(output[-1500:])

    # The audit sits beside the workspace, not inside it, so file tools cannot
    # edit their own trail through the sandbox.
    audit_path = workspace.parent / "audit" / "events.jsonl"
    try:
        audit = AuditLog(audit_path)
    except AuditError as exc:
        print(f"audit error -> {exc}")
        return 1

    toolbox = Toolbox(sandbox=sandbox, runner=runner)
    model = ScriptedModel(_demo_replies())
    agent = Agent(toolbox, model, audit, max_steps=max_steps)

    print(f"workspace: {sandbox.root}")
    print(f"audit:     {audit.path}")
    print(f"docker:    {'available' if runner.check_available() else 'NOT available (command step will be denied)'}")
    print()

    result = agent.run("Write hello.py, read it, then run it in the sandbox.")
    _print_run(result)

    print(f"\naudit chain verifies: {audit.verify()}")
    print(f"audit events: {len(audit.events())}")
    return 0


def main(argv: list[str] | None = None) -> int:
    """CLI entry point."""
    args = _parser().parse_args(argv)

    if args.workspace is not None:
        workspace = Path(args.workspace).expanduser().resolve()
        workspace.mkdir(parents=True, exist_ok=True)
        return run_demo(workspace, build=args.build, max_steps=args.max_steps)

    # A temporary lab is the default. Everything is cleaned up at exit, so a
    # demo run cannot leave a half-written file in the repository.
    with tempfile.TemporaryDirectory(prefix="mini-harness-") as temp:
        workspace = Path(temp) / "workspace"
        workspace.mkdir()
        return run_demo(workspace, build=args.build, max_steps=args.max_steps)


if __name__ == "__main__":
    raise SystemExit(main())
