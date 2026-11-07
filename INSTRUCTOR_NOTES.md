# Appendix E — Instructor and recording companion

> **Educational use only — not a production-ready system.** These notes are for an educational video series that walks through the book. The code is deliberately simplified. Do not present it as a secure, complete, or production-ready sandbox, and do not deploy it as-is.

This appendix is the production-side companion to the six chapters. It gives you
a repeatable recording workflow, a shot list for each stage, the exact commands
to run on camera, and the questions your audience is most likely to ask.

Use the chapters as the teaching material. Use this appendix as the run sheet.

## How to read the note cards

The book uses coloured callout cards throughout. Each icon has one job:

| Card | Icon | What it means on camera |
|---|---|---|
| Recording cue | 🎬 | Start, stop, or transition the take here. |
| Demo beat | 🧪 | Run this command or show this result on screen. |
| Pro tip | 💡 | A small production or teaching improvement. |
| Alert | ⚠️ | A common failure, safety issue, or claim to avoid. |
| Audience question | 🗣️ | A good question to pose before the explanation. |
| Edit note | ✂️ | Something to cut, shorten, or use as b-roll. |

> **Pro tip:** 💡 Keep a text file open beside the recording app with the
> commands from the current chapter. Paste commands into the terminal instead
> of typing them live. It removes dead air and typo retakes.

## Series shape and timing

The six stages make six episodes plus one short series trailer. The times below
are editing targets, not hard limits.

| Episode | Chapter | Target length | The one-sentence promise |
|---|---|---|---|
| Trailer | Introduction | 45–60 s | "A model can ask your computer to do things. This series builds the wall between the two." |
| 0 | The naive fence | 8–10 min | "The first sandbox is always a string check. Here is why it fails." |
| 1 | One path policy | 12–15 min | "Stop comparing spellings. Compare real filesystem paths." |
| 2 | The sandbox and file tools | 12–15 min | "A good path is not enough: bound the bytes, the writes, and the errors." |
| 3 | Running code locally | 14–18 min | "An argv allowlist is hygiene, not a jail." |
| 4 | Docker as the real wall | 16–20 min | "Move the command into a container and make the boundary explicit." |
| 5 | The finished harness | 16–20 min | "Route tools, limit the loop, and leave an audit trail you can verify." |

> **Edit note:** ✂️ A 15-minute target usually means a 25–35 minute raw take.
> Record one section at a time so a mistake costs one section, not the episode.

## Pre-record checklist

Run this before every session. It takes two minutes and saves retakes.

1. Activate the virtual environment.
2. Confirm Python and pytest are available.
3. Confirm Docker is running for Stages 4–5.
4. Build the container image once, before recording.
5. Run the chapter demo and tests off camera.
6. Clear terminals, browser tabs, notifications, and personal file paths.
7. Increase terminal font size. Use a light or dark theme with high contrast.
8. Check microphone levels and record a ten-second test.

> **Pro tip:** 💡 The demos render with Rich panels and colours. Keep colour on
> for a recording; use `NO_COLOR=1` or `MINI_HARNESS_THEME=mono` when you want a
> plain transcript for a log or CI artifact. Each chapter has its own accent,
> so the same terminal theme looks consistent across the series.

```powershell
# Windows PowerShell, from the repository root
.\.venv\Scripts\Activate.ps1
python --version
python -m pytest ch00 -q
docker version
```

```bash
# macOS / Linux, from the repository root
source .venv/bin/activate
python --version
python -m pytest ch00 -q
docker version
```

> **Alert:** ⚠️ Do not record Stage 0 with a real home directory visible in the
> terminal or on screen. The demo is deliberately unsafe. Use the throwaway
> `tempfile.TemporaryDirectory` in the chapter demo, and blur or rename any
> personal paths in the shell prompt.

## Screen and scene setup

A simple two-scene OBS layout is enough for the whole series.

| Scene | Contents | Use it for |
|---|---|---|
| `Talking head` | Camera, soft light, book cover or chapter title card | Cold open, transitions, conclusions |
| `Code` | Full-screen editor or terminal, small camera overlay | Walkthroughs and demos |
| `Diagram` | One slide with the boundary diagram | Explaining the concept before code |

