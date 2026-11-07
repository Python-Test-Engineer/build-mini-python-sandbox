# Plan — the stage contract

> **Educational use only — not a production-ready system.** This plan describes an educational project to learn and understand, not a production architecture. It is deliberately simplified. Do not deploy it as-is. The goal is to make each layer visible, runnable, and easy to reason about.

This is the build contract for **Build a Mini Python Sandbox**. Each stage is a
standalone chapter directory with runnable code and tests. A stage is done when
its acceptance checks pass and its known limits are written down.

The plan is deliberately narrower than “build a secure agent platform”. The
subject is the boundary between a model's tool call and the operating system.

## Global rules

1. Python 3.11+ for runtime code; pytest is the test runner. Docker is
   optional for the offline tests and required for the integration tests in
   Stages 4–5.
2. Every chapter runs from its own directory with `python -m pytest -v`.
3. No network, no API key and no third-party runtime dependency in any test;
   pytest is the only test dependency.
4. A refusal is a stable observation string, never an uncaught exception.
5. Never weaken a test to make a demo pass. If a boundary cannot be tested on a
   platform, skip with a reason.
6. Stage 0 is intentionally unsafe and must remain clearly labelled.

## Stage 0 — The naive fence

**Goal:** Show the failure modes before fixing them.

| Item | Contract |
|---|---|
| New code | `mini_harness/unsafe.py`, `mini_harness/demo.py` |
| Tests | `tests/test_unsafe.py` |
| Must show | prefix-sibling escape; symlink escape where supported; shell call with inherited env and no timeout |
| Must not do | touch a real home directory; run a destructive command |
| Limits | not a sandbox; keep out of later stages |

**Done when:** the demo exits 0, the tests pass, and the escape outcomes are
asserted rather than hidden.

## Stage 1 — One path policy

**Goal:** Replace the string fence with canonical path resolution.

| Item | Contract |
|---|---|
| New code | `mini_harness/path_policy.py`, `demo.py` |
| Public API | `PathPolicy(root)`, `resolve_read`, `resolve_write`, `is_inside`, `relative`; `PolicyError`; `ResolvedPath` |
| Tests | `tests/test_path_policy.py` |
| Must handle | `..`, symlinks, symlinked parents, absolute reads, relative-only writes, UNC, drive-relative, reserved names, control chars, `~`/env expansion |
| Limits | no OS boundary; TOCTOU remains |

**Done when:** traversal and prefix-sibling escapes are refused, inside reads
and writes still work, and platform-specific tests skip with a reason.

## Stage 2 — The sandbox and file tools

**Goal:** Make the policy usable by bounded tools.

| Item | Contract |
|---|---|
| New code | `mini_harness/sandbox.py`, `mini_harness/file_tools.py`, `demo.py` |
| Public API | `Sandbox`, `Limits`, `SandboxError`, `DirEntry`; `run_tool`, `TOOL_SPECS` |
| Tools | `list_files`, `read_file`, `write_file`, `edit_file`, `delete_file` |
| Tests | `tests/test_sandbox.py` |
| Must enforce | read/write byte caps, directory-entry cap, atomic writes, create-only option, unique edit default, file-only delete |
| Must return | `OK: ...` or `ERROR[CODE]: ...` |

**Done when:** normal file work succeeds, every refusal is an observation, and
no temporary writer files remain after a failure.

## Stage 3 — Running code locally

**Goal:** Replace `shell=True` with an argv runner and visible limits.

| Item | Contract |
|---|---|
| New code | `mini_harness/local_runner.py`, `mini_harness/command_tool.py`, `demo.py` |
| Public API | `CommandRunner`, `CommandPolicy`, `Limits`, `CommandResult`, `CommandError`, `default_command_policy` |
| Tools | `run_command` with `argv` and optional `cwd` |
| Tests | `tests/test_local_runner.py` |
| Must enforce | list argv only, absolute-path allowlist, clean env, workspace cwd, timeout, process-tree kill, output caps, POSIX rlimits |
| Must demonstrate | the child can still read outside the workspace |

**Done when:** a normal command works, every refusal is visible, a sleeping
child is killed, output is capped, and the local runner’s residual filesystem
access is documented.

## Stage 4 — Docker as the real wall

**Goal:** Move command execution into a hardened container.

| Item | Contract |
|---|---|
| New code | `docker/Dockerfile`, `mini_harness/docker_runner.py`, `demo.py` |
| Public API | `DockerRunner`, `DockerConfig`, `RunResult`, `DockerError` |
| Tests | `tests/test_docker_runner.py` |
| Offline tests | assert the full `docker run` argv and configuration refusals |
| Integration tests | run Python, fail network access, fail root writes, see the workspace |
| Must enforce | `--network none`, `--read-only`, `--cap-drop ALL`, `no-new-privileges`, pids/memory/cpu/nofile limits, non-root user, single workspace mount, tmpfs scratch |
| Must clean up | remove the named container on timeout |

**Done when:** the offline tests pass without Docker; with Docker and the image,
the integration checks pass and all four boundary behaviours are observed.

## Stage 5 — The finished harness

**Goal:** Route tools, run the loop and record the trail.

| Item | Contract |
|---|---|
| New code | `toolbox.py`, `docker_tools.py`, `audit.py`, `agent.py`, `cli.py`, `__main__.py` |
| Public API | `Toolbox`, `run_command_tool`; `AuditLog`; `Agent`, `ModelReply`, `ScriptedModel`, `AgentResult` |
| Tests | `test_toolbox.py`, `test_agent.py`, `test_audit.py`, `test_cli.py` |
| Must enforce | one dispatch point, hard `max_steps`, observations not exceptions, hash-chained audit outside the workspace, secret redaction |
| Demo | write, read, container run, final answer, audit verification |

**Done when:**

- `python -m mini_harness` exits 0 and prints `audit chain verifies: True`;
- Docker absence produces `ERROR[DOCKER_MISSING]` and the loop still ends;
- tampering with the audit file makes `verify()` return False;
- all chapter suites pass, with Docker integration tests skipping cleanly.

## Stage boundaries and non-goals

| Not in this book | Where it belongs |
|---|---|
| LLM provider adapter, retries, streaming | Application layer |
| Per-user approval prompts, capability tokens | Policy/UX layer |
| Multi-tenant quotas and scheduling | Service layer |
| Rootless Docker, host hardening, network policy | Platform/operations |
| Image scanning and patch pipeline | Supply chain/operations |
| OS-level syscall filtering beyond Docker defaults | Platform security |

## Definition of done for the whole book

1. A reader can run each chapter from a clean checkout with only Python 3.11+.
2. Every security claim in a chapter is exercised by a test or a demo.
3. Every known limit is written down in the chapter and in `THREAT_MODEL.md`.
4. The final harness demonstrates the full path from a model decision to a
   sandboxed action and an auditable record.
5. Docker integration remains optional for reading and mandatory for the final
   acceptance run.