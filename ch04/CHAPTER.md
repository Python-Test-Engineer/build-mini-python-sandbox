# Chapter 4 — Stage 4: Docker as the real wall

**Book:** Stage 4, "Docker as the real wall"
**Plan:** Stage 4
**Goal:** Run one argv command inside a no-network, no-capability, resource-limited container with a read-only root and a single workspace bind mount.

## The problem

Stage 3 is good hygiene, not a boundary. The local runner and the agent run as
the same user on the same kernel. A command can read the user's SSH keys, write
to the user's home folder, or open a network connection. Timeouts and rlimits
limit how much damage happens; they do not decide **what** is reachable.

Docker adds a kernel-backed boundary: namespaces, cgroups, capabilities, a
seccomp profile and a separate filesystem view. It is still not magic — a
container shares the host kernel — but it is a much better default than "same
process, same user, same filesystem".

## What changed

- Added `docker/Dockerfile` and `docker/.dockerignore`.
- Added `mini_harness/docker_runner.py` with `DockerRunner`, `DockerConfig` and
  `RunResult`.
- Added `mini_harness/demo.py` and `tests/test_docker_runner.py`.
- The tests assert the **exact** `docker run` flags without needing a daemon.

## The image contract

```dockerfile
FROM python:3.12-slim-bookworm
RUN groupadd --gid 1000 sandbox \
    && useradd --uid 1000 --gid sandbox --create-home \
       --shell /usr/sbin/nologin sandbox \
    && mkdir -p /workspace \
    && chown sandbox:sandbox /workspace
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONNOUSERSITE=1 \
    PYTHONIOENCODING=utf-8
WORKDIR /workspace
USER sandbox
CMD ["python", "-c", "print('mini-harness sandbox image ready')"]
```

The image does one job: run Python tools. It does not install a browser, a
compiler stack or a package manager workflow at runtime. Fewer tools mean fewer
ways out. The fixed `uid:gid` is what `--user` passes.

Build from `ch04/`:

```bash
docker build -t mini-harness-python:latest docker
```

Pin the base image by digest in a real deployment. "latest" is convenient for a
book and dangerous for production.

## The run contract

Every flag below is a deliberate decision. The tests fail if one disappears.

| Flag | Why it is there |
|---|---|
| `--rm` | Remove the container when it exits. |
| `--name <unique>` | Gives the timeout cleanup a reliable handle. |
| `--network none` | No network namespace connectivity. A command cannot exfiltrate data or fetch a payload. |
| `--read-only` | The container root filesystem is immutable. |
| `--cap-drop ALL` | Drop every Linux capability; no raw sockets, no mounts, no `chown` tricks. |
| `--security-opt no-new-privileges` | A setuid binary inside the image cannot gain privileges. |
| `--pids-limit 64` | Bounds process creation (fork bombs). |
| `--memory 256m` / `--memory-swap 256m` | Bounds memory and prevents swap from hiding the limit. |
| `--cpus 1.0` | Bounds CPU time per unit of wall clock. |
| `--ulimit nofile=64:64` | Bounds open file descriptors. |
| `--user 1000:1000` | Non-root inside the container. |
| `--workdir /workspace` | The only bind mount is the working directory. |
| `--tmpfs /tmp:...` | A small writable scratch space, `noexec`, `nosuid`, size-limited. |
| `--tmpfs /run:...` | Some tools expect `/run`; keep it small and ephemeral. |
| `--volume <workspace>:/workspace:rw` | The only host path visible. Change to `:ro` for read-only tasks. |
| `--env ...` | Explicit, minimal environment; the host environment is not passed through. |
| `--ipc none` | No shared IPC namespace. |
| `--stop-timeout 2` | Docker gets two seconds to stop the container before killing it. |
| `--init` | A tiny init reaps orphaned grandchildren inside the container. |

Docker's default seccomp profile still applies. The runner does not pass
`--privileged`, does not mount the Docker socket, and does not add devices.

