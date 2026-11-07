# Chapter 5 — Stage 5: The finished harness

> **Educational use only — not a production-ready system.** This chapter is part of an educational project to learn and understand. It deliberately simplifies design, error handling, security, and operations so the core idea stays visible. Do not deploy this code as-is.

**Book:** Stage 5, "The finished harness"
**Plan:** Stage 5
**Goal:** Wire the path policy, file sandbox, Docker runner and an append-only audit log into one small agent loop, then prove it end to end without an API key.

## The problem

At the end of Stage 4 we have two good boundaries and no product:

* file tools that enforce a path policy;
* a Docker runner that enforces a container contract.

What is missing is the thing that makes them an **agent**: a loop that chooses a
tool, sees the observation, and decides what to do next — plus a record of what
happened that an operator can inspect afterwards.

Stage 5 adds exactly three pieces:

1. a `Toolbox` that routes file and command tools through one interface;
2. an `Agent` loop with a hard step limit and an audit record for every action;
3. a `ScriptedModel` and CLI so the whole thing runs offline and in CI.

The absence of an LLM client is deliberate. The book is about the sandbox, not
about choosing a provider. A real adapter implements one method and everything
else stays the same.

## What changed

- Added `mini_harness/toolbox.py` — one dispatch point for all tools.
- Added `mini_harness/docker_tools.py` — the model-facing command tool.
- Added `mini_harness/audit.py` — append-only, hash-chained JSONL.
- Added `mini_harness/agent.py` — the ReAct loop and `ScriptedModel`.
- Added `mini_harness/cli.py` and `__main__.py` — the offline demo.
- Added `tests/test_toolbox.py`, `test_agent.py`, `test_audit.py` and
  `test_cli.py`.

## The toolbox

The toolbox is intentionally thin:

```python
if name == "run_command":
    return run_command_tool(self.runner, arguments)
if name in FILE_TOOL_NAMES:
    return file_tools.run_tool(self.sandbox, name, arguments)
return f"ERROR[UNKNOWN_TOOL]: no tool named {name!r}"
```

It adds no second policy. Each boundary owns its own decisions:

* the sandbox owns file paths, sizes and atomic writes;
* the Docker runner owns the container recipe;
* the toolbox only routes by name.

A new file tool appears in `FILE_TOOL_NAMES` automatically because the set is
derived from `file_tools.TOOL_SPECS`. A new command tool would add one branch
and one spec.

## The loop

```text
messages = [user task]
for step in 1..max_steps:
    reply = model(messages, tools)
    if reply is final: return
    observation = toolbox.run(reply.tool, reply.args)
    messages += [tool_call, observation]
return "stopped after max_steps"
```

Two details matter:

* **The step limit is in the loop, not the model.** A model can loop forever;
  the harness cannot.
* **A refusal is an observation, not an exception.** The model sees
  `ERROR[PATH]` or `ERROR[DOCKER_MISSING]` and can choose a different action.
  The loop continues.

`AgentResult` returns the final text, the step count, the stop reason, the full
transcript and a compact list of observations. A UI can render the transcript;
a test can assert on the observations.

## The audit log

`AuditLog` writes one JSON object per line:

```json
{"ts":"...","seq":1,"action":"tool.call","outcome":"requested",
 "detail":{"tool":"read_file","args":{"path":"hello.py"}},
 "prev":"0000...","hash":"..."}
```

Properties:

* **Append-only.** Opened with append mode and fsynced after each line.
* **Hash-chained.** `hash = sha256(prev + canonical_event)`. Editing or deleting
  a middle line breaks `verify()`.
* **Outside the workspace.** The file tools cannot edit their own trail through
  the sandbox. A local user with the same permissions still can; the chain makes
  tampering visible, not impossible.
* **Redacted.** Keys matching `key|token|secret|password|credential` are written
  as `***REDACTED***`; long values are truncated.

The audit records `agent.start`, `tool.call`, `tool.result`, `agent.final` and
`agent.max_steps`. The `tool.result` observation is clipped in the log but kept
in full in the transcript.

## The scripted demo

From `ch05/`:

```bash
python -m mini_harness
python -m mini_harness --build
python -m pytest -v
```

The demo:

1. writes `hello.py` through the file sandbox;
2. reads it back with numbered lines;
3. runs `python hello.py` in the container;
4. returns a final answer;
5. prints the audit verification result.

If Docker is missing, step 3 returns:

```text
ERROR[DOCKER_MISSING]: Docker CLI/daemon is not available
```

The loop still finishes. That is the desired behaviour: infrastructure absence
is a visible failed tool call, not a crash.

## End-to-end acceptance

Run these in order on a machine with Docker and the image built:

```bash
cd ch04 && python -m mini_harness.demo --build
cd ../ch05 && python -m mini_harness --build
python -m pytest -v
```

- [ ] `python -m mini_harness` exits 0 and prints `audit chain verifies: True`.
- [ ] `hello.py` is written and read back correctly.
- [ ] The `run_command` observation is `OK` with the container output.
- [ ] Stopping the Docker daemon produces `ERROR[DOCKER_MISSING]`, not a crash.
- [ ] Killing the daemon or making the image missing still leaves a verifiable
      audit log.
- [ ] The CLI's temporary workspace is cleaned up when the process exits.
- [ ] All chapter test suites pass; Docker integration tests skip cleanly on a
      machine without a daemon or image.

## Stage limits

This is a teaching harness, not a production service. It still lacks:

* a real LLM adapter, retries, token accounting and streaming;
* per-user policy, approval prompts and capability tokens;
* concurrency and a queue;
* log shipping, rotation and retention;
* a hardened host, a rootless Docker setup and network policy outside the
  container;
* an image update pipeline and vulnerability scanning.

Those are operations concerns. `../OPERATIONS.md` explains where they attach to
this code without changing the boundaries.

## If it goes wrong

- **`ModuleNotFoundError: mini_harness`** — run from the chapter directory:
  `cd ch05 && python -m mini_harness`. The package lives beside the chapter, not
  in a global environment.
- **`audit chain verifies: False`** — do not keep appending. Inspect
  `audit/events.jsonl`; a malformed or edited line breaks the chain. Restore a
  known-good copy and investigate.
- **The audit file already exists and fails verification** — `AuditLog` refuses
  to open a broken log. Move it aside deliberately; do not edit it to make the
  check pass.
- **The model gets stuck** — lower `--max-steps` and inspect the transcript. A
  tool returning `ERROR[...]` repeatedly is a prompt or tool-contract problem,
  not a sandbox problem.
- **The container command reports `ERROR[EXIT]` with a permission error** —
  check the workspace mount and `--user` mapping. The file tools may have
  written a file owned by the host user that the container uid cannot edit.
- **Audit logging slows the demo** — fsync on every event is deliberate. Batch
  or buffer only with a clear durability trade-off; do not silently drop the
  trail.

## Read next

- `../plan.md` Stage 5
- `../OPERATIONS.md` — the runbook
- `../THREAT_MODEL.md` — what remains after the container
- `../qa.html` — the architecture Q&A companion