Keep the terminal at roughly 18–22 pt. Keep lines under 90 characters. If a
command is long, put it in a shell script and show the script, then run it.

> **Pro tip:** 💡 Record at 1080p, not 4K, if you plan to zoom into code. A
> 1080p canvas with a clean 18 pt terminal is easier to read after compression
> than a 4K canvas scaled down.

## Episode run sheets

### Trailer and introduction

**Show:** the six-stage table from the Introduction, then a five-second clip of
the Stage 5 demo ending with `audit chain verifies: True`.

**Say:** "A coding agent is a loop that turns text into operating-system
actions. This series is about that conversion point: what a tool may do, how
much it may consume, and what the model sees when it is refused."

**Do not say:** "This is how to build a secure agent." Say: "This is how to
build and understand the boundary."

> **Recording cue:** 🎬 End the trailer on the promise of the Stage 3 cliffhanger:
> the local runner is still not a jail. That is the hook for Episode 4.

### Episode 0 — The naive fence

**Open with the bug, not the theory.** Show the three-line prefix check and ask
the audience to spot the flaw before you explain it.

**Demo beats:**

```bash
cd ch00
python -m mini_harness.demo
python -m pytest -v
```

**Show on screen:** the `[leaked]` prefix-sibling result and the `[blocked]`
plain traversal result. If the symlink case skips on Windows, say why.

**Talking points:**

- `startswith` compares spellings, not filesystem identities.
- `abspath` collapses `.` and `..`; it does not resolve symlinks.
- `shell=True` turns one request into a small program.
- The tests assert the bad outcomes so the failure is reproducible.

> **Audience question:** 🗣️ "If the path starts with the workspace folder,
> is it inside the workspace?" Pause. Then show `workspace-evil`.

> **Alert:** ⚠️ Never run the Stage 0 shell demo against your real home folder.
> Keep the harmless `echo` example. The point is the shape of the call.

### Episode 1 — One path policy

**Open with the question:** "Which file will the kernel actually open?" That is
the whole chapter.

**Demo beats:**

```bash
cd ch01
python -m mini_harness.demo
python -m pytest -v
```

**Show on screen:** a normal read, a traversal refusal, and the prefix-sibling
refusal, all through the same `PathPolicy`.

**Diagram:** `requested path -> lexical normalise -> resolve deepest existing
ancestor -> compare real paths -> allow or refuse`.

**Talking points:**

- One policy for every tool; no tool invents a second check.
- Reads may be absolute inside the root; writes must be relative.
- `commonpath` understands boundaries; `startswith` does not.
- The TOCTOU gap remains, and Stage 4 is the real answer.

> **Pro tip:** 💡 Put the `commonpath` comparison on screen as a single code
> block. Do not scroll through the whole module while explaining it.

### Episode 2 — The sandbox and file tools

**Open with the failure modes:** a 2 GB read, a million-entry directory, a
half-written file, a silent replace of three identical snippets.

**Demo beats:**

```bash
cd ch02
python -m mini_harness.demo
python -m pytest -v
```

**Show on screen:** one successful write, then `TOO_LARGE`, `EXISTS`,
`AMBIGUOUS`, and `PATH` observations. Point out that no traceback reaches the
model.

**Talking points:**

- Limits protect the agent process, not the host kernel.
- Atomic write: temp file in the same directory, fsync, replace.
- Edit is unique by default; `count=0` is an explicit opt-in.
- Delete is file-only; recursive delete is a different blast radius.
- Errors are observations, so the loop can continue.

> **Audience question:** 🗣️ "Why not just catch the exception and return it?"
> Answer: a traceback is noise in the model's context and can leak host paths.
> A stable error code is a contract.

> **Edit note:** ✂️ The symlink-write test can skip on Windows. Record the skip
> once, explain it, and move on. Do not fight the OS on camera.

### Episode 3 — Running code locally

**Open with the one-liner everyone writes:** `subprocess.run(user_string,
shell=True)`. Then list what that single line gives the model.

