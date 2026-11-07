# Chapter 1 — Stage 1: One path policy

**Book:** Stage 1, "One path policy"
**Plan:** Stage 1
**Goal:** Replace the string-prefix fence with one object that resolves real paths and answers the same question for every tool.

## The problem

The naive fence fails because it asks "does this path *look* like it is inside
the workspace?" The kernel asks "which file will this path *open*?" Those are
different questions, and only the second one matters.

There are three layers to get right:

1. **Lexical normalisation.** Collapse `.` and `..`; reject NUL bytes, control
   characters, UNC paths and drive-relative forms.
2. **Symlink resolution.** Follow every link in the longest existing prefix,
   then reattach the part that does not exist yet.
3. **Containment.** Compare canonical paths with a real common-path check, not
   `startswith`.

Stage 1 puts all three in `mini_harness/path_policy.py`. It contains no
file-content logic. It only answers where a path points.

## What changed

- Added `mini_harness/path_policy.py` with `PathPolicy`, `PolicyError` and
  `ResolvedPath`.
- Added `mini_harness/demo.py`, which exercises allowed and refused names.
- Added `tests/test_path_policy.py` with 25 cases covering the platform edges.

## The central algorithm

### Resolve the deepest existing ancestor

A write target often does not exist yet:

```text
workspace/deep/new/file.txt
```

`os.path.realpath` only resolves what is on disk. If the whole path is missing,
it cannot tell you that `workspace/link-to-outside` is a symlinked parent.

`_realpath_best` walks upward until it finds something that exists, resolves
that prefix, then reattaches the missing components:

```python
current = Path(os.path.abspath(path))
missing = []
while not current.exists():
    missing.append(current.name)
    current = current.parent
resolved = Path(os.path.realpath(current))
for part in reversed(missing):
    resolved = resolved / part
```

This catches the important case:

```text
workspace/outside-link/new.txt
                ^ symlink to /tmp/attacker
```

The `new.txt` does not exist, but its parent does. Resolving the parent proves
that the canonical target is outside the workspace.

### Compare real paths with `commonpath`

```python
root = os.path.normcase(str(self.real_root))
target = os.path.normcase(str(real_target))
common = os.path.commonpath([root, target])
return common == root
```

`commonpath` understands path boundaries. On Windows it raises `ValueError` for
paths on different drives; that is a refusal, not a crash. `normcase` lowercases
on Windows so case-insensitive filesystems compare correctly.

### Reads and writes differ on purpose

Reads may be absolute as long as the resolved file is inside the root. A
developer may want to read a file by its full path. Writes must be relative:
a write should be an intentional workspace action, not an absolute overwrite of
a system file.

Writes also refuse a final symlink. The atomic writer in Stage 2 would replace
the link rather than follow it, but other tools may not. Refusing at the policy
layer makes the rule independent of the tool.

### Platform spellings are normalised before validation

The policy treats `\` as a separator on every platform. On POSIX, `..\secret`
would otherwise be a legal (but bizarre) filename. Normalising it makes the
answer the same everywhere: that is traversal, and it is refused.

The policy also rejects:

* `C:foo` — drive-relative, not drive-absolute;
* `\\server\share` — UNC;
* `CON`, `NUL`, `LPT1.log` — Windows device names;
* `file.txt:stream` — an NTFS alternate data stream (colon-bearing names are refused);
* trailing dots and spaces on Windows — the OS may strip them, so two different
  strings can name the same file;
* control characters, especially NUL.

## Run it

From `ch01/`:

```bash
python -m mini_harness.demo
python -m pytest -v
```

The demo prints the canonical path for allowed names and a `PATH:` refusal for
the rest:

```text
[allowed] read notes.txt: notes.txt -> ...\workspace\notes.txt
[blocked] read ../outside.txt: PATH: path escapes workspace: ../outside.txt
[blocked] read prefix sibling: PATH: path escapes workspace: ../workspace-evil/secret.txt
```

## It works when

- [ ] A normal read resolves to a canonical path inside the root.
- [ ] `../outside.txt` is refused.
- [ ] `../workspace-evil/secret.txt` is refused (the Stage 0 bug).
- [ ] An absolute path inside the root is allowed for reads.
- [ ] An absolute path outside the root is refused.
- [ ] A write to an absolute path is refused.
- [ ] A write through a symlink is refused.
- [ ] `CON.txt`, `C:foo`, UNC and NUL-byte names are refused.
- [ ] The symlink tests skip, rather than fail, on a machine that cannot create
      symlinks.

## Stage limits

- The policy is not a jail. A Python process running as the same user can still
  open files directly with `os.open`, race a check, or read `/proc`.
- The policy does not cap file sizes; Stage 2 adds that.
- The policy does not audit refusals; Stage 5 adds that.
- `realpath` + `open` is still a time-of-check/time-of-use gap. The only full
  answer is a separate security boundary (Stage 4).

## If it goes wrong

- **A symlink test skips on Windows** — enable Developer Mode or run elevated,
  or accept the skip. The prefix-sibling and traversal tests still exercise the
  containment logic.
- **`resolve_read("C:/x")` behaves differently on POSIX** — drive-absolute
  paths are refused on non-Windows because they would be interpreted as a
  relative name containing a colon. This is intentional.
- **A path with `..` gets a reserved-name error** — make sure `.` and `..` are
  skipped by the reserved-name check and handled by normalisation. The tests
  cover this.
- **A write to a new nested path is refused** — check that
  `_realpath_best` reattaches the missing tail after resolving the parent.
  Stage 2's `_ensure_parent` creates those folders.

## Read next

- `../plan.md` Stage 1
- `../THREAT_MODEL.md` — path traversal and symlink threats
- `../ch02/CHAPTER.md` — file tools with size limits and atomic writes
