"""Tests for the local command runner.

Run from ``ch03``:

    python -m pytest -v

The tests use the running Python interpreter as the only program on the
allowlist. They do not need a network or a shell. pytest is the runner.
"""

from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from mini_harness.command_tool import run_command_tool
from mini_harness.local_runner import CommandError, CommandRunner, Limits


class LocalRunnerTests(unittest.TestCase):
    """One fresh workspace per test."""

    def setUp(self) -> None:
        self.temp = self.enterContext(tempfile.TemporaryDirectory(prefix="runner-test-"))
        self.root = Path(self.temp) / "workspace"
        self.root.mkdir()
        (self.root / "sub").mkdir()
        (self.root / "data.txt").write_text("inside\n", encoding="utf-8")
        self.outside = Path(self.temp) / "outside.txt"
        self.outside.write_text("outside\n", encoding="utf-8")
        self.runner = CommandRunner(
            self.root,
            limits=Limits(timeout_seconds=3.0, max_output_bytes=10_000),
        )

    def py(self, code: str, *, cwd: str = ".", **kwargs) -> object:
        """Shorthand for running a small Python program."""
        return self.runner.run("python", ["-c", code], cwd=cwd, **kwargs)

    def test_normal_command(self) -> None:
        result = self.py("print('hello')")
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout, "hello\n")
        self.assertTrue(result.ok)

    def test_stderr_is_captured(self) -> None:
        result = self.py("import sys; print('bad', file=sys.stderr)")
        self.assertEqual(result.stderr, "bad\n")

    def test_nonzero_exit(self) -> None:
        result = self.py("raise SystemExit(3)")
        self.assertEqual(result.returncode, 3)
        self.assertFalse(result.ok)

    def test_args_must_be_a_list(self) -> None:
        with self.assertRaises(CommandError) as exc:
            self.runner.run("python", "print('hi')")  # type: ignore[arg-type]
        self.assertEqual(exc.exception.code, "ARGS")

    def test_program_not_allowed(self) -> None:
        with self.assertRaises(CommandError) as exc:
            self.runner.run("definitely-not-allowed", [])
        self.assertEqual(exc.exception.code, "DENIED")

    def test_absolute_program_not_allowed(self) -> None:
        with self.assertRaises(CommandError) as exc:
            self.runner.run(sys.executable, ["-c", "print(1)"])
        self.assertEqual(exc.exception.code, "DENIED")

    def test_nul_argument_rejected(self) -> None:
        with self.assertRaises(CommandError) as exc:
            self.py("print('x')\x00")
        self.assertEqual(exc.exception.code, "ARGS")

    def test_cwd_escape_rejected(self) -> None:
        with self.assertRaises(CommandError) as exc:
            self.py("print(1)", cwd="../..")
        self.assertEqual(exc.exception.code, "CWD")

    def test_cwd_subdirectory(self) -> None:
        result = self.py("import os; print(os.path.basename(os.getcwd()))", cwd="sub")
        self.assertEqual(result.stdout.strip(), "sub")

    def test_environment_is_scrubbed(self) -> None:
        os.environ["BOOK_TEST_SECRET"] = "leak-me-if-you-can"
        result = self.py("import os; print(os.environ.get('BOOK_TEST_SECRET', 'MISSING'))")
        self.assertEqual(result.stdout.strip(), "MISSING")

    def test_timeout(self) -> None:
        runner = CommandRunner(
            self.root,
            limits=Limits(timeout_seconds=0.4, max_output_bytes=10_000),
        )
        result = runner.run("python", ["-c", "import time; time.sleep(5)"])
        self.assertTrue(result.timed_out)
        self.assertLess(result.duration_seconds, 4.0)

    def test_output_cap(self) -> None:
        runner = CommandRunner(
            self.root,
            limits=Limits(timeout_seconds=3.0, max_output_bytes=100),
        )
        result = runner.run("python", ["-c", "print('x' * 5000)"])
        self.assertTrue(result.truncated)
        self.assertLessEqual(len(result.stdout.encode("utf-8")), 100)

    def test_no_shell_semantics(self) -> None:
        # ``;`` is an ordinary character inside an argv element. It cannot end
        # the command and start a second one.
        result = self.py("print('a;b')")
        self.assertEqual(result.stdout.strip(), "a;b")

    def test_partial_output_on_timeout(self) -> None:
        runner = CommandRunner(
            self.root,
            limits=Limits(timeout_seconds=0.5, max_output_bytes=10_000),
        )
        result = runner.run(
            "python",
            ["-c", "import time; print('before', flush=True); time.sleep(5)"],
        )
        self.assertTrue(result.timed_out)
        self.assertIn("before", result.stdout)

    def test_command_tool_observation(self) -> None:
        observation = run_command_tool(
            self.runner,
            {"argv": ["python", "-c", "print('hi')"]},
        )
        self.assertTrue(observation.startswith("OK\n"))
        self.assertIn("hi", observation)

    def test_command_tool_denied(self) -> None:
        observation = run_command_tool(self.runner, {"argv": ["sh", "-c", "echo x"]})
        self.assertTrue(observation.startswith("ERROR[DENIED]"))

    def test_command_tool_bad_argv(self) -> None:
        observation = run_command_tool(self.runner, {"argv": "python -c 'print(1)'"})
        self.assertTrue(observation.startswith("ERROR[ARGS]"))

    @unittest.skipIf(os.name == "nt", "POSIX resource limits only")
    def test_rlimit_is_applied(self) -> None:
        runner = CommandRunner(
            self.root,
            limits=Limits(timeout_seconds=3.0, cpu_seconds=2, max_output_bytes=1000),
        )
        result = runner.run(
            "python",
            ["-c", "import resource; print(resource.getrlimit(resource.RLIMIT_CPU)[0])"],
        )
        # The child may have a lower inherited hard limit; 2 is the requested
        # soft limit when the host allows it.
        self.assertIn(result.stdout.strip(), {"2", "1"})


if __name__ == "__main__":
    unittest.main()
