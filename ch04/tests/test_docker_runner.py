"""Tests for the Docker runner.

Run from ``ch04/``:

    python -m pytest -v

Most tests are offline: they inspect the ``docker run`` argv and never start a
container. The integration test skips when Docker is missing, the daemon is
stopped, or the image has not been built.
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
        self.temp = self.enterContext(tempfile.TemporaryDirectory(prefix="docker-test-"))
        self.root = Path(self.temp) / "workspace"
        self.root.mkdir()
        (self.root / "sub").mkdir()
        (self.root / "notes.txt").write_text("inside\n", encoding="utf-8")
        self.runner = DockerRunner(self.root)

    def command(self, argv=None, **kwargs):
        """Build a command with a stable name for easy assertions."""
        return self.runner.build_command(
            argv or ["python", "-c", "print(1)"],
            name="test-container",
            **kwargs,
        )

    def test_hardening_flags_are_present(self) -> None:
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

        for flag in ("--read-only", "--init"):
            self.assertIn(flag, command)

    def test_resource_limits(self) -> None:
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
        command = self.command()
        self.assertIn("--read-only", command)
        tmpfs_values = [command[i + 1] for i, item in enumerate(command) if item == "--tmpfs"]
        self.assertTrue(any(value.startswith("/tmp:") for value in tmpfs_values))
        self.assertTrue(any(value.startswith("/run:") for value in tmpfs_values))

    def test_workspace_is_the_only_volume(self) -> None:
        command = self.command()
        volumes = [command[i + 1] for i, item in enumerate(command) if item == "--volume"]
        self.assertEqual(len(volumes), 1)
        self.assertIn(str(self.runner.root), volumes[0])
        self.assertTrue(volumes[0].endswith(":/workspace:rw"))

    def test_read_only_workspace_mode(self) -> None:
        runner = DockerRunner(
            self.root,
            config=DockerConfig(workspace_mode="ro"),
        )
        command = runner.build_command(["python", "-c", "print(1)"], name="x")
        volumes = [command[i + 1] for i, item in enumerate(command) if item == "--volume"]
        self.assertTrue(volumes[0].endswith(":/workspace:ro"))

    def test_cwd_is_translated_into_the_mount(self) -> None:
        command = self.command(cwd="sub")
        self.assertIn("/workspace/sub", command)

    def test_cwd_escape_rejected(self) -> None:
        with self.assertRaises(DockerError) as exc:
            self.runner.build_command(["python", "-c", "print(1)"], cwd="../..")
        self.assertEqual(exc.exception.code, "CWD")

    def test_argv_string_rejected(self) -> None:
        with self.assertRaises(DockerError) as exc:
            self.runner.build_command("python -c 'print(1)'")  # type: ignore[arg-type]
        self.assertEqual(exc.exception.code, "ARGS")

    def test_empty_argv_rejected(self) -> None:
        with self.assertRaises(DockerError) as exc:
            self.runner.build_command([])
        self.assertEqual(exc.exception.code, "ARGS")

    def test_nul_argument_rejected(self) -> None:
        with self.assertRaises(DockerError) as exc:
            self.runner.build_command(["python", "bad\x00arg"])
        self.assertEqual(exc.exception.code, "ARGS")

    def test_environment_is_explicit(self) -> None:
        os.environ["BOOK_HOST_SECRET"] = "must-not-appear"
        command = self.command(env={"MY_FLAG": "1"})
        self.assertIn("MY_FLAG=1", command)
        self.assertNotIn("BOOK_HOST_SECRET=must-not-appear", command)

    def test_bad_environment_name_rejected(self) -> None:
        with self.assertRaises(DockerError) as exc:
            self.command(env={"BAD-NAME": "1"})
        self.assertEqual(exc.exception.code, "ENV")

    def test_environment_newline_rejected(self) -> None:
        with self.assertRaises(DockerError) as exc:
            self.command(env={"OK": "line\nbreak"})
        self.assertEqual(exc.exception.code, "ENV")

    def test_image_precedes_argv(self) -> None:
        command = self.command(["python", "-c", "print(1)"])
        image_index = command.index(self.runner.config.image)
        self.assertEqual(command[image_index + 1], "python")
        self.assertEqual(command[image_index + 2], "-c")

    def test_network_cannot_be_enabled(self) -> None:
        with self.assertRaises(DockerError) as exc:
            DockerConfig(network="bridge").validate()
        self.assertEqual(exc.exception.code, "CONFIG")

    def test_root_filesystem_cannot_be_writable(self) -> None:
        with self.assertRaises(DockerError) as exc:
            DockerConfig(read_only_root=False).validate()
        self.assertEqual(exc.exception.code, "CONFIG")

    def test_bad_user_rejected(self) -> None:
        with self.assertRaises(DockerError) as exc:
            DockerConfig(user="root").validate()
        self.assertEqual(exc.exception.code, "CONFIG")

    def test_check_available_returns_bool(self) -> None:
        # This test is intentionally weak: both outcomes are valid on a
        # developer machine, but the method must not raise.
        self.assertIsInstance(self.runner.check_available(), bool)


class DockerIntegrationTests(unittest.TestCase):
    """These tests need a real daemon and the built image."""

    def setUp(self) -> None:
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
        result = self.runner.run(["python", "-c", "print('container works')"])
        self.assertEqual(result.returncode, 0)
        self.assertIn("container works", result.stdout)

    def test_no_network(self) -> None:
        result = self.runner.run(
            [
                "python",
                "-c",
                "import socket; socket.create_connection(('1.1.1.1', 80), timeout=2)",
            ]
        )
        self.assertNotEqual(result.returncode, 0)

    def test_root_is_read_only(self) -> None:
        result = self.runner.run(
            ["python", "-c", "open('/etc/passwd', 'a').write('nope')"]
        )
        self.assertNotEqual(result.returncode, 0)

    def test_workspace_is_mounted(self) -> None:
        result = self.runner.run(["python", "-c", "print(open('notes.txt').read())"])
        self.assertEqual(result.returncode, 0)
        self.assertIn("inside", result.stdout)


if __name__ == "__main__":
    unittest.main()
