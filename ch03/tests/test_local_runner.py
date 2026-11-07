"""Tests for the local command runner.

Run from ``ch03``:

    python -m pytest -v

The tests use the running Python interpreter as the only program on the
allowlist. They do not need a network or a shell. pytest is the runner.

What is being protected
-----------------------
The runner turns two model-supplied values - a program name and an argv list -
into a child process. The tests check that:

* the program must appear on a fixed allowlist (no absolute paths, no shell),
* argv is a list of strings, never a command string,
* the working directory stays inside the workspace,
* the child environment is scrubbed, not inherited,
* output and runtime are bounded,
* every failure becomes a stable ``CommandError`` code or a returned result.

These are the threats that a container later contains at the kernel level;
here they are policy checks in Python.
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
        # A private workspace and a parent-relative "outside" target.
        self.temp = self.enterContext(tempfile.TemporaryDirectory(prefix="runner-test-"))
        self.root = Path(self.temp) / "workspace"
        self.root.mkdir()
        (self.root / "sub").mkdir()
        (self.root / "data.txt").write_text("inside\n", encoding="utf-8")

        self.outside = Path(self.temp) / "outside.txt"
        self.outside.write_text("outside\n", encoding="utf-8")

        # Short limits keep the timeout tests fast.
        self.runner = CommandRunner(
            self.root,
            limits=Limits(timeout_seconds=3.0, max_output_bytes=10_000),
        )

    def py(self, code: str, *, cwd: str = ".", **kwargs) -> object:
        """Shorthand for running a small Python program.

        Using the interpreter as the program keeps the tests portable: no
        shell, no external tools, and the same behaviour on Windows and POSIX.
        """
        return self.runner.run("python", ["-c", code], cwd=cwd, **kwargs)

    # -- normal execution --------------------------------------------------

    def test_normal_command(self) -> None:
        """A permitted program runs and its stdout/exit status are captured.

        ``ok`` is convenience for ``returncode == 0``; the result also carries
        the argv and duration for the audit trail.
        """
        result = self.py("print('hello')")
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout, "hello\n")
        self.assertTrue(result.ok)

    def test_stderr_is_captured(self) -> None:
        """stderr is collected separately, not merged into stdout.

        Keeping the streams apart lets the tool layer show the model both the
        program's output and its error text without guessing.
        """
        result = self.py("import sys; print('bad', file=sys.stderr)")
        self.assertEqual(result.stderr, "bad\n")

    def test_nonzero_exit(self) -> None:
        """A non-zero exit is a result, not a runner exception.

        The command ran successfully from the runner's point of view; the
        program simply failed. The tool layer turns this into ``ERROR[EXIT]``.
        """
        result = self.py("raise SystemExit(3)")
        self.assertEqual(result.returncode, 3)
        self.assertFalse(result.ok)

    # -- argument rules ----------------------------------------------------

    def test_args_must_be_a_list(self) -> None:
        """A single command string is rejected with ``ARGS``.

        A plain string invites shell-style parsing, where spaces, quotes and
        semicolons change meaning. Requiring a list makes every element a
        literal argument.
        """
        with self.assertRaises(CommandError) as exc:
            self.runner.run("python", "print('hi')")  # type: ignore[arg-type]
        self.assertEqual(exc.exception.code, "ARGS")

    def test_program_not_allowed(self) -> None:
        """Programs outside the allowlist are refused with ``DENIED``.

        The allowlist is the first line of defence: a model cannot simply ask
        for an arbitrary binary.
        """
        with self.assertRaises(CommandError) as exc:
            self.runner.run("definitely-not-allowed", [])
        self.assertEqual(exc.exception.code, "DENIED")

    def test_absolute_program_not_allowed(self) -> None:
        """Absolute program paths are denied even if they are on the allowlist.

        The allowlist matches names (e.g. ``python``), not arbitrary filesystem
        locations. Accepting ``C:\\...\\python.exe`` would let a workspace drop
        an executable and run it by path.
        """
        with self.assertRaises(CommandError) as exc:
            self.runner.run(sys.executable, ["-c", "print(1)"])
        self.assertEqual(exc.exception.code, "DENIED")

    def test_nul_argument_rejected(self) -> None:
        """NUL bytes inside an argument are refused with ``ARGS``.

        The OS cannot represent an embedded NUL in argv, and different layers
        may truncate it differently. Rejecting it avoids ambiguity.
        """
        with self.assertRaises(CommandError) as exc:
            self.py("print('x')\x00")
        self.assertEqual(exc.exception.code, "ARGS")

    # -- working directory -------------------------------------------------

    def test_cwd_escape_rejected(self) -> None:
        """``cwd`` is contained inside the workspace (``CWD`` refusal).

        Without this check, a command could run from a directory outside the
        workspace and read or write files relative to it.
        """
        with self.assertRaises(CommandError) as exc:
            self.py("print(1)", cwd="../..")
        self.assertEqual(exc.exception.code, "CWD")

    def test_cwd_subdirectory(self) -> None:
        """A real subdirectory of the workspace is an allowed ``cwd``.

        The child's actual working directory is checked, proving the runner
        passes ``cwd`` through rather than ignoring it.
        """
        result = self.py("import os; print(os.path.basename(os.getcwd()))", cwd="sub")
        self.assertEqual(result.stdout.strip(), "sub")

    # -- environment -------------------------------------------------------

    def test_environment_is_scrubbed(self) -> None:
        """Parent environment variables do not leak into the child.

        We set a secret in the test process, then ask the child to print it. The
        expected ``MISSING`` proves the runner builds a minimal environment
        instead of inheriting the host's (which may hold API keys).
        """
        os.environ["BOOK_TEST_SECRET"] = "leak-me-if-you-can"
        result = self.py("import os; print(os.environ.get('BOOK_TEST_SECRET', 'MISSING'))")
        self.assertEqual(result.stdout.strip(), "MISSING")

    # -- resource limits ---------------------------------------------------

    def test_timeout(self) -> None:
        """A long-running program is killed and marked ``timed_out``.

        The duration check proves the runner did not simply wait for the full
        sleep. The timeout is a real bound, not just a flag.
        """
        runner = CommandRunner(
            self.root,
            limits=Limits(timeout_seconds=0.4, max_output_bytes=10_000),
        )
        result = runner.run("python", ["-c", "import time; time.sleep(5)"])
        self.assertTrue(result.timed_out)
        self.assertLess(result.duration_seconds, 4.0)

    def test_output_cap(self) -> None:
        """Output is truncated at the configured byte limit.

        When the child writes far more than the cap, the returned stdout must
        stay within the limit and be flagged ``truncated`` so the model knows
        it is not seeing everything.
        """
        runner = CommandRunner(
            self.root,
            limits=Limits(timeout_seconds=3.0, max_output_bytes=100),
        )
        result = runner.run("python", ["-c", "print('x' * 5000)"])
        self.assertTrue(result.truncated)
        self.assertLessEqual(len(result.stdout.encode("utf-8")), 100)

    def test_no_shell_semantics(self) -> None:
        """Shell metacharacters are ordinary characters inside argv.

        ``;`` cannot end the command and start a second one, because there is no
        shell in the pipeline. The entire string is passed to Python as data.
        """
        result = self.py("print('a;b')")
        self.assertEqual(result.stdout.strip(), "a;b")

    def test_partial_output_on_timeout(self) -> None:
        """Output produced before a timeout is preserved.

        Partial output is often the most useful debugging signal. The runner
        captures what arrived before killing the process, rather than throwing
        it away.
        """
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

    # -- tool adapter ------------------------------------------------------

    def test_command_tool_observation(self) -> None:
        """A successful run becomes an ``OK`` observation for the model."""
        observation = run_command_tool(
            self.runner,
            {"argv": ["python", "-c", "print('hi')"]},
        )
        self.assertTrue(observation.startswith("OK\n"))
        self.assertIn("hi", observation)

    def test_command_tool_denied(self) -> None:
        """A denied program becomes ``ERROR[DENIED]`` instead of raising.

        This is the same "errors are observations" rule as the file tools.
        """
        observation = run_command_tool(self.runner, {"argv": ["sh", "-c", "echo x"]})
        self.assertTrue(observation.startswith("ERROR[DENIED]"))

    def test_command_tool_bad_argv(self) -> None:
        """A string argv from the model is refused with ``ERROR[ARGS]``.

        Models frequently try to send a shell-style command string. The tool
        must explain the required shape without crashing.
        """
        observation = run_command_tool(self.runner, {"argv": "python -c 'print(1)'"})
        self.assertTrue(observation.startswith("ERROR[ARGS]"))

    # -- platform-specific ------------------------------------------------

    @unittest.skipIf(os.name == "nt", "POSIX resource limits only")
    def test_rlimit_is_applied(self) -> None:
        """A CPU rlimit is applied to the child on POSIX systems.

        The child prints its own ``RLIMIT_CPU``. The requested soft limit is 2,
        but an inherited lower hard limit can force 1, so either is accepted.
        On Windows there is no ``resource`` module, hence the skip.
        """
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
