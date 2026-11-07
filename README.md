# Build a Mini Python Sandbox

> **Educational use only — not a production-ready system.**
> This repository is an educational project to learn and understand how to sandbox a small Python coding agent. It is intentionally simplified, optimised for clarity and step-by-step learning, and makes no claim to be secure, complete, or production-ready. Do not deploy it as-is. If you adapt it for real work, add proper validation, isolation, monitoring, testing, and operational controls.

Companion code for a short, hands-on book about sandboxing a small **Python
coding agent** — from a deliberately broken string-prefix fence to a hardened
Docker container with a hash-chained audit log.

The book is the six `chNN/CHAPTER.md` files. This repository is the runnable
version: every stage is a standalone Python project, every module is commented,
and every security claim has a test beside it.

> **Safety note.** Stage 0 is intentionally unsafe. It exists to demonstrate
> three concrete holes, and its demo only runs against a temporary directory.
> Do not point `unsafe.py` at your home folder, do not add `--privileged` to the
> Docker recipe, and never mount the Docker socket into the sandbox.

## What the book builds

| Stage | Chapter | The boundary added |
|---|---|---|
| 0 | The naive fence | A string prefix check and a shell call — and proof of why they fail |
| 1 | One path policy | Canonical paths, symlink resolution, platform rules |
| 2 | The sandbox and file tools | Size limits, atomic writes, safe edits, observations |
| 3 | Running code locally | Argv allowlist, clean env, timeout, tree kill, output caps, rlimits |
| 4 | Docker as the real wall | Network none, read-only root, capabilities dropped, resource limits |
| 5 | The finished harness | Tool routing, ReAct loop, audit chain, offline demo |

A coding agent is a loop that turns model text into operating-system actions.
The book focuses on that conversion point: **what a tool is allowed to do, how
much it may consume, and what the model sees when it is refused.**

## Quick start

Each chapter runs from its own directory. The runtime code has no third-party
dependencies; pytest is the only test dependency. Install it once with
`python -m pip install pytest` (or use your own environment manager). No API
key is required. Python 3.11 or newer is recommended.

```bash
cd ch00
python -m mini_harness.demo
python -m pytest -v
```

The finished harness:

```bash
cd ch05
python -m mini_harness                 # offline demo, Docker optional
python -m mini_harness --build         # build the sandbox image first
python -m pytest -v
```

With Docker installed and the image built:

```bash
cd ch04
docker build -t mini-harness-python:latest docker
python -m mini_harness.demo
```

Docker integration tests skip cleanly when the daemon or image is missing. The
offline tests never need Docker.

## Rebuild the book artifacts

The chapters and manuals are the editable sources. `scripts/build_book.py`
concatenates them into two generated Markdown variants: `book.md` for the PDF
(one title, `##` chapters) and `book_html.md` for the sidebar reading guide
(one `#` per chapter).

```bash
python scripts/build_book.py
```

PDF export (needs `markdown` and `pypdf`; Chrome or Edge is detected
automatically):

```bash
python skills/make-pdf-from-md/scripts/make_pdf.py book.md book.pdf --title "Build a Mini Python Sandbox" --keep-html build/book.html
```

HTML reading guide (needs Node.js; the local converter is in the skill):

```bash
python scripts/build_book_html.py
```

`book.pdf` and `book.html` are the two reader-facing artifacts; `book.md` and
`book_html.md` are generated intermediate sources.

## Repository map

