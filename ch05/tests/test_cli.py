"""End-to-end CLI test for the offline demo.

The demo must exit zero even when Docker is not installed: file tools still
work, and the command step is a visible ``ERROR[DOCKER_MISSING]`` observation.
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
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            code = main([])
        output = buffer.getvalue()

        self.assertEqual(code, 0)
        self.assertIn("TASK:", output)
        self.assertIn("FINAL:", output)
        self.assertIn("audit chain verifies: True", output)

    def test_demo_with_explicit_workspace_writes_and_audits(self) -> None:
        self.temp = self.enterContext(tempfile.TemporaryDirectory(prefix="cli-test-"))
        workspace = Path(self.temp) / "workspace"
        workspace.mkdir()

        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            code = main(["--workspace", str(workspace)])
        self.assertEqual(code, 0)

        # hello.py is written through the sandbox and remains after the run.
        self.assertTrue((workspace / "hello.py").exists())
        self.assertIn("hello from the sandboxed harness", (workspace / "hello.py").read_text(encoding="utf-8"))

        # The audit sits beside the workspace and verifies.
        audit = AuditLog(Path(self.temp) / "audit" / "events.jsonl")
        self.assertTrue(audit.verify())


if __name__ == "__main__":
    unittest.main()
