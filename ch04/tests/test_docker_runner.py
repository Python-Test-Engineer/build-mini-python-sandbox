"""Tests for the Docker runner.

Run from ``ch04/``:

    python -m pytest -v

Most tests are offline: they inspect the ``docker run`` argv and never start a
container. The integration test skips when Docker is missing, the daemon is
stopped, or the image has not been built.

Why inspect the argv instead of always running containers?
----------------------------------------------------------
The generated command line *is* the security contract: network disabled, root
filesystem read-only, capabilities dropped, non-root user, one writable mount.
Asserting those flags directly is fast, deterministic, and works on machines
without Docker. A few integration tests then confirm the flags actually have
the intended effect when a daemon is available.
"""

from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from mini_harness.docker_runner import DockerConfig, DockerError, DockerRunner


class DockerCommandTests(unittest.TestCase):
    """The CLI recipe is the security contract; assert it directly."""

    def setUp(self) -> None:
        # A private workspace with a subdirectory for cwd-translation tests.
        self.temp = self.enterContext(tempfile.TemporaryDirectory(prefix="docker-test-"))
        self.root = Path(self.temp) / "workspace"
        self.root.mkdir()
        (self.root / "sub").mkdir()
        (self.root / "notes.txt").write_text("inside\n", encoding="utf-8")
        self.runner = DockerRunner(self.root)

    def command(self, argv=None, **kwargs):
        """Build a command with a stable name for easy assertions.

        A fixed container name avoids collisions in test output and makes the
        command easier to read when a test fails.
        """
        return self.runner.build_command(
            argv or ["python", "-c", "print(1)"],
            name="test-container",
            **kwargs,
        )

    # -- hardening flags ---------------------------------------------------

    def test_hardening_flags_are_present(self) -> None:
        """The essential isolation flags appear in the generated command.

        Each pair is a promise about the container:

        * ``--network none``: no network access,
        * ``--read-only``: an immutable root filesystem,
        * ``--cap-drop ALL``: remove Linux capabilities,
        * ``--security-opt no-new-privileges``: no setuid escalation,
        * ``--user 1000:1000``: run as a non-root user,
        * ``--workdir /workspace``: run from the mounted workspace.

        We compare adjacent ``(flag, value)`` pairs, which is more precise than
        searching for each string separately.
        """
        command = self.command()
        pairs = list(zip(command, command[1:]))
        required = [
            ("--network", "none"),
            ("--read-only", "--cap-drop"),
            ("--cap-drop", "ALL"),
            ("--security-opt", "no-new-privileges"),
            ("--user", "1000:1000"),
            ("--workdir", "/workspace"),
        ]
        for pair in required:
            self.assertIn(pair, pairs)

        # ``--init`` reaps orphaned child processes so one run cannot leave
        # zombies behind inside the container.
        for flag in ("--read-only", "--init"):
            self.assertIn(flag, command)

    def test_resource_limits(self) -> None:
        """CPU, memory, process and file-descriptor caps are set.

        These keep a runaway program from exhausting the host. The test checks
        the chosen values as well as the flags, so an accidental change to a
        looser default is caught.
        """
        command = self.command()
        self.assertIn("--pids-limit", command)
        self.assertIn("64", command)
        self.assertIn("--memory", command)
        self.assertIn("256m", command)
        self.assertIn("--memory-swap", command)
        self.assertIn("--cpus", command)
        self.assertIn("1.0", command)
        self.assertIn("nofile=64:64", command)

    def test_read_only_root_and_tmpfs(self) -> None:
        """The root is read-only, with writable tmpfs only where required.

        A read-only root is only practical if temporary locations still work.
        ``/tmp`` and ``/run`` are mounted as in-memory filesystems that vanish
        with the container.
        """
        command = self.command()
        self.assertIn("--read-only", command)

        tmpfs_values = [command[i + 1] for i, item in enumerate(command) if item == "--tmpfs"]
        self.assertTrue(any(value.startswith("/tmp:") for value in tmpfs_values))
        self.assertTrue(any(value.startswith("/run:") for value in tmpfs_values))

    def test_workspace_is_the_only_volume(self) -> None:
        """Exactly one host directory is mounted, at ``/workspace``.

        Limiting the mount surface is critical: every extra volume is another
        place the container can read or change host state.
        """
        command = self.command()
        volumes = [command[i + 1] for i, item in enumerate(command) if item == "--volume"]
        self.assertEqual(len(volumes), 1)
        self.assertIn(str(self.runner.root), volumes[0])
        self.assertTrue(volumes[0].endswith(":/workspace:rw"))

    def test_read_only_workspace_mode(self) -> None:
        """The workspace can be mounted read-only for inspection-only tasks.

        When ``workspace_mode="ro"``, the same single mount ends in ``:ro`` so
        the container cannot modify host files at all.
        """
        runner = DockerRunner(
            self.root,
            config=DockerConfig(workspace_mode="ro"),
        )
        command = runner.build_command(["python", "-c", "print(1)"], name="x")
        volumes = [command[i + 1] for i, item in enumerate(command) if item == "--volume"]
        self.assertTrue(volumes[0].endswith(":/workspace:ro"))

    # -- working directory -------------------------------------------------

    def test_cwd_is_translated_into_the_mount(self) -> None:
        """A workspace-relative ``cwd`` becomes a path inside ``/workspace``.

        The host path must never appear as the container's workdir; it only
        exists inside the mount.
        """
        command = self.command(cwd="sub")
        self.assertIn("/workspace/sub", command)

    def test_cwd_escape_rejected(self) -> None:
        """A ``cwd`` outside the workspace is refused with ``CWD``."""
        with self.assertRaises(DockerError) as exc:
            self.runner.build_command(["python", "-c", "print(1)"], cwd="../..")
        self.assertEqual(exc.exception.code, "CWD")

    # -- argv rules --------------------------------------------------------

    def test_argv_string_rejected(self) -> None:
        """A shell-style command string is refused with ``ARGS``.

        As in the local runner, argv must be a list so no layer re-parses it as
        a shell command.
        """
        with self.assertRaises(DockerError) as exc:
            self.runner.build_command("python -c 'print(1)'")  # type: ignore[arg-type]
        self.assertEqual(exc.exception.code, "ARGS")

    def test_empty_argv_rejected(self) -> None:
        """An empty argv has no program to run and is refused."""
        with self.assertRaises(DockerError) as exc:
            self.runner.build_command([])
        self.assertEqual(exc.exception.code, "ARGS")

    def test_nul_argument_rejected(self) -> None:
        """NUL bytes in an argument are refused with ``ARGS``."""
        with self.assertRaises(DockerError) as exc:
            self.runner.build_command(["python", "bad\x00arg"])
        self.assertEqual(exc.exception.code, "ARGS")

    # -- environment -------------------------------------------------------

    def test_environment_is_explicit(self) -> None:
        """Only explicitly passed variables reach the container.

        We set a host secret and confirm it is absent, while an explicit
        ``MY_FLAG`` is present. Containers inherit nothing unless told to.
        """
        os.environ["BOOK_HOST_SECRET"] = "must-not-appear"
        command = self.command(env={"MY_FLAG": "1"})
        self.assertIn("MY_FLAG=1", command)
        self.assertNotIn("BOOK_HOST_SECRET=must-not-appear", command)

    def test_bad_environment_name_rejected(self) -> None:
        """Environment names must look like shell identifiers (``ENV``)."""
        with self.assertRaises(DockerError) as exc:
            self.command(env={"BAD-NAME": "1"})
        self.assertEqual(exc.exception.code, "ENV")

    def test_environment_newline_rejected(self) -> None:
        """Newlines in environment values are refused.

        An embedded newline can break log parsing or smuggle extra lines into
        output. Values are single-line by policy.
        """
        with self.assertRaises(DockerError) as exc:
            self.command(env={"OK": "line\nbreak"})
        self.assertEqual(exc.exception.code, "ENV")

    # -- command shape -----------------------------------------------------

    def test_image_precedes_argv(self) -> None:
        """The image name comes immediately before the program and its argv.

        Docker treats everything after the image as the container's command, so
        this ordering check confirms the argv is not being read as options.
        """
        command = self.command(["python", "-c", "print(1)"])
        image_index = command.index(self.runner.config.image)
        self.assertEqual(command[image_index + 1], "python")
        self.assertEqual(command[image_index + 2], "-c")

    # -- configuration guards ---------------------------------------------

    def test_network_cannot_be_enabled(self) -> None:
        """Configuration cannot re-enable networking (fixed policy)."""
        with self.assertRaises(DockerError) as exc:
            DockerConfig(network="bridge").validate()
        self.assertEqual(exc.exception.code, "CONFIG")

    def test_root_filesystem_cannot_be_writable(self) -> None:
        """Configuration cannot make the root filesystem writable."""
        with self.assertRaises(DockerError) as exc:
            DockerConfig(read_only_root=False).validate()
        self.assertEqual(exc.exception.code, "CONFIG")

    def test_bad_user_rejected(self) -> None:
        """The container cannot be configured to run as ``root``."""
        with self.assertRaises(DockerError) as exc:
            DockerConfig(user="root").validate()
        self.assertEqual(exc.exception.code, "CONFIG")

    def test_check_available_returns_bool(self) -> None:
        """Docker availability detection must never raise.

        This test is intentionally weak: both outcomes are valid on a developer
        machine. What matters is that a missing CLI or stopped daemon produces
        ``False`` rather than an exception that crashes startup.
        """
        self.assertIsInstance(self.runner.check_available(), bool)


