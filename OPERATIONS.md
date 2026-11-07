# Operations runbook

This is the operator-facing companion to the chapters. It assumes you have read
`THREAT_MODEL.md` and understand that the **container is the boundary**; the
Python path policy is accident prevention and usability, not a jail.

## 1. Prerequisites

| Component | Minimum | Notes |
|---|---|---|
| Python | 3.11 | `TestCase`-style tests; pytest collects them; `enterContext` needs 3.11 |
| Docker | Engine 24+ or Docker Desktop | Linux containers |
| OS | Windows, macOS or Linux | Symlink and rlimit tests vary by platform |
| Disk | ~1 GB for the Python base image | More if you add tools |

No API key or network access is needed for the offline suites. Install pytest
and Rich (`python -m pip install pytest rich`). The sandbox core is standard
library only; Rich is used by the demo layer for panels and colour.

## 2. Install and verify

```bash
# from the repository root
for chapter in ch00 ch01 ch02 ch03 ch04 ch05; do
  echo "== $chapter =="
  (cd "$chapter" && python -m pytest -v)
done
```

Expected: all tests pass; symlink, rlimit and Docker integration tests skip with
a reason on platforms that cannot run them.

Build the image:

```bash
cd ch04
docker build -t mini-harness-python:latest docker
```

For production, build with a pinned digest and a unique tag:

```bash
docker build \
  --build-arg PYTHON_BASE=python:3.12-slim-bookworm@sha256:<digest> \
  -t registry.example.com/mini-harness-python:2026-11-07 \
  docker
```

The book's Dockerfile uses a readable `FROM` line. A real pipeline should
template the digest and record it in the release metadata.

## 3. Configuration

The defaults live in `DockerConfig` (`ch04`/`ch05`) and `Limits` (`ch02`/`ch03`).
Treat them as policy, not constants to tweak casually.

| Knob | Default | Raise when | Lower when |
|---|---|---|---|
| `timeout_seconds` | 20 | legitimate builds/tests need longer | interactive tasks should fail fast |
| `memory` | `256m` | the toolchain needs more | untrusted workloads |
| `cpus` | `1.0` | parallel test suites | shared hosts |
| `pids_limit` | 64 | test runners spawn workers | fork-bomb exposure |
| `nofile_limit` | 64 | large test suites | strict workloads |
| `max_output_bytes` | 200 000 | logs need more | context/memory pressure |
| `max_read_bytes` | 2 MiB | large source files | small-model context |
| `max_write_bytes` | 1 MiB | generated files | accidental overwrite risk |
| `max_dir_entries` | 500 | monorepos | huge directories |
| `workspace_mode` | `rw` | editing tasks | read-only analysis |
| `max_steps` | 8 | complex tasks | cost/abuse control |

Change one knob at a time and add or update a test that states the new
behaviour. A limit that is not tested is a comment.

## 4. Docker daemon security

The daemon is more powerful than any container it starts. Protect it.

* Run Docker rootless where possible; otherwise restrict access to the
  `docker` group and treat that group as root-equivalent.
* Never mount `/var/run/docker.sock` into the sandbox. A container with the
  socket can start a privileged container and own the host.
* Keep the daemon bound to a local socket; do not expose TCP without TLS and
  authentication.
* Enable user namespace remapping if your platform supports it.
* Apply host firewall policy outside the container. `--network none` is the
  container control; it does not configure the host.
* Keep the kernel and Docker patched. Container escapes often start with a
  kernel or runtime vulnerability.
* Do not add `--privileged`, `--device`, host PID/IPC namespaces, or extra
  capabilities to make a tool “just work”. Add the smallest explicit exception
  you can and document it.

## 5. Image lifecycle

1. **Build** in CI from a reviewed Dockerfile.
2. **Pin** the base image by digest; tag the result with a date and commit.
3. **Scan** the image (Trivy, Grype, Docker Scout, or your registry scanner).
4. **Test** the recipe tests and the integration suite.
5. **Publish** to a private registry with immutable tags.
6. **Deploy** the exact digest; do not let a host pull `latest` at run time.
7. **Rebuild** on base-image security updates, not only when application code
   changes.
8. **Retire** old digests and keep the previous known-good digest for rollback.

`DockerRunner.build()` is an explicit operator action. Do not expose it as a
model tool.

## 6. Audit lifecycle

The audit file is append-only JSONL written beside the workspace:

```text
<workspace parent>/audit/events.jsonl
```

Operational rules:

* **Protect the directory.** The harness user needs append; other users should
  not have write access. The audit is outside the sandbox but not outside the
  host.
