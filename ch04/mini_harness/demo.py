"""demo.py - inspect the Docker command, then run it when Docker is present.

Run from ``ch04/``:

    python -m mini_harness.demo            # show the recipe, run if possible
    python -m mini_harness.demo --build    # build the image first

The first half always works, even on a laptop without Docker: it prints the
exact ``docker run`` argv that the runner would execute. The second half is
optional and skips cleanly when the daemon or image is missing.
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

# A direct script run (``uv run demo.py``) has no package context. Add the
# chapter directory so ``mini_harness`` is importable; module runs skip this.
if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from mini_harness.docker_runner import DockerError, DockerRunner
from mini_harness.ui import UI


def main() -> int:
    """Show the hardening recipe and optionally exercise it."""
    ui = UI(accent="blue", title="Stage 4 - The Docker boundary")
    ui.header(
        subtitle="The container owns the boundary; the flags are the contract.",
        badge="no network - read-only root - no privileges",
    )

    with tempfile.TemporaryDirectory(prefix="sandbox-ch04-") as temp:
        workspace = Path(temp) / "workspace"
        workspace.mkdir()
        (workspace / "notes.txt").write_text("inside\n", encoding="utf-8")

        runner = DockerRunner(workspace)

        ui.section("the docker run recipe")
        command = runner.build_command(
            ["python", "-c", "print('hello from the container')"],
            cwd=".",
            name="demo-container",
        )
        ui.command(command, title="docker run")
        ui.explain(
            "the run recipe",
            "The command disables networking, mounts the root read-only, drops "
            "capabilities, sets a non-root user, applies CPU/memory/process/file "
            "limits, and mounts only the workspace.",
            "Each flag removes a class of escape or bounds a resource. The "
            "offline tests assert this exact argv, so deleting a hardening flag "
            "is a failing test rather than a silent regression.",
        )

        ui.section("availability")
        available = runner.check_available()
        ui.note(
            "Docker daemon",
            f"available: {available}",
            kind="success" if available else "warning",
        )
        if not available:
            ui.note(
                "Next step",
                "Install Docker Desktop/Engine and start it, then rerun this demo. "
                "The command above is still the exact recipe Stage 4 uses.",
                kind="info",
            )
            ui.explain(
                "the offline path",
                "No daemon is available, so the live boundary checks are skipped. "
                "The recipe is still printed in full.",
                "The security contract is inspectable without Docker. The "
                "integration tests need a running daemon and the built image; "
                "their absence must not hide the recipe or crash the demo.",
            )
            return 0

        image_present = runner.image_exists()
        ui.note(
            "Image",
            f"present: {image_present} -> {runner.config.image}",
            kind="success" if image_present else "warning",
        )

        if "--build" in sys.argv or not image_present:
            if "--build" not in sys.argv:
                ui.note(
                    "Image missing",
                    "Run: python -m mini_harness.demo --build "
                    "(building needs network access to pull the Python base image).",
                    kind="warning",
                )
                return 0
            ui.section("building")
            docker_dir = Path(__file__).resolve().parents[1] / "docker"
            output = runner.build(docker_dir)
            ui.note("Build output", output[-2000:], kind="info")

        ui.section("normal command")
        try:
            result = runner.run(["python", "-c", "print('hello from the container')"])
        except DockerError as exc:
            ui.note("Docker error", f"ERROR[{exc.code}]: {exc.message}", kind="error")
            return 1
        ui.note(
            "Result",
            f"exit={result.returncode} in {result.duration_seconds:.2f}s\n"
            f"stdout: {result.stdout.strip()}",
            kind="success" if result.returncode == 0 else "error",
        )
        ui.explain(
            "normal command",
            "The container runs Python and prints the hello message.",
            "The boundary is usable for ordinary work. A sandbox that cannot "
            "run the task is not a sandbox; it is just a refusal.",
        )

        ui.section("read-only root filesystem")
        result = runner.run(
            ["python", "-c", "open('/etc/passwd', 'a').write('nope')"]
        )
        ui.note(
            "Root write",
            f"exit={result.returncode} (non-zero means the write was refused)\n"
            f"stderr: {(result.stderr.strip().splitlines() or ['(empty)'])[-1]}",
            kind="success" if result.returncode != 0 else "error",
        )
        ui.explain(
            "read-only root",
            "Writing to /etc/passwd fails because the image filesystem is "
            "mounted read-only.",
            "A command cannot modify the base image, plant a persistent "
            "binary, or rewrite system configuration. The workspace is the "
            "only intentional write path.",
        )

        ui.section("no network")
        result = runner.run(
            [
                "python",
                "-c",
                "import socket; socket.create_connection(('1.1.1.1', 80), timeout=2)",
            ]
        )
        ui.note(
            "Network",
            f"exit={result.returncode} (non-zero means the connection failed)\n"
            f"stderr: {(result.stderr.strip().splitlines() or ['(empty)'])[-1]}",
            kind="success" if result.returncode != 0 else "error",
        )
        ui.explain(
            "network isolation",
            "The outbound connection fails inside the container.",
            "--network none removes the network namespace, so a command cannot "
            "fetch a payload or exfiltrate workspace data. It also means the "
            "demo cannot install packages at run time.",
        )

        ui.section("workspace is writable")
        result = runner.run(
            ["python", "-c", "open('/workspace/from-container.txt', 'w').write('ok')"]
        )
        ui.note(
            "Workspace",
            f"exit={result.returncode}\nstdout: {result.stdout.strip()}\n"
            f"file exists on host after run: {(workspace / 'from-container.txt').exists()}",
            kind="success" if result.returncode == 0 else "error",
        )
        ui.explain(
            "the workspace mount",
            "The command writes from-container.txt, and the host sees the file "
            "after the run.",
            "Read-only root does not mean read-only workspace. The workspace is "
            "the one deliberate bridge between the container and the host, and "
            "it should be the only one.",
        )

        ui.done(
            "Lesson: the container owns the boundary; the Python path policy "
            "still matters, but it is no longer the only lock on the door."
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
