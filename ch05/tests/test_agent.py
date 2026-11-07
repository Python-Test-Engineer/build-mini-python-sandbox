"""Tests for the offline ReAct loop and its audit trail."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from mini_harness.agent import Agent, ModelReply, ScriptedModel
from mini_harness.audit import AuditLog
from mini_harness.sandbox import Sandbox
from mini_harness.toolbox import Toolbox


class FakeRunner:
    """A runner that fails cleanly, so the loop tests need no Docker."""

    def run(self, argv, *, cwd="."):
        from mini_harness.docker_runner import DockerError

        raise DockerError("DOCKER_MISSING", "fake runner is offline")


class AgentTests(unittest.TestCase):
    """Each test uses a fresh workspace, toolbox and audit log."""

    def setUp(self) -> None:
        self.temp = self.enterContext(tempfile.TemporaryDirectory(prefix="agent-test-"))
        base = Path(self.temp)
        self.root = base / "workspace"
        self.root.mkdir()
        self.sandbox = Sandbox(self.root)
        self.toolbox = Toolbox(self.sandbox, FakeRunner())  # type: ignore[arg-type]
        self.audit = AuditLog(base / "audit" / "events.jsonl")

    def test_write_read_final(self) -> None:
        model = ScriptedModel(
            [
                ModelReply.call("write_file", {"path": "a.txt", "content": "hello"}),
                ModelReply.call("read_file", {"path": "a.txt"}),
                ModelReply.final("done"),
            ]
        )
        result = Agent(self.toolbox, model, self.audit).run("make a file")

        self.assertEqual(result.text, "done")
        self.assertEqual(result.steps, 3)
        self.assertEqual(result.stopped, "final")
        self.assertEqual(len(result.observations), 2)
        self.assertIn("hello", result.observations[1]["observation"])
        self.assertTrue((self.root / "a.txt").exists())
        self.assertTrue(self.audit.verify())

    def test_max_steps_stops_the_loop(self) -> None:
        model = ScriptedModel(
            [
                ModelReply.call("list_files", {"path": "."}),
                ModelReply.call("list_files", {"path": "."}),
                ModelReply.call("list_files", {"path": "."}),
                ModelReply.final("never reached"),
            ]
        )
        result = Agent(self.toolbox, model, self.audit, max_steps=2).run("loop")

        self.assertEqual(result.stopped, "max_steps")
        self.assertEqual(result.steps, 2)
        self.assertIn("without a final answer", result.text)

    def test_invalid_reply_is_an_error_not_a_crash(self) -> None:
        model = ScriptedModel([ModelReply(kind="nonsense")])
        result = Agent(self.toolbox, model, self.audit).run("bad reply")
        self.assertEqual(result.stopped, "error")
        self.assertIn("invalid model reply", result.text)

    def test_tool_refusal_is_recorded_and_loop_continues(self) -> None:
        model = ScriptedModel(
            [
                ModelReply.call("read_file", {"path": "../outside.txt"}),
                ModelReply.final("handled the refusal"),
            ]
        )
        result = Agent(self.toolbox, model, self.audit).run("try an escape")
        self.assertEqual(result.text, "handled the refusal")
        self.assertTrue(result.observations[0]["observation"].startswith("ERROR[PATH]"))
        self.assertTrue(self.audit.verify())

    def test_docker_missing_is_an_observation(self) -> None:
        model = ScriptedModel(
            [
                ModelReply.call("run_command", {"argv": ["python", "x.py"]}),
                ModelReply.final("docker was unavailable"),
            ]
        )
        result = Agent(self.toolbox, model, self.audit).run("run something")
        self.assertIn("ERROR[DOCKER_MISSING]", result.observations[0]["observation"])
        self.assertEqual(result.stopped, "final")

    def test_audit_records_the_loop(self) -> None:
        model = ScriptedModel(
            [
                ModelReply.call("write_file", {"path": "a.txt", "content": "x"}),
                ModelReply.final("done"),
            ]
        )
        Agent(self.toolbox, model, self.audit).run("task")

        actions = [event["action"] for event in self.audit.events()]
        self.assertIn("agent.start", actions)
        self.assertIn("tool.call", actions)
        self.assertIn("tool.result", actions)
        self.assertIn("agent.final", actions)

    def test_scripted_model_run_out_is_safe(self) -> None:
        model = ScriptedModel([])
        result = Agent(self.toolbox, model, self.audit).run("nothing scripted")
        self.assertEqual(result.stopped, "final")
        self.assertIn("no more replies", result.text)


if __name__ == "__main__":
    unittest.main()
