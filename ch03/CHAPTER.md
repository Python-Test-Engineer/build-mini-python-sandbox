# Chapter 3 — Stage 3: Running code locally

**Book:** Stage 3, "Running code locally"
**Plan:** Stage 3
**Goal:** Execute a command through an argv allowlist with a clean environment, a timeout, a process-tree kill and bounded output.

## The problem

The moment a coding agent can run a command, the sandbox story changes. File
tools are a small set of operations; a process is a general-purpose escape
hatch. The first version of a command tool is usually:

```python
subprocess.run(user_string, shell=True)
```

That single line gives the model:

* shell composition (`;`, `&&`, pipes, redirection);
* the parent environment, including API keys;
* unlimited run time;
* unlimited output;
* no CPU, memory, file-size or process limits;
* the same filesystem and network access as the agent process.

Stage 3 removes the easy accidents. It does **not** claim to be a jail.

## What changed

- Added `mini_harness/local_runner.py` with `CommandRunner`, `Limits`,
  `CommandPolicy` and `CommandResult`.
- Added `mini_harness/command_tool.py` with the model-facing `run_command`
  observation shape.
- Added `mini_harness/demo.py` and `tests/test_local_runner.py`.

## The seven controls

### 1. Argv, not a string

`CommandRunner.run("python", ["-c", "print('hi')"])` takes a program and a list
of arguments. Passing a single string is rejected. There is no `shell=True`
path in the runner.

A semicolon inside an argument is an ordinary character:

```text
python -c "print('a;b')"   ->  a;b
```

There is no second command to start.

### 2. An absolute-path allowlist

`CommandPolicy` maps a logical name to an absolute executable:

```python
{"python": sys.executable}
```

The runner does not use `shutil.which` for model-supplied names. A file called
`python` dropped into the workspace cannot shadow the interpreter through
`PATH`. The allowlist is checked again at call time; a missing executable is an
`IO` error, not a fallback to `PATH`.

### 3. A clean environment

`_clean_environment` starts from an empty dict and adds only:

* OS-essential variables (`SYSTEMROOT`, `WINDIR`, `COMSPEC`, `PATHEXT`, `LANG`,
  `LC_ALL`);
* a minimal `PATH`;
* workspace-local `HOME`, `TMP` and `TEMP`;
* deterministic Python flags.

A sentinel secret in the parent environment does not appear in the child. The
test asserts that directly.

### 4. A timeout with a process-tree kill

The child is started in a new session (POSIX) or a new process group (Windows).
On timeout the runner kills the **group**:

* POSIX: `os.killpg(os.getpgid(pid), SIGKILL)`;
* Windows: `taskkill /F /T /PID`.

Killing only the direct child would leave grandchildren running.

### 5. Output caps that still drain

Two background threads read stdout and stderr in 8 KiB chunks. Once the cap is
reached the bytes are discarded but the pipe keeps being read. If the parent
stopped reading, the child would block on a full pipe and never exit, turning
an output limit into a hang.

The observation always says when output was truncated.

### 6. POSIX resource limits

Before `exec`, the child lowers:

* `RLIMIT_CPU` — CPU seconds;
* `RLIMIT_AS` — address space;
* `RLIMIT_FSIZE` — maximum file size;
* `RLIMIT_NOFILE` — open file descriptors;
* `RLIMIT_NPROC` — process count (where supported).

Failures are swallowed: an unsupported limit should not stop a legitimate
command. On Windows there is no Python-level equivalent here; the book uses
container limits in Stage 4 instead. Do not pretend the local runner is
equivalent on both platforms.

### 7. A workspace-relative working directory

`cwd` goes through the same path policy as reads. The model cannot ask to run
from the user's home folder. A missing or non-directory cwd is a `CWD` refusal.

## What the demo proves, honestly

The final demo command reads a file **outside** the workspace:

```text
local runner is not a filesystem jail
  OK ... outside data
```

That is not a bug in Stage 3. It is the motivation for Stage 4. Hygiene is not
a boundary.

## Run it

From `ch03/`:

```bash
python -m mini_harness.demo
python -m pytest -v
```

The tests use the running Python interpreter as the only allowlisted program,
so they need no network and no shell. pytest is the sole test dependency.

## It works when

- [ ] A normal Python command returns stdout and exit code 0.
- [ ] stderr is captured separately.
- [ ] A non-zero exit is visible in the result.
- [ ] A string instead of a list returns `ARGS`.
- [ ] A non-allowlisted program returns `DENIED`.
- [ ] A sentinel parent-environment secret is `MISSING` in the child.
- [ ] A sleeping child is killed at the timeout, and the run returns quickly.
- [ ] A 5000-byte line is truncated to the configured cap.
- [ ] `cwd="../.."` returns `CWD`.
- [ ] On POSIX, the child sees the requested `RLIMIT_CPU` (test may skip on
      Windows).

## Stage limits

- Same user, same filesystem, same network. The child can read anything the
  user can read and connect to anything the user can connect to.
- `preexec_fn` is used for rlimits. It is only safe here because the runner
  executes one command at a time and starts no threads before `fork`. A
  concurrent server should use `posix_spawn` or a supervisor.
- The allowlist applies to the **direct** program. That program can spawn
  helpers. The container is what limits that.
- Windows has no rlimits in this chapter. The Docker chapter is the portable
  boundary.

## If it goes wrong

- **`DENIED` for a program that exists** — add its absolute path to the
  `CommandPolicy` mapping. Do not switch to `shutil.which` for model input.
- **The timeout takes longer than expected on Windows** — `taskkill /T` walks
  the process tree and can take a moment. The test uses a generous bound.
- **Output is empty after a timeout** — the child may have buffered its output.
  Use `flush=True` in the test program, or accept that partial output is not
  guaranteed.
- **`RLIMIT_AS` breaks a legitimate Python start** — the memory cap is applied
  to the interpreter too. Raise `memory_mb` deliberately and record why.
- **`preexec_fn` warnings** — do not call this runner from multiple threads in a
  larger application without redesigning child setup.

## Read next

- `../plan.md` Stage 3
- `../THREAT_MODEL.md` — command execution and resource exhaustion
- `../ch04/CHAPTER.md` — Docker as the real boundary