## The important subtlety: read-only root is not read-only workspace

`--read-only` freezes the **image** filesystem. The bind mount at `/workspace`
is still writable when `workspace_mode="rw"`. That is intentional: a coding
agent must edit files. The boundary is "only this folder is writable", not
"nothing is writable".

If a task only needs to read, use:

```python
DockerConfig(workspace_mode="ro")
```

Then even the workspace is immutable inside the container, and the host file
tools remain the only way to change it.

## Timeout cleanup

`docker run --rm` removes the container when it exits. If the command hangs,
the Python runner must **also** remove the container, because killing the
`docker` CLI process does not necessarily stop the daemon-side container. The
runner calls:

```python
docker rm -f <container-name>
```

then kills the CLI process. The unique name makes this safe.

## Run it

From `ch04/`:

```bash
python -m mini_harness.demo
python -m mini_harness.demo --build
python -m pytest -v
```

The first command prints the full `docker run` argv even when Docker is not
installed. The integration tests skip when the daemon or image is missing.

## It works when

- [ ] The command contains `--network none`, `--read-only`, `--cap-drop ALL`,
      `--security-opt no-new-privileges`, `--pids-limit`, `--memory`,
      `--memory-swap`, `--cpus`, `--ulimit`, `--user`, `--workdir`, `--tmpfs`,
      `--volume`, `--ipc none` and `--init`.
- [ ] There is exactly one `--volume`, and it ends in `:/workspace:rw`.
- [ ] `workspace_mode="ro"` changes the mount to `:ro`.
- [ ] `cwd="sub"` becomes `/workspace/sub`; `cwd="../.."` returns `CWD`.
- [ ] A string argv returns `ARGS`; an empty argv returns `ARGS`.
- [ ] A host environment secret does not appear in the command.
- [ ] A configuration with `network="bridge"` or `read_only_root=False` is
      refused.
- [ ] With Docker and the image present: Python runs, the network fails, the
      root filesystem refuses a write, and the workspace is visible.

## Stage limits

- A container shares the host kernel. Kernel exploits and Docker daemon
  compromise are outside this boundary.
- The Docker socket is extremely powerful. Never mount it into the sandbox.
- The image is part of the attack surface. Pin the base by digest, rebuild on
  security updates, and review packages.
- On Windows/macOS, Docker Desktop runs Linux containers in a VM. The boundary
  is real, but the host file sharing layer and the VM configuration still
  matter.
- Bind-mount permissions depend on the host user and Docker's user mapping.
  `--user 1000:1000` may not be able to write on a host where the workspace is
  owned by a different uid. This is a deployment decision, not a bug.
- `--network none` blocks network access inside the container; it does not stop
  the Docker daemon, the host, or a sibling container.

## If it goes wrong

- **`docker: command not found`** — install Docker Desktop/Engine and start it.
  The unit tests still run; only the integration tests skip.
- **`Cannot connect to the Docker daemon`** — start Docker Desktop or the
  `docker` service. `check_available()` uses `docker version` for this reason.
- **`image not found` / integration skip** — build the image from `ch04/`:
  `docker build -t mini-harness-python:latest docker`.
- **A file written in `/workspace` is owned by root** — check the host mount
  and the `--user` mapping. On Linux, use a uid:gid that matches the workspace
  owner, or `chown` the workspace before the run.
- **The container is still present after a timeout** — check that the unique
  `--name` was passed and that `docker rm -f` has permission to talk to the
  daemon.
- **A command that needs a writable cache fails** — do not make the root
  writable. Add a small, explicit tmpfs at the path the tool needs, or set
  `HOME`/`TMP` to `/tmp`.

## Read next

- `../plan.md` Stage 4
- `../OPERATIONS.md` — image updates, daemon security and incident response
- `../ch05/CHAPTER.md` — wiring Docker into the final harness
