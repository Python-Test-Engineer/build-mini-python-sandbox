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
from .ui import UI

CHAPTER_DIR = Path(__file__).resolve().parents[1]
DOCKER_DIR = CHAPTER_DIR / "docker"

# Short teaching blocks for the tool observations the scripted demo produces.
TOOL_EXPLANATIONS = {
    "write_file": (
        "write_file",
        "The sandbox writes hello.py through one atomic write: temp file, "
        "flush, fsync, then replace.",
        "The model never touches the host path directly. The path policy, the "
        "size limit and the atomic replace are all applied before the file "
        "becomes visible.",
    ),
    "read_file": (
        "read_file",
        "The file tool reads hello.py back with numbered lines.",
        "The observation is bounded and formatted for the model. A read is "
        "allowed here because the resolved path is inside the workspace.",
    ),
    "run_command": (
        "run_command",
        "The command runs inside the Docker sandbox, or returns "
        "ERROR[DOCKER_MISSING] when Docker is absent.",
        "Infrastructure absence is a failed tool call, not a crash. The loop "
        "sees the error and can still finish with a final answer.",
    ),
}


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


def _print_run(result, ui: UI) -> None:
    """Print a compact, colour-coded transcript of one agent run."""
    ui.section("transcript")
    for entry in result.transcript:
        role = entry.get("role")
        content = entry.get("content")

        if role == "user":
            ui.note("TASK:", str(content), kind="accent")
        elif role == "assistant" and isinstance(content, dict):
            tool = content.get("tool")
            args = content.get("args")
            ui.note("CALL:", f"{tool}({args})", kind="info")
        elif role == "assistant":
            ui.note("FINAL:", str(content), kind="success")
            ui.explain(
                "the final answer",
                "The agent returns a normal final response instead of another "
                "tool call.",
                "The transcript and audit still hold every action that led to "
                "this answer. The final text is not the only record.",
            )
        elif role == "tool":
            # Show the whole observation, but keep huge output readable.
            text = str(content)
            if len(text) > 1200:
                text = text[:1200] + "\n...[observation clipped in console]"
            name = entry.get("name")
            ui.result(f"OBSERVE [{name}]:", text)
            explanation = TOOL_EXPLANATIONS.get(str(name))
            if explanation:
                ui.explain(*explanation)
    ui.note(
        "Stopped",
        f"{result.stopped} after {result.steps} step(s)",
        kind="warning" if result.stopped != "final" else "success",
    )
    ui.explain(
        "the loop limit",
        "The loop stopped because the model returned a final answer, not "
        "because the step budget ran out.",
        "The step limit lives in the harness. A model may loop forever; the "
        "harness may not.",
    )


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
    ui = UI(accent="magenta", title="Stage 5 - The finished harness")
    ui.header(
        subtitle="Route tools, bound the loop, and leave a verifiable trail.",
        badge="offline demo - Docker optional",
    )

    sandbox = Sandbox(workspace)
    runner = DockerRunner(workspace)

    if build:
        ui.section("building the sandbox image")
        try:
            output = runner.build(DOCKER_DIR)
        except DockerError as exc:
            ui.note("Build failed", str(exc), kind="error")
            return 1
        ui.note("Build output", output[-1500:], kind="info")

    # The audit sits behind the workspace, not inside it, so file tools cannot
    # edit their own trail through the sandbox.
    audit_path = workspace.parent / "audit" / "events.jsonl"
    try:
        audit = AuditLog(audit_path)
    except AuditError as exc:
        ui.note("Audit error", str(exc), kind="error")
        return 1

    toolbox = Toolbox(sandbox=sandbox, runner=runner)
    model = ScriptedModel(_demo_replies())
    agent = Agent(toolbox, model, audit, max_steps=max_steps)

    docker_state = "available" if runner.check_available() else "NOT available (command step will be denied)"
    ui.table(
        "run context",
        ["Item", "Value"],
        [
            ["workspace", sandbox.root],
            ["audit", audit.path],
            ["docker", docker_state],
        ],
    )
    ui.explain(
        "the run context",
        "The workspace is the only writable folder. The audit sits beside "
        "it. Docker may be available or missing.",
        "The audit is outside the sandbox, so tools cannot edit their own "
        "trail. A missing Docker daemon becomes an observation, not a crash.",
    )

    result = agent.run("Write hello.py, read it, then run it in the sandbox.")
    _print_run(result, ui)

    verified = audit.verify()
    ui.note(
        "Audit",
        f"audit chain verifies: {verified}",
        kind="success" if verified else "error",
    )
    ui.note("Audit events", str(len(audit.events())), kind="info")
    ui.explain(
        "the audit chain",
        "Each audit event stores a sequence number, the previous hash and its "
        "own hash. verify() recomputes the chain from the start.",
        "Editing or deleting a middle event breaks the chain, so tampering is "
        "visible. The chain makes tampering detectable, not impossible.",
    )
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