**Demo beats:**

```bash
cd ch03
python -m mini_harness.demo
python -m pytest -v
```

**Show on screen:** argv refusal, clean-environment sentinel, timeout kill, and
the final honest demo where the child reads a file outside the workspace.

**Talking points:**

- Argv, not a string: a semicolon is an argument, not a second command.
- Absolute-path allowlist; do not use `shutil.which` for model input.
- Clean environment: build it, do not inherit it.
- Timeout kills the process tree, not just the direct child.
- Output caps must keep draining the pipe or the child hangs.
- POSIX rlimits are not portable; Docker is the portable boundary.

> **Recording cue:** 🎬 End the episode on the outside-read result. Say: "That is
> not a bug in Stage 3. That is the reason Stage 4 exists." Cut to black.

> **Alert:** ⚠️ Do not claim the local runner is a sandbox. Call it hygiene, a
> guardrail, or accident prevention. The chapter says this explicitly; keep the
> video consistent with it.

### Episode 4 — Docker as the real wall

**Open with the threat Stage 3 cannot stop:** the child process can read the
user's SSH keys and open a network connection.

**Pre-record:** start Docker Desktop and build the image before the take.

```bash
cd ch04
docker build -t mini-harness-python:latest docker
python -m mini_harness.demo
python -m mini_harness.demo --build
python -m pytest -v
```

**Show on screen:** the full `docker run` argv, then the four live behaviours:
Python runs, network fails, root write fails, workspace is visible.

**Talking points:**

- Every flag in the run contract is a deliberate decision with a test.
- `--read-only` freezes the image, not the workspace bind mount.
- `--network none`, `--cap-drop ALL`, and `no-new-privileges` remove easy exits.
- Timeout cleanup needs `docker rm -f`; killing the CLI is not enough.
- The container shares the host kernel. It is a boundary, not magic.

> **Pro tip:** 💡 Put the flag table on screen as an overlay while the command
> runs. Pause on the four or five flags that matter most; do not read all of
> them aloud.

> **Alert:** ⚠️ Never mount the Docker socket into the sandbox, never add
> `--privileged`, and do not show a command that writes to the host outside the
> workspace.

### Episode 5 — The finished harness

**Open with the missing piece:** we have boundaries but no agent loop and no
record of what happened.

**Demo beats:**

```bash
cd ch05
python -m mini_harness
python -m mini_harness --build
python -m pytest -v
```

**Show on screen:** the write, the read, the container run, the final answer,
and `audit chain verifies: True`. Then show the audit JSONL and point at `seq`,
`prev`, and `hash`.

**Talking points:**

- The toolbox routes; it does not invent a second policy.
- The step limit lives in the loop, not in the model.
- A refusal is an observation; infrastructure absence still ends the loop.
- The audit is append-only, hash-chained, outside the workspace, and redacted.
- Tampering breaks `verify()`; the chain makes it visible, not impossible.

> **Audience question:** 🗣️ "Why not let the model decide when to stop?"
> Answer: a model may loop forever; the harness may not.

> **Recording cue:** 🎬 Close the series on the audit line, then a title card:
> "The boundary is the product." Keep the final take under 20 seconds.

## Demo reset between takes

Run these commands to return to a clean state. They are safe: they only remove
generated caches, audit files, and the chapter's sample output.

```bash
# From the repository root
find . -name "__pycache__" -type d -prune -exec rm -rf {} +
find . -name ".pytest_cache" -type d -prune -exec rm -rf {} +
rm -f ch05/audit/events.jsonl ch05/hello.py
```

```powershell
# Windows PowerShell
Get-ChildItem -Recurse -Directory -Filter __pycache__ | Remove-Item -Recurse -Force
Get-ChildItem -Recurse -Directory -Filter .pytest_cache | Remove-Item -Recurse -Force
Remove-Item ch05\audit\events.jsonl, ch05\hello.py -ErrorAction SilentlyContinue
```

> **Pro tip:** 💡 Re-run the chapter demo once after cleanup and before the take.
> A fresh run gives you the exact output you will point at later.

