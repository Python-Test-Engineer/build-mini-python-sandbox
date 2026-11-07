"""Tests for the combined file + Docker toolbox.

The Docker runner is replaced with a fake in most tests. The fake records the
call and returns a prepared ``RunResult``; no daemon is needed. A real
integration test at the end skips when Docker is unavailable.

The toolbox is the single dispatch point the agent uses. It routes ``read_file``,
``write_file`` and friends to the sandbox, and ``run_command`` to the runner.
Whatever happens, it returns a string observation with a stable ``ERROR[...]``
prefix instead of raising. These tests pin down that contract.
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
    """A tiny stand-in for DockerRunner with a controllable result.

    It records every call so tests can assert that the toolbox passed the right
    argv and cwd, and it can either return a prepared ``RunResult`` or raise a
    prepared ``DockerError``.
    """

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
        # A private workspace with a two-line file for the file-tool tests.
        self.temp = self.enterContext(tempfile.TemporaryDirectory(prefix="toolbox-test-"))
        self.root = Path(self.temp) / "workspace"
        self.root.mkdir()
        (self.root / "notes.txt").write_bytes(b"alpha\nbeta\n")
        self.sandbox = Sandbox(self.root)

    # -- file tool routing -------------------------------------------------

    def test_file_write_and_read(self) -> None:
        """The toolbox routes file tools to the sandbox correctly.

        A write followed by a read round-trip proves dispatch works and that the
        sandbox is the component doing the I/O.
        """
        toolbox = Toolbox(self.sandbox, FakeRunner(ok_result()))
        written = toolbox.run("write_file", {"path": "new.txt", "content": "hello"})
        self.assertIn("OK", written)
        read = toolbox.run("read_file", {"path": "new.txt"})
        self.assertIn("hello", read)

    def test_file_path_escape_is_an_observation(self) -> None:
        """A path escape through the toolbox is an ``ERROR[PATH]`` string."""
        toolbox = Toolbox(self.sandbox, FakeRunner(ok_result()))
        result = toolbox.run("read_file", {"path": "../outside.txt"})
        self.assertTrue(result.startswith("ERROR[PATH]"))

    def test_unknown_tool(self) -> None:
        """An unknown tool name is reported, not raised."""
        toolbox = Toolbox(self.sandbox, FakeRunner(ok_result()))
        result = toolbox.run("nope", {})
        self.assertTrue(result.startswith("ERROR[UNKNOWN_TOOL]"))

    def test_specs_include_run_command(self) -> None:
        """The tool specs list every tool the model is allowed to call.

        Specs are how the agent discovers its capabilities, so the file tools
        and the command tool must all appear.
        """
        toolbox = Toolbox(self.sandbox, FakeRunner(ok_result()))
        names = [spec.name for spec in toolbox.specs()]
        self.assertIn("run_command", names)
        self.assertIn("read_file", names)
        self.assertIn("write_file", names)

    # -- command tool routing ---------------------------------------------

    def test_run_command_success(self) -> None:
        """A successful command is rendered as ``OK`` plus its stdout.

        The fake records the call, letting us assert that the toolbox forwarded
        the exact argv and cwd the model supplied.
        """
        fake = FakeRunner(ok_result("hello\n"))
        toolbox = Toolbox(self.sandbox, fake)
        result = toolbox.run("run_command", {"argv": ["python", "x.py"], "cwd": "sub"})
        self.assertTrue(result.startswith("OK\n"))
        self.assertIn("hello", result)
        self.assertEqual(fake.calls, [(["python", "x.py"], "sub")])

    def test_run_command_nonzero(self) -> None:
        """A non-zero exit becomes ``ERROR[EXIT]`` with the captured stderr.

        The command did run; the program failed. The model needs the error text
        to decide what to do next.
        """
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
        """A timeout becomes ``ERROR[TIMEOUT]`` and keeps partial output.

        Partial output is valuable for debugging, so it must survive in the
        observation rather than being discarded.
        """
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
        """A missing Docker runtime is a clean observation, not a traceback.

        The whole demo still works on a laptop without Docker because the
        toolbox converts ``DockerError`` into ``ERROR[DOCKER_MISSING]``.
        """
        fake = FakeRunner(error=DockerError("DOCKER_MISSING", "no daemon"))
        toolbox = Toolbox(self.sandbox, fake)
        result = toolbox.run("run_command", {"argv": ["python", "x.py"]})
        self.assertEqual(result, "ERROR[DOCKER_MISSING]: no daemon")

    def test_run_command_bad_argv(self) -> None:
        """A string argv from the model is refused with ``ERROR[ARGS]``."""
        toolbox = Toolbox(self.sandbox, FakeRunner(ok_result()))
        result = toolbox.run("run_command", {"argv": "python x.py"})
        self.assertTrue(result.startswith("ERROR[ARGS]"))

    def test_unexpected_runner_error_is_internal(self) -> None:
        """An unexpected runner bug is contained as ``ERROR[INTERNAL]``.

        A ``ValueError`` is not a known policy failure, so the toolbox labels it
        internal. The key property is that even a programming error in a runner
        does not escape and crash the agent loop.
        """
        class BrokenRunner:
            def run(self, argv, *, cwd="."):
                raise ValueError("broken runner")

        toolbox = Toolbox(self.sandbox, BrokenRunner())  # type: ignore[arg-type]
        result = toolbox.run("run_command", {"argv": ["python", "x.py"]})
        self.assertTrue(result.startswith("ERROR[INTERNAL]"))


class DockerIntegrationTests(unittest.TestCase):
    """One real container run, when the environment supports it."""

    def setUp(self) -> None:
        # Skip with an actionable message when Docker or the image is missing.
        self.temp = self.enterContext(tempfile.TemporaryDirectory(prefix="toolbox-docker-"))
        self.root = Path(self.temp) / "workspace"
        self.root.mkdir()
        self.runner = DockerRunner(self.root)
        if not self.runner.check_available():
            self.skipTest("Docker daemon is not available")
        if not self.runner.image_exists():
            self.skipTest("build the image first: docker build -t mini-harness-python:latest docker")

    def test_run_command_in_container(self) -> None:
        """The full toolbox-to-container path works end to end.

        This complements the offline tests: they prove the argv is correct,
        while this proves a real container accepts it and returns output.
        """
        toolbox = Toolbox(Sandbox(self.root), self.runner)
        result = toolbox.run("run_command", {"argv": ["python", "-c", "print('real container')"]})
        self.assertTrue(result.startswith("OK\n"))
        self.assertIn("real container", result)


if __name__ == "__main__":
    unittest.main()
