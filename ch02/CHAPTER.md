# Chapter 2 — Stage 2: The sandbox object and file tools

> **Educational use only — not a production-ready system.** This chapter is part of an educational project to learn and understand. It deliberately simplifies design, error handling, security, and operations so the core idea stays visible. Do not deploy this code as-is.

**Book:** Stage 2, "The sandbox object and file tools"
**Plan:** Stage 2
**Goal:** Put every file operation behind one object with size limits, atomic writes and a stable error vocabulary.

## The problem

A path policy is necessary but not sufficient. Even a correctly resolved path
can be used badly:

* reading a 2 GB file into the model's context;
* listing a directory with a million entries;
* writing a file in place, so a crash leaves half a file;
* following a symlink for a write that the policy only checked marginally;
* raising a Python exception that unwinds the agent loop.

Stage 2 turns the policy into a **sandbox contract**. The policy still answers
"where"; the sandbox answers "how much, how safely, and what does the caller
see when it is refused?"

> **Recording cue:** 🎬 Open with the four failure modes as a list, not with the
> code. The viewer should feel the problem before seeing `Limits(...)`.

## What changed

- Added `mini_harness/sandbox.py` with `Sandbox`, `Limits`, `DirEntry` and
  `SandboxError`.
- Added `mini_harness/file_tools.py` with the model-facing tool contract and
  `run_tool`.
- Added `mini_harness/demo.py` and `tests/test_sandbox.py`.

## The contract

### Limits

```python
@dataclass(frozen=True)
class Limits:
    max_read_bytes: int = 2 * 1024 * 1024
    max_write_bytes: int = 1 * 1024 * 1024
    max_dir_entries: int = 500
    max_line_bytes: int = 4000
```

These are policy choices, not security boundaries. They protect the **agent
process** from a tool result that is too large to handle. A model can still ask
for a small file many times; the loop's step limit and the operator's rate
limits are the answer to that.

### Reads are byte-bounded

`read_text` checks `stat().st_size` before opening. It then reads bytes and
decodes UTF-8 with `errors="replace"`. Reading bytes:

* applies the limit to exactly the data received;
* avoids newline translation, so an edit round-trip preserves `\r\n`;
* avoids crashing on one stray non-UTF-8 byte.

### Writes are atomic

The writer creates a temporary file in the **same directory**, writes and
flushes it, calls `os.fsync`, then `os.replace`s it over the target. A reader
sees the old file or the new file, never a half-written one. The temporary file
is removed on failure.

The parent folders are created one component at a time, and the policy is
re-run after each `mkdir`. That does not eliminate a determined race, but it
catches a symlink planted between the first check and the write. The real fix
for a hostile local user is the container in Stage 4.

### Edits are unique by default

`edit_text(path, old, new)` refuses when `old` appears zero times or more than
once. A silent `replace` of three identical snippets is a classic way for an
agent to corrupt code. Passing `count=0` means "replace all" and is an explicit
opt-in.

### Deletes are file-only

`delete_file` refuses directories and non-regular files. Recursive delete is a
much larger blast radius than one file, and an agent can always ask for files
one at a time. A symlink is refused by the policy before this method sees it.

### Errors become observations

Tools return strings, not exceptions:

```text
OK: wrote 19 bytes to todo.md
ERROR[PATH]: path escapes workspace: ../outside.txt
ERROR[TOO_LARGE]: content is 2000 bytes; limit is 1024
ERROR[IS_DIR]: refusing to delete a folder
```

`run_tool` catches `SandboxError`, `KeyError`-style argument mistakes and
unexpected exceptions. A bug in a tool is labelled `INTERNAL` and does not kill
the session. The traceback belongs in the server log, not in the model's
context.

## Run it

From `ch02/`:

```bash
python -m mini_harness.demo
python -m pytest -v
```

The demo performs normal work and then four refusals. The exact observation
strings are what a model would see.

> **Demo beat:** 🧪 Show one successful write, then `TOO_LARGE`, `EXISTS`,
> `AMBIGUOUS`, and `PATH` in that order. End on the fact that no traceback
> reaches the model.

> **Audience question:** 🗣️ "Why not just catch the exception and return the
> traceback?" Answer: a traceback is noisy context and can leak host paths. A
> stable error code is a contract the model can act on.

## It works when

- [ ] `read_text` returns the file, preserves `\r\n`, and refuses a directory.
- [ ] A read over the limit returns `TOO_LARGE`.
- [ ] A write creates missing parent folders.
- [ ] A write leaves no `.sandbox-*.tmp` file behind.
- [ ] `overwrite=False` returns `EXISTS` instead of clobbering.
- [ ] An edit with missing or repeated old text returns `NO_MATCH` or
      `AMBIGUOUS`.
- [ ] A delete of a folder returns `IS_DIR`.
- [ ] An escape returns `ERROR[PATH]`, not a traceback.
- [ ] The symlink-write test skips on a machine that cannot create symlinks.

## Stage limits

- Still the same user on the same kernel. A command tool would be able to
  bypass the sandbox entirely.
- Still a time-of-check/time-of-use gap between policy and open.
- No command execution yet.
- No audit trail yet.

> **Alert:** ⚠️ These limits protect the agent process from oversized results.
> They do not protect the host from a command. Stage 3 adds a runner, and Stage
> 4 makes the runner live behind a real boundary.

## If it goes wrong

- **An edit changes the wrong text** — check that the unique-match default is
  active and that `count=0` is only used deliberately.
- **A write succeeds but the file is empty** — check that the temp file is
  flushed and fsynced before `os.replace`, and that the bytes are written
  before the handle closes.
- **A new nested path fails** — `_ensure_parent` walks `relative_to(root)` and
  creates each missing component. A parent that is a file returns `NOT_DIR`.
- **Windows says the temp file is in use** — an open handle usually means the
  writer raised before `os.replace`. The cleanup path removes it; check the
  `IO` message for the underlying error.
- **A symlink read looks like a normal file** — that is correct: reading
  through a symlink is allowed when the resolved target is inside the root. A
  write through a final symlink is refused.

## Read next

- `../plan.md` Stage 2
- `../THREAT_MODEL.md` — resource exhaustion and file-write threats
- `../ch03/CHAPTER.md` — command execution without a shell