| Path | What it is |
|---|---|
| `ch00/` … `ch05/` | One standalone, runnable stage per chapter |
| `chNN/CHAPTER.md` | The chapter: problem, design, walkthrough, acceptance, limits |
| `chNN/mini_harness/` | The stage's Python package |
| `chNN/tests/` | unittest-style tests, collected by `pytest` |
| `chNN/workspace/` | A small sample workspace for experimenting |
| `ch04/docker/`, `ch05/docker/` | The sandbox image |
| `plan.md` | The stage-by-stage build contract |
| `function_reference.md` | Alphabetical and file-by-file code map |
| `THREAT_MODEL.md` | Assets, adversaries, threats, mitigations and residual risk |
| `OPERATIONS.md` | Build, run, update, audit and incident-response runbook |
| `qa.html` | Architecture Q&A companion built with the shared explainer standard; open it in a browser |
| `book.md`, `book.pdf` | Generated combined manuscript and print-ready PDF |
| `book_html.md`, `book.html` | Generated HTML source and sidebar reading guide |
| `scripts/build_book.py`, `scripts/build_book_html.py` | Rebuild the combined sources and the HTML reading guide |
| `scripts/md-to-html.mjs` | Canonical Markdown → styled explainer converter |
| `assets/explainer.css`, `assets/explainer.js` | The one stylesheet and behaviour shared by every explainer |
| `templates/explainer.html` | Starter page for a hand-built explainer |
| `EXPLAINERS.md` | The HTML explainer standard (layout, components, checklist) |
| `skills/` | Local PDF/HTML generation skills and scripts |
| `EXPLAINERS.md` | Shared HTML explainer standard |
| `assets/`, `templates/` | Shared explainer CSS/JS and starter page |

## Design rules used throughout

1. **One policy per boundary.** File paths go through one `PathPolicy`. Container
   flags go through one `DockerRunner`. A tool does not invent a second check.
2. **Refusals are observations.** A tool returns `ERROR[PATH]: ...`, not a
   traceback. The loop continues; the model can choose another action.
3. **No shell for model input.** Commands are argv lists. A semicolon is an
   argument, not a second command.
4. **The environment is built, not inherited.** A child process sees the
   variables the OS needs and nothing else.
5. **Limits are explicit.** Byte caps, entry caps, timeouts, memory, pids and
   step counts each have a named default and a test.
6. **Defence in depth.** The path policy protects the file tools; the container
   protects everything that escapes Python.
7. **The audit is outside the workspace.** Tools cannot edit their own trail
   through the sandbox, and the hash chain makes edits visible.
8. **The step limit is in the loop.** A model may loop forever; the harness may
   not.

## Test map

| Chapter | Command | Docker needed | Notes |
|---|---|---|---|
| `ch00` | `python -m pytest -v` | No | Asserts the three unsafe outcomes |
| `ch01` | same | No | Symlink tests skip if the OS refuses links |
| `ch02` | same | No | Atomic writes, limits, error strings |
| `ch03` | same | No | Uses the running Python as the only allowlisted program |
| `ch04` | same | Optional | Offline tests inspect every `docker run` flag; integration skips |
| `ch05` | same | Optional | Audit chain, agent loop, CLI demo; Docker step skips |

Run all chapters from the repository root:

```bash
for chapter in ch00 ch01 ch02 ch03 ch04 ch05; do
  echo "== $chapter =="
  (cd "$chapter" && python -m pytest -v)
done
```

On Windows PowerShell:

```powershell
foreach ($chapter in "ch00","ch01","ch02","ch03","ch04","ch05") {
  Write-Host "== $chapter =="
  Push-Location $chapter
  python -m pytest -v
  Pop-Location
}
```

## Platform notes

* **Windows.** Creating symlinks needs Developer Mode or an elevated process;
  the path-policy symlink tests skip when the OS refuses. POSIX `RLIMIT_*`
  tests also skip. The Docker chapters use Linux containers through Docker
  Desktop.
* **macOS / Linux.** Symlink and rlimit tests run. Docker Desktop or Docker
  Engine is needed only for the integration tests.
* **No Docker?** The book still teaches the whole path from Stage 0 to Stage 3,
  and Stage 4's offline tests validate the exact container recipe.

## Where to start reading

Read `THREAT_MODEL.md` first if you want the “why”. Read `plan.md` if you want
the contract. Read `function_reference.md` when you are tracing a function.
Open `qa.html` when you want the short answer to an architecture question. Every
HTML explainer follows `EXPLAINERS.md`; generate a new one from Markdown with
`node scripts/md-to-html.mjs <input.md>`.

Then start at `ch00/CHAPTER.md` and run each stage in order. The code is
cumulative in shape but each chapter is standalone on disk, so you can jump to
the boundary you care about.