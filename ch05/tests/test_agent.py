"""Tests for the offline ReAct loop and its audit trail.

The agent loop is tested without a model server and without Docker:

* ``ScriptedModel`` returns a fixed list of replies, so each test controls the
  exact conversation.
* ``FakeRunner`` always raises, so a ``run_command`` call becomes a clean
  ``ERROR[DOCKER_MISSING]`` observation instead of starting a container.

That makes the loop itself - stopping conditions, error handling, audit
recording - deterministic and fast to test.
"""

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
        # Import here so the test module does not require Docker at import time.
        from mini_harness.docker_runner import DockerError

        raise DockerError("DOCKER_MISSING", "fake runner is offline")


class AgentTests(unittest.TestCase):
    """Each test uses a fresh workspace, toolbox and audit log."""

    def setUp(self) -> None:
        # Everything the agent touches lives under one temporary directory.
        self.temp = self.enterContext(tempfile.TemporaryDirectory(prefix="agent-test-"))
        base = Path(self.temp)

        self.root = base / "workspace"
        self.root.mkdir()
        self.sandbox = Sandbox(self.root)
        self.toolbox = Toolbox(self.sandbox, FakeRunner())  # type: ignore[arg-type]
        self.audit = AuditLog(base / "audit" / "events.jsonl")

    def test_write_read_final(self) -> None:
        """A normal three-step conversation runs tools and then answers.

        The scripted model asks to write a file, read it back, and then gives a
        final answer. We check:

        * the loop stops for the right reason (``final``),
        * the step count matches the model calls,
        * the read observation contains the written data,
        * the file really exists, and
        * the audit chain still verifies.
        """
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
        """The loop stops at ``max_steps`` instead of running forever.

        The scripted model never gives a final answer. With ``max_steps=2`` the
        agent must stop after two tool calls and synthesise a text result that
        explains why there is no final answer. The fourth scripted reply is
        never reached.
        """
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
        """A malformed model reply stops the loop as ``error``.

        Free-form models sometimes return something other than a tool call or a
        final answer. The loop must reject it with a readable message rather
        than raising an exception.
        """
        model = ScriptedModel([ModelReply(kind="nonsense")])
        result = Agent(self.toolbox, model, self.audit).run("bad reply")
        self.assertEqual(result.stopped, "error")
        self.assertIn("invalid model reply", result.text)

    def test_tool_refusal_is_recorded_and_loop_continues(self) -> None:
        """A policy refusal is shown to the model; the loop keeps going.

        The model tries to read outside the workspace. The sandbox refuses, the
        observation starts with ``ERROR[PATH]``, and the model then gives a
        final answer. This proves safety errors are part of the conversation,
        not fatal to it.
        """
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
        """A missing Docker runtime is a tool observation, not a crash.

        ``FakeRunner`` raises ``DockerError``. The toolbox converts it into
        ``ERROR[DOCKER_MISSING]`` so the agent can explain the situation and
        finish normally.
        """
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
        """Every meaningful loop event is written to the audit log.

        We look for the start marker, the tool request and result, and the final
        marker. Those events are what an operator needs to reconstruct a run.
        """
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
        """An empty script ends safely with a "no more replies" message.

        Real models can also return nothing. The agent must not index past the
        end of the reply list or hang; it should stop as ``final`` with a clear
        explanation.
        """
        model = ScriptedModel([])
        result = Agent(self.toolbox, model, self.audit).run("nothing scripted")
        self.assertEqual(result.stopped, "final")
        self.assertIn("no more replies", result.text)


if __name__ == "__main__":
    unittest.main()
