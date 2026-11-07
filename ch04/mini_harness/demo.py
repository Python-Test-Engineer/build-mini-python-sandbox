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

from .docker_runner import DockerError, DockerRunner


def banner(text: str) -> None:
    """Print a small section heading."""
    print(f"\n== {text} ==")


def main() -> int:
    """Show the hardening recipe and optionally exercise it."""
    with tempfile.TemporaryDirectory(prefix="sandbox-ch04-") as temp:
        workspace = Path(temp) / "workspace"
        workspace.mkdir()
        (workspace / "notes.txt").write_text("inside\n", encoding="utf-8")

        runner = DockerRunner(workspace)

        banner("the docker run recipe")
        command = runner.build_command(
            ["python", "-c", "print('hello from the container')"],
            cwd=".",
            name="demo-container",
        )
        # Render one flag per line so the security boundary is readable.
        for index, item in enumerate(command):
            prefix = "$" if index == 0 else " "
            print(f"{prefix} {item}")

        banner("availability")
        available = runner.check_available()
        print("docker daemon available:", available)
        if not available:
            print("Install Docker Desktop/Engine, start it, then rerun this demo.")
            print("The command above is still the exact recipe Stage 4 uses.")
            return 0

        image_present = runner.image_exists()
        print("image present:", image_present, "->", runner.config.image)

        if "--build" in sys.argv or not image_present:
            if "--build" not in sys.argv:
                print("Image is missing. Run: python -m mini_harness.demo --build")
                print("(Building needs network access to pull the Python base image.)")
                return 0
            banner("building")
            docker_dir = Path(__file__).resolve().parents[1] / "docker"
            output = runner.build(docker_dir)
            print(output[-2000:])

        banner("normal command")
        try:
            result = runner.run(["python", "-c", "print('hello from the container')"])
        except DockerError as exc:
            print(f"ERROR[{exc.code}]: {exc.message}")
            return 1
        print(f"exit={result.returncode} in {result.duration_seconds:.2f}s")
        print("stdout:", result.stdout.strip())

        banner("read-only root filesystem")
        result = runner.run(
            ["python", "-c", "open('/etc/passwd', 'a').write('nope')"]
        )
        print(f"exit={result.returncode} (non-zero means the write was refused)")
        print("stderr:", (result.stderr.strip().splitlines() or ["(empty)"])[-1])

        banner("no network")
        result = runner.run(
            [
                "python",
                "-c",
                "import socket; socket.create_connection(('1.1.1.1', 80), timeout=2)",
            ]
        )
        print(f"exit={result.returncode} (non-zero means the connection failed)")
        print("stderr:", (result.stderr.strip().splitlines() or ["(empty)"])[-1])

        banner("workspace is writable")
        result = runner.run(
            ["python", "-c", "open('/workspace/from-container.txt', 'w').write('ok')"]
        )
        print(f"exit={result.returncode}")
        print("stdout:", result.stdout.strip())
        print(
            "file exists on host after run:",
            (workspace / "from-container.txt").exists(),
        )

        print(
            "\nLesson: the container owns the boundary; the Python path policy\n"
            "still matters, but it is no longer the only lock on the door."
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
