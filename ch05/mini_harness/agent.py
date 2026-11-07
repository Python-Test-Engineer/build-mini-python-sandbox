"""agent.py - the smallest useful ReAct loop around the sandbox.

A model is any object with ``reply(messages, tools) -> ModelReply``. The book
ships ``ScriptedModel`` so the demo and tests run offline, without an API key.
A real adapter would call an LLM and parse its tool-call format; the loop and
the sandbox boundary do not change.

The loop is intentionally boring:

1. ask the model for the next action;
2. if it is a final answer, stop;
3. otherwise run the tool, append the observation, and ask again;
4. stop after ``max_steps`` even if the model never finishes.

That last rule is the agent equivalent of a timeout. It belongs in the loop,
not in the model's good behaviour.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

from .audit import AuditLog
from .toolbox import Toolbox


# ---------------------------------------------------------------------------
# Model contract
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ModelReply:
    """One decision from a model: call a tool, or finish."""

    kind: str                       # "tool" or "final"
    text: str = ""                  # final answer text
    tool: str | None = None         # tool name for kind == "tool"
    args: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def final(cls, text: str) -> "ModelReply":
        """Build a final-answer reply."""
        return cls(kind="final", text=text)

    @classmethod
    def call(cls, tool: str, args: dict[str, Any] | None = None) -> "ModelReply":
        """Build a tool-call reply."""
        return cls(kind="tool", tool=tool, args=args or {})


class Model(Protocol):
    """The interface the agent needs from a model adapter."""

    def reply(self, messages: list[dict[str, Any]], tools: list[object]) -> ModelReply:
        """Return the next action given the transcript and tool contract."""


class ScriptedModel:
    """A deterministic model for demos and tests.

    Replies are consumed in order. When the script runs out, the model returns
    a final answer instead of hanging or inventing a tool call. That makes an
    offline demo reproducible and keeps tests from depending on a network.
    """

    def __init__(self, replies: list[ModelReply]) -> None:
        self._replies = list(replies)
        self.calls = 0

    def reply(self, messages: list[dict[str, Any]], tools: list[object]) -> ModelReply:
        """Return the next scripted reply, or a polite final answer."""
        self.calls += 1
        if self._replies:
            return self._replies.pop(0)
        return ModelReply.final("(scripted model has no more replies)")


# ---------------------------------------------------------------------------
# Results
# ---------------------------------------------------------------------------


@dataclass
class AgentResult:
    """The observable output of one agent run."""

    text: str
    steps: int
    stopped: str                    # "final" or "max_steps" or "error"
    transcript: list[dict[str, Any]]
    observations: list[dict[str, Any]]


# ---------------------------------------------------------------------------
# Agent
# ---------------------------------------------------------------------------


class Agent:
    """Run the model/tool loop against a sandboxed toolbox."""

    def __init__(
        self,
        toolbox: Toolbox,
        model: Model,
        audit: AuditLog,
        *,
        max_steps: int = 8,
    ) -> None:
        if max_steps <= 0:
            raise ValueError("max_steps must be positive")
        self.toolbox = toolbox
        self.model = model
        self.audit = audit
        self.max_steps = max_steps

    def run(self, task: str) -> AgentResult:
        """Execute one task and return the final text plus a full transcript."""
        transcript: list[dict[str, Any]] = [{"role": "user", "content": task}]
        observations: list[dict[str, Any]] = []

        self.audit.record("agent.start", "ok", {"task": task, "max_steps": self.max_steps})

        for step in range(1, self.max_steps + 1):
            try:
                reply = self.model.reply(transcript, self.toolbox.specs())
            except Exception as exc:  # noqa: BLE001 - a model adapter can fail
                text = f"agent stopped: model error: {type(exc).__name__}: {exc}"
                self.audit.record("agent.error", "error", {"step": step, "error": str(exc)})
                return AgentResult(
                    text=text,
                    steps=step,
                    stopped="error",
                    transcript=transcript,
                    observations=observations,
                )

            if reply.kind == "final":
                self.audit.record(
                    "agent.final",
                    "ok",
                    {"step": step, "text": reply.text},
                )
                transcript.append({"role": "assistant", "content": reply.text})
                return AgentResult(
                    text=reply.text,
                    steps=step,
                    stopped="final",
                    transcript=transcript,
                    observations=observations,
                )

            if reply.kind != "tool" or not reply.tool:
                text = f"agent stopped: invalid model reply kind={reply.kind!r}"
                self.audit.record("agent.error", "error", {"step": step, "error": text})
                return AgentResult(
                    text=text,
                    steps=step,
                    stopped="error",
                    transcript=transcript,
                    observations=observations,
                )

            # Record the request before running it. If the process dies during
            # the tool call, the audit still shows what was attempted.
            self.audit.record(
                "tool.call",
                "requested",
                {"step": step, "tool": reply.tool, "args": reply.args},
            )
            transcript.append(
                {
                    "role": "assistant",
                    "content": {
                        "type": "tool_call",
                        "tool": reply.tool,
                        "args": reply.args,
                    },
                }
            )

            observation = self.toolbox.run(reply.tool, reply.args)
            observations.append({"tool": reply.tool, "observation": observation})

            # The audit stores a clipped observation. The full text stays in
            # the transcript for the model; the log is a trail, not a copy.
            self.audit.record(
                "tool.result",
                "ok" if not observation.startswith("ERROR[") else "error",
                {"step": step, "tool": reply.tool, "observation": observation},
            )
            transcript.append(
                {
                    "role": "tool",
                    "name": reply.tool,
                    "content": observation,
                }
            )

        text = f"agent stopped after {self.max_steps} steps without a final answer"
        self.audit.record("agent.max_steps", "stopped", {"steps": self.max_steps})
        return AgentResult(
            text=text,
            steps=self.max_steps,
            stopped="max_steps",
            transcript=transcript,
            observations=observations,
        )