## Common recording failures

| Symptom | Likely cause | Fix |
|---|---|---|
| `ModuleNotFoundError: mini_harness` | Ran from the repository root, not the chapter | `cd ch00` (or the right chapter) first |
| `pytest: command not found` | Virtual environment not active | Activate `.venv`, or use `python -m pytest` |
| Docker demo prints `ERROR[DOCKER_MISSING]` | Docker Desktop is not running | Start Docker, wait for the whale icon, retry |
| Docker integration tests skip | Image not built | `docker build -t mini-harness-python:latest docker` from `ch04/` |
| Symlink test skips on Windows | Developer Mode or elevation is off | Explain the skip; do not enable Developer Mode just for the take |
| Audit verification fails on a second run | Old audit log has a broken chain | Remove `ch05/audit/events.jsonl` deliberately and re-run |
| Terminal text is unreadable after upload | Font too small or too many columns | 18–22 pt, wrap at 90 columns, enlarge the editor |

> **Alert:** ⚠️ If a test fails on camera, do not hide it. Show the failure,
> read the error code, and explain which contract caught it. That is better
> teaching than a suspiciously perfect run.

## Audience questions to plant

Use one question per episode as a cold open or a transition. They give the
audience a reason to keep watching.

1. **Stage 0:** "What is the difference between a path that looks inside and a
   file that opens inside?"
2. **Stage 1:** "Why is `startswith` the wrong tool for containment?"
3. **Stage 2:** "What should a model see when a tool refuses?"
4. **Stage 3:** "If the command runner is allowlisted, why can it still read
   your SSH keys?"
5. **Stage 4:** "Why is a read-only root filesystem not a read-only workspace?"
6. **Stage 5:** "How do you prove that nobody edited the audit log?"

## Titles, thumbnails, and descriptions

Keep titles concrete and outcome-led. Avoid claiming security guarantees.

| Episode | Title idea | Thumbnail text |
|---|---|---|
| Trailer | Build a Mini Python Sandbox | "The boundary is the product" |
| 0 | The sandbox that isn't | `startswith` is not enough |
| 1 | One path policy to rule them all | Real paths, not spellings |
| 2 | File tools that refuse safely | Errors are observations |
| 3 | Running code without `shell=True` | Argv. Timeout. Clean env. |
| 4 | Docker is the real wall | No network. No caps. |
| 5 | The finished agent harness | Audit chain verifies: True |

Description footer for every episode:

> Educational content only. This is not a production-ready sandbox. Do not
> deploy the code as-is. See the repository's `README.md` and
> `THREAT_MODEL.md` for the full limits.

## Editing notes

- **Keep the failure.** A refusal or a failed test is the lesson, not a blooper.
- **Cut installation and setup.** Put prerequisites in the description and a
  pinned comment.
- **Show the command before the output.** Let the viewer predict the result.
- **Zoom on one line at a time.** Do not show a whole module for a single idea.
- **Use chapter cards, not hard cuts.** A two-second card with the stage number
  and boundary makes the series easier to follow.
- **Caption code on screen.** Add the exact command to the lower third when the
  terminal is small.

> **Pro tip:** 💡 Export a clean `book.pdf` and put the chapter number in the
> video description. Viewers who want the written version can follow along
> without pausing the video.

## Final checklist before publishing

- [ ] The episode says "educational" and does not claim production security.
- [ ] Stage 0 is clearly labelled unsafe.
- [ ] The demo commands match the chapter exactly.
- [ ] The test output shown is from a real run, not a mock-up.
- [ ] Docker claims distinguish offline tests from integration tests.
- [ ] The audit line `audit chain verifies: True` is shown honestly.
- [ ] Personal paths, tokens, and notifications are not visible.
- [ ] Captions are enabled or a transcript is linked.
- [ ] The description links the book, `README.md`, and `THREAT_MODEL.md`.

> **Alert:** ⚠️ The series teaches a boundary, not a security certification.
> Keep the disclaimer in the video description, the pinned comment, and the
> spoken introduction of Episode 0.
