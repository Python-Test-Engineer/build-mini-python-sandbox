"""Tests for the combined file + Docker toolbox.

The Docker runner is replaced with a fake in most tests. The fake records the
call and returns a prepared ``RunResult``; no daemon is needed. A real
integration test at the end skips when Docker is unavailable.
"""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from mini_harness.docker_runner import DockerError, DockerRunner, RunResult
from mini_harness.sandbox import Sandbox
from mini_harness.toolbox import Toolbox


class FakeRunner:
    """A tiny stand-in for DockerRunner with a controllable result."""

    def __init__(self, result: RunResult | None = None, error: DockerError | None = None) -> None:
        self.result = result
        self.error = error
        self.calls: list[tuple[list[str], str]] = []

    def run(self, argv, *, cwd="."):
        self.calls.append((list(argv), cwd))
        if self.error is not None:
            raise self.error
        assert self.result is not None
        return self.result


def ok_result(stdout: str = "hi\n") -> RunResult:
    """Build a successful container result for the fake."""
    return RunResult(
        argv=("python", "-c", "print('hi')"),
        container_name="fake",
        returncode=0,
        stdout=stdout,
        stderr="",
        timed_out=False,
        truncated=False,
        duration_seconds=0.1,
    )


class ToolboxTests(unittest.TestCase):
    """File tools and command tools behind one dispatch point."""

    def setUp(self) -> None:
        self.temp = self.enterContext(tempfile.TemporaryDirectory(prefix="toolbox-test-"))
        self.root = Path(self.temp) / "workspace"
        self.root.mkdir()
        (self.root / "notes.txt").write_bytes(b"alpha\nbeta\n")
        self.sandbox = Sandbox(self.root)

    def test_file_write_and_read(self) -> None:
        toolbox = Toolbox(self.sandbox, FakeRunner(ok_result()))
        written = toolbox.run("write_file", {"path": "new.txt", "content": "hello"})
        self.assertIn("OK", written)
        read = toolbox.run("read_file", {"path": "new.txt"})
        self.assertIn("hello", read)

    def test_file_path_escape_is_an_observation(self) -> None:
        toolbox = Toolbox(self.sandbox, FakeRunner(ok_result()))
        result = toolbox.run("read_file", {"path": "../outside.txt"})
        self.assertTrue(result.startswith("ERROR[PATH]"))

    def test_unknown_tool(self) -> None:
        toolbox = Toolbox(self.sandbox, FakeRunner(ok_result()))
        result = toolbox.run("nope", {})
        self.assertTrue(result.startswith("ERROR[UNKNOWN_TOOL]"))

    def test_specs_include_run_command(self) -> None:
        toolbox = Toolbox(self.sandbox, FakeRunner(ok_result()))
        names = [spec.name for spec in toolbox.specs()]
        self.assertIn("run_command", names)
        self.assertIn("read_file", names)
        self.assertIn("write_file", names)

    def test_run_command_success(self) -> None:
        fake = FakeRunner(ok_result("hello\n"))
        toolbox = Toolbox(self.sandbox, fake)
        result = toolbox.run("run_command", {"argv": ["python", "x.py"], "cwd": "sub"})
        self.assertTrue(result.startswith("OK\n"))
        self.assertIn("hello", result)
        self.assertEqual(fake.calls, [(["python", "x.py"], "sub")])

    def test_run_command_nonzero(self) -> None:
        fake = FakeRunner(
            RunResult(
                argv=("python",),
                container_name="fake",
                returncode=1,
                stdout="",
                stderr="bad\n",
                timed_out=False,
                truncated=False,
                duration_seconds=0.1,
            )
        )
        toolbox = Toolbox(self.sandbox, fake)
        result = toolbox.run("run_command", {"argv": ["python", "x.py"]})
        self.assertTrue(result.startswith("ERROR[EXIT]"))
        self.assertIn("bad", result)

    def test_run_command_timeout(self) -> None:
        fake = FakeRunner(
            RunResult(
                argv=("python",),
                container_name="fake",
                returncode=None,
                stdout="partial\n",
                stderr="",
                timed_out=True,
                truncated=False,
                duration_seconds=20.0,
            )
        )
        toolbox = Toolbox(self.sandbox, fake)
        result = toolbox.run("run_command", {"argv": ["python", "x.py"]})
        self.assertTrue(result.startswith("ERROR[TIMEOUT]"))
        self.assertIn("partial", result)

    def test_run_command_docker_missing(self) -> None:
        fake = FakeRunner(error=DockerError("DOCKER_MISSING", "no daemon"))
        toolbox = Toolbox(self.sandbox, fake)
        result = toolbox.run("run_command", {"argv": ["python", "x.py"]})
        self.assertEqual(result, "ERROR[DOCKER_MISSING]: no daemon")

    def test_run_command_bad_argv(self) -> None:
        toolbox = Toolbox(self.sandbox, FakeRunner(ok_result()))
        result = toolbox.run("run_command", {"argv": "python x.py"})
        self.assertTrue(result.startswith("ERROR[ARGS]"))

    def test_unexpected_runner_error_is_internal(self) -> None:
        class BrokenRunner:
            def run(self, argv, *, cwd="."):
                raise ValueError("broken runner")

        toolbox = Toolbox(self.sandbox, BrokenRunner())  # type: ignore[arg-type]
        result = toolbox.run("run_command", {"argv": ["python", "x.py"]})
        self.assertTrue(result.startswith("ERROR[INTERNAL]"))


class DockerIntegrationTests(unittest.TestCase):
    """One real container run, when the environment supports it."""

    def setUp(self) -> None:
        self.temp = self.enterContext(tempfile.TemporaryDirectory(prefix="toolbox-docker-"))
        self.root = Path(self.temp) / "workspace"
        self.root.mkdir()
        self.runner = DockerRunner(self.root)
        if not self.runner.check_available():
            self.skipTest("Docker daemon is not available")
        if not self.runner.image_exists():
            self.skipTest("build the image first: docker build -t mini-harness-python:latest docker")

    def test_run_command_in_container(self) -> None:
        toolbox = Toolbox(Sandbox(self.root), self.runner)
        result = toolbox.run("run_command", {"argv": ["python", "-c", "print('real container')"]})
        self.assertTrue(result.startswith("OK\n"))
        self.assertIn("real container", result)


if __name__ == "__main__":
    unittest.main()
