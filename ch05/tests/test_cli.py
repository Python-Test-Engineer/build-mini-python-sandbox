"""End-to-end CLI test for the offline demo.

The demo must exit zero even when Docker is not installed: file tools still
work, and the command step is a visible ``ERROR[DOCKER_MISSING]`` observation.

These tests run the CLI *in-process* (calling ``main`` directly) with stdout
redirected into a buffer. That lets us assert on the user-visible transcript
without spawning a subprocess, while still exercising the real command-line
entry point and its argument handling.
"""

from __future__ import annotations

import contextlib
import io
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from mini_harness.audit import AuditLog
from mini_harness.cli import main


class CliTests(unittest.TestCase):
    """Run the CLI in-process and inspect its effects."""

    def test_demo_with_temporary_workspace(self) -> None:
        """Running with no arguments uses a temporary workspace and exits 0.

        The demo is intentionally usable out of the box. We capture the
        transcript and check the three landmarks a reader should see: the task,
        the final answer, and a verifying audit chain. This also proves the
        demo does not fail just because Docker is absent.
        """
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            code = main([])
        output = buffer.getvalue()

        self.assertEqual(code, 0)
        self.assertIn("TASK:", output)
        self.assertIn("FINAL:", output)
        self.assertIn("audit chain verifies: True", output)

    def test_demo_with_explicit_workspace_writes_and_audits(self) -> None:
        """An explicit ``--workspace`` makes the demo's effects inspectable.

        We pass a temporary workspace, then verify two real side effects:

        1. ``hello.py`` was written through the sandbox and contains the
           expected program text.
        2. The audit log beside the workspace exists and its hash chain
           verifies.

        This is the closest thing to an end-to-end test without a container.
        """
        self.temp = self.enterContext(tempfile.TemporaryDirectory(prefix="cli-test-"))
        workspace = Path(self.temp) / "workspace"
        workspace.mkdir()

        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            code = main(["--workspace", str(workspace)])
        self.assertEqual(code, 0)

        # hello.py is written through the sandbox and remains after the run.
        self.assertTrue((workspace / "hello.py").exists())
        self.assertIn(
            "hello from the sandboxed harness",
            (workspace / "hello.py").read_text(encoding="utf-8"),
        )

        # The audit sits beside the workspace and verifies.
        audit = AuditLog(Path(self.temp) / "audit" / "events.jsonl")
        self.assertTrue(audit.verify())


if __name__ == "__main__":
    unittest.main()
