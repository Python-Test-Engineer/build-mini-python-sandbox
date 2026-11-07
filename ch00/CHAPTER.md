# Chapter 0 — Stage 0: The naive fence

> **Educational use only — not a production-ready system.** This chapter is part of an educational project to learn and understand. It deliberately simplifies design, error handling, security, and operations so the core idea stays visible. Do not deploy this code as-is.

**Book:** Stage 0, "The naive fence"
**Plan:** Stage 0
**Goal:** Build the smallest possible tool surface, then prove that its sandbox is not a sandbox.

## The shape we are building

A coding agent is a loop:

```text
user task -> model -> tool call -> observation -> model -> ... -> final answer
```

The interesting part for this book is the arrow between **tool call** and
**observation**. A tool is where model text becomes an operating-system action:
a file read, a file write, a process start. Everything else is conversation.
Sandboxing is the set of decisions that controls that arrow.

> **Recording cue:** 🎬 Open with the three-line prefix check, not the theory.
> Ask the viewer to spot the flaw before you name it. The answer lands harder
> after a pause than after a definition.

Stage 0 deliberately makes the wrong decisions, because they are the ones a
first prototype usually makes:

* join the requested path to a workspace root;
* check that the result starts with the root as a **string**;
* run commands through the platform shell;
* inherit the parent environment;
* trust the model not to ask for anything strange.

Each of those choices looks reasonable in a demo. Each has a concrete failure.

## What changed

- Added `mini_harness/unsafe.py` with `read_file`, `list_files` and `run_shell`.
- Added `mini_harness/demo.py`, which builds a throwaway lab and shows the holes.
- Added `tests/test_unsafe.py`, which **asserts the bad outcomes** so the
  threat model is executable.

## The three holes

### 1. A prefix check is not a containment check

```python
target = os.path.abspath(os.path.join(root, relative))
if target.startswith(root):
    return Path(target).read_text()
```

`/tmp/workspace-evil` starts with `/tmp/workspace`. A sibling folder therefore
passes the fence. The check compares spellings, not filesystem identities.

### 2. A symlink is inside the workspace by name and outside by target

```text
workspace/innocent-link.txt -> /home/me/.ssh/id_ed25519
```

The string `workspace/innocent-link.txt` starts with `workspace`, so the check
passes. The kernel follows the link and opens the key. `os.path.abspath` does
not resolve symlinks; it only collapses `.` and `..`.

### 3. A shell is not a command runner

```python
subprocess.run(command, shell=True, cwd=root)
```

This gives one tool call the power to become many commands. It also inherits
every secret in the parent environment, has no wall-clock limit, captures
unbounded output in memory, and applies no CPU, memory or file-size limit.

The tests keep the shell command harmless (`echo hello`). The point is the
shape of the call, not a destructive example. Never point Stage 0 at a real
home directory.

## Run it

From `ch00/`:

```bash
python -m mini_harness.demo
python -m pytest -v
```

The demo uses `tempfile.TemporaryDirectory`. On Windows without Developer Mode,
creating a symlink is refused by the OS; the demo prints a skip line and still
shows the prefix-sibling escape.

Expected shape:

```text
[leaked ] prefix sibling: sibling secret\n
[blocked] plain ../ traversal: ValueError: path escapes workspace: ../outside-secret.txt
```

> **Demo beat:** 🧪 Show the `[leaked]` prefix-sibling line first, then the
> `[blocked]` traversal line. The contrast is the whole episode: one is caught
> by spelling, the other is not a spelling problem at all.

> **Alert:** ⚠️ Keep the shell command harmless. Never point this stage at a
> real home folder or run a destructive command for a reaction. The lesson is
> the shape of the call, not the damage.

## It works when

- [ ] `python -m mini_harness.demo` exits zero.
- [ ] The prefix-sibling read is reported as `[leaked]`.
- [ ] Plain `../` traversal is reported as `[blocked]`.
- [ ] On a symlink-capable machine, the symlink read is reported as `[leaked]`.
- [ ] `python -m pytest -v` passes (symlink test may skip).
- [ ] You can explain why the symlink case is invisible to `startswith`.

## Why keep the broken code?

Because "we will add security later" is easier to resist when the first version
comes with a failing threat model. The tests are not celebrating the holes; they
are pinning them down. Chapter 1 replaces the expectations with the opposite
ones: the escape must be refused.

A second reason is pedagogical: the fixed version is easier to trust when you
have seen the exact input that broke the naive version.

> **Audience question:** 🗣️ "If the path starts with the workspace folder, is it
> inside the workspace?" Pause, then show `workspace-evil`. That one example
> carries the entire episode.

> **Edit note:** ✂️ If the symlink case skips on Windows, record the skip once,
> explain Developer Mode, and move on. Do not spend the take fighting the OS.

## Stage limits

- No real path policy.
- No size limits.
- No command allowlist, timeout or output cap.
- No audit trail.
- The demo is intentionally unsafe; do not reuse `unsafe.py`.

## If it goes wrong

- **The demo blocks plain `../` and nothing else** — that is correct for this
  stage. The string check catches the obvious spelling.
- **The symlink case skips** — Windows needs Developer Mode or an elevated
  process to create symlinks. The prefix-sibling case still demonstrates the
  class of bug.
- **A test fails because echo is missing** — the demo uses the platform shell;
  `echo` is available in both `cmd.exe` and POSIX shells. If your environment is
  unusual, replace it with `python -c "print('hello')"` in `run_shell`.

## Read next

- `../plan.md` Stage 0
- `../THREAT_MODEL.md` — the full list of assets and threats
- `../ch01/CHAPTER.md` — one path policy for every tool