* **Ship it off-host.** Use a log agent with read-only access. Do not let the
  agent process rewrite or truncate the file.
* **Rotate by segment, not by editing.** Stop the process, move the file, start
  a new one. The chain restarts at sequence 1 for the new file; keep the
  segment boundary in the shipper.
* **Verify on ingest.** Recompute the chain in the log store; alert on a gap.
* **Retention.** Decide how long task transcripts and audit events are kept.
  They may contain source code and user data even after redaction.
* **Redaction is not classification.** `api_key`, `token`, `secret`,
  `password` and `credential` keys are masked, but arbitrary content can still
  contain sensitive data. Treat logs accordingly.

### Audit verification

```bash
cd ch05
python - <<'PY'
from pathlib import Path
from mini_harness.audit import AuditLog
log = AuditLog(Path("audit/events.jsonl"))
print("events:", len(log.events()))
print("chain:", log.verify())
PY
```

`AuditLog` refuses to open a log that is already broken. That is intentional:
do not “fix” the file to make the check pass.

## 7. Monitoring and alerts

Alert on:

* a rising rate of `ERROR[PATH]`, `ERROR[DENIED]`, `ERROR[CWD]` or
  `ERROR[DOCKER_MISSING]` observations (possible probing or misconfiguration);
* timeouts and output truncation (limits too tight or a runaway command);
* audit chain verification failures;
* Docker daemon restarts, image pull failures, and disk pressure;
* container removal failures after timeouts;
* repeated `agent.max_steps` stops (prompt or tool-contract issue).

Dashboards should separate **refusals** (the sandbox working) from **failures**
(the sandbox or infrastructure broken). A refusal spike is not automatically an
incident; a dropped audit event is.

## 8. Incident response

### Suspected sandbox escape or host compromise

1. **Stop new work.** Disable the agent’s task intake; do not just ask the model
   to stop.
2. **Isolate the host.** Remove it from the network / stop the Docker daemon if
   the blast radius is unknown.
3. **Preserve evidence.** Copy the audit log and container logs; do not edit the
   audit file.
4. **Identify the boundary that failed.** Path policy? Docker flag? Image?
   Daemon? Host kernel?
5. **Rotate secrets** that were present in the environment or reachable from the
   host filesystem.
6. **Patch and retest** the specific control; add a regression test before
   re-enabling.
7. **Review other hosts** with the same image/daemon configuration.

### Audit chain failure

1. Treat the log as untrusted.
2. Compare the last verified event with the log shipper’s copy.
3. Check file permissions, disk errors and process crashes before assuming
   malicious tampering.
4. Preserve the broken segment; start a new one only after the investigation.

### Runaway container

1. `docker ps` to find the named container (`mini-harness-*`).
2. `docker rm -f <name>`.
3. Check the audit for the `tool.call` without a matching `tool.result`.
4. Inspect `DockerRunner` timeout and `--stop-timeout` settings.
5. Lower the per-command timeout or memory limit if the task does not need it.

## 9. Kill switch

The minimum viable kill switch is:

* stop accepting new tasks in the application;
* stop the Docker daemon or deny the harness user access to it;
* revoke the API key the model adapter uses;
* preserve the audit log.

Do not rely on a prompt instruction (“stop using tools”). The model is not a
security control.

## 10. Windows and macOS notes

* **Windows** needs Developer Mode or elevation to create symlinks; the path
  tests skip otherwise. POSIX `RLIMIT_*` tests skip. Docker Desktop runs Linux
  containers in a VM; the host file sharing layer matters for workspace
  permissions.
* **macOS** has POSIX rlimits and symlinks; Docker Desktop also runs a VM. File
  sharing performance and permission mapping are host-specific.
* **Linux** is the closest match to the book’s container assumptions. Use a
  non-root user, rootless Docker if possible, and a workspace owned by a uid
  that matches the container `--user`.

## 11. Capacity planning

Each concurrent agent run needs:

* one Python process (the harness);
* one `docker run` client process;
* one container (memory + CPU + pids);
* one audit append stream;
* workspace disk for edits and container scratch in tmpfs.

Size the host for the **sum of container limits**, not the average. A 256 MiB
limit per container is small, but 100 concurrent runs are 25 GiB before the
harness and the page cache.

## 12. Change control checklist

Before merging a change to any boundary:

- [ ] The threat model entry is updated.
- [ ] A test fails without the change and passes with it.
- [ ] The default is the safe option.
- [ ] The refusal is still an observation string.
- [ ] The audit event is still written outside the workspace.
- [ ] The Docker recipe still has every hardening flag.
- [ ] Windows/POSIX differences are documented.
- [ ] The operator runbook still matches the flags and defaults.