class DockerIntegrationTests(unittest.TestCase):
    """These tests need a real daemon and the built image."""

    def setUp(self) -> None:
        # Skip (not fail) when the optional runtime is unavailable. The skip
        # message tells the reader exactly how to enable the tests.
        self.temp = self.enterContext(tempfile.TemporaryDirectory(prefix="docker-int-"))
        self.root = Path(self.temp) / "workspace"
        self.root.mkdir()
        (self.root / "notes.txt").write_text("inside\n", encoding="utf-8")
        self.runner = DockerRunner(self.root)
        if not self.runner.check_available():
            self.skipTest("Docker daemon is not available")
        if not self.runner.image_exists():
            self.skipTest(
                "sandbox image is not built; run: "
                "docker build -t mini-harness-python:latest docker"
            )

    def test_runs_python(self) -> None:
        """A permitted program runs successfully inside the container.

        This is the smoke test: if it fails, the image or runtime is broken,
        not the security policy.
        """
        result = self.runner.run(["python", "-c", "print('container works')"])
        self.assertEqual(result.returncode, 0)
        self.assertIn("container works", result.stdout)

    def test_no_network(self) -> None:
        """Outbound connections fail because the container has no network.

        The program is expected to raise, so a non-zero exit is the success
        condition here.
        """
        result = self.runner.run(
            [
                "python",
                "-c",
                "import socket; socket.create_connection(('1.1.1.1', 80), timeout=2)",
            ]
        )
        self.assertNotEqual(result.returncode, 0)

    def test_root_is_read_only(self) -> None:
        """Writing to ``/etc/passwd`` fails because the root is read-only."""
        result = self.runner.run(
            ["python", "-c", "open('/etc/passwd', 'a').write('nope')"]
        )
        self.assertNotEqual(result.returncode, 0)

    def test_workspace_is_mounted(self) -> None:
        """The workspace is visible at the container's working directory.

        Reading ``notes.txt`` by its relative name proves both the mount and
        the ``--workdir`` setting are correct.
        """
        result = self.runner.run(["python", "-c", "print(open('notes.txt').read())"])
        self.assertEqual(result.returncode, 0)
        self.assertIn("inside", result.stdout)


if __name__ == "__main__":
    unittest.main()
