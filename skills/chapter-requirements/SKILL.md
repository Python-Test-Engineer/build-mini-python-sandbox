---
name: chapter-requirements
description: Contract for the book's runnable chapter snapshots (ch00–ch16). Use when creating, generating, reviewing, or fixing any chNN project so each chapter is a standalone snapshot of exactly one plan stage, installs offline, passes npm test, and records intentional deviations.
---

# chapter-requirements

Every `chNN/` directory is a **snapshot project**: the complete, runnable state of
the mini coding harness *after* that plan stage, with **no later-stage features**.
A reader must be able to `cd ch07 && npm install && npm test` and see exactly what
the book says.

Authoritative sources, in order:

1. **`plan.md`** — stage contract: what exists, API surface, defaults, acceptance.
2. **`mini-js-coding-harness.md`** — reader-facing chapter: commands, expected
   output, checkpoints.
3. **`mini-coding-agent-js/`** — finished reference; implementation details only.
   Never copy later-stage features backwards.

If plan and book disagree, follow the plan for scope and record it in the
chapter's `CHAPTER.md`. If plan and reference disagree, resolve explicitly and
record it in `references/DEVIATIONS.md` (or the repository copy if one exists) — never silently choose.

Full source documents live in `references/`:
`chapter_project_requirements.md` and `DEVIATIONS.md`.

---

## Chapter numbering

`chNN` maps one-to-one to Stage `NN`. All chapters live at the repository root;
the obsolete `BOOK/` wrapper is gone.

| Folder | Stage | Project state | Added | Modified | Proof |
|---|---|---|---|---|---|
| `ch00` | 0 | Flat scaffold; one dependency; no CLI | `package.json`, `.gitignore`, `src/.gitkeep`, `workspace/.gitkeep` | — | `npm install`; `npm ls --depth=0`; `node --test` (0 tests) |
| `ch01` | 1 | Terminal output helpers; strings only | `src/ui.js`, `test/ui.test.js` | — | `node --test test/ui.test.js` |
| `ch02` | 2 | Config with provenance; one OpenRouter POST; no CLI | `src/config.js`, `src/llm.js`, `test/config.test.js`, `test/llm.test.js` | — | `node --test test/config.test.js test/llm.test.js` |
| `ch03` | 3 | First runnable chatbot; one task, one reply; no tools | `src/cli.js`, `test/input.test.js` | — | `--help`; live task; non-TTY exits 2 |
| `ch04` | 4 | Interactive session; `messages`; `/new`, `/quit`, `/exit` | — | `src/cli.js` | Live multi-turn; `/new`; summary |
| `ch05` | 5 | System prompt module; rules injected; no tools | `src/prompt.js`, `test/prompt.test.js` | `src/cli.js` | `node --test test/prompt.test.js` |
| `ch06` | 6 | Path policy; reads open, writes fenced; no tools | `src/workspace.js`, `test/workspace.test.js` | — | `node --test test/workspace.test.js` |
| `ch07` | 7 | Read-only tools + manual tool loop | `src/tools.js`, `test/tools.test.js` | `src/prompt.js`, `src/cli.js` | Live list/read; tools tests |
| `ch08` | 8 | Sandbox + create/write/edit/delete tools | `src/sandbox.js`, `test/sandbox.test.js` | `src/tools.js`, `src/cli.js` | Live create/edit; escape write refused; sandbox tests |
| `ch09` | 9 | `run_command`: tokeniser, write scan, deny-list, policy, safe env | `test/shell-sandbox.test.js` | `src/sandbox.js`, `src/tools.js`, `src/cli.js` | Live command; `CMD_POLICY=deny`; Desktop-copy refusal |
| `ch10` | 10 | File-backed memory; digest injection; `remember`/`recall` | `src/memory.js`, `src/memory.md`, `test/memory.test.js` | `src/prompt.js`, `src/tools.js`, `src/cli.js` | `--memory`; remember/recall across runs |
| `ch11` | 11 | Nine lifecycle hooks; catalogue, trace, deciding hooks | `src/hooks.js`, `test/hooks.test.js` | `src/cli.js` | `--hooks`; `--no-hooks`; hooks tests |
| `ch12` | 12 | ReAct loop in library; heartbeat; step limit; truncation guard | `src/agent.js`, `src/heartbeat.js`, `test/agent.test.js` | `src/cli.js` | agent tests; `node src/agent.js`; live task |
| `ch13` | 13 | Scripted offline demo + scorecard | `src/demo.js` | `src/cli.js`, `test/agent.test.js` | `--demo` → 7/7, exit 0; second run recovers |
| `ch14` | 14 | Sessions, trimming, banner, warnings, exit-code mapping, entry guard | — | `src/cli.js`, `test/session.test.js` | Session flow; max-step exits 3; no-TTY exits 2 |
| `ch15` | 15 | Full offline test suite | remaining `test/*.test.js` | existing tests | `npm test` fully offline |
| `ch16` | 16 | Docs + final acceptance; project README | `README.md`, `demo_prompt.md` | `CHAPTER.md` | Twenty acceptance checks; `--help`/`--hooks`/`--memory`/`--demo` |

### Stage boundaries that must not leak

- `ch00`–`ch02`: no `cli.js`. Chat starts at `ch03`.
- `ch03`–`ch05`: no tools. Model talks, cannot act.
- `ch06`: path policy only, no tool calls.
- `ch07`: read-only tools; no writes.
- `ch08`: writes; `ch09`: shell; `ch10`: memory; `ch11`: hooks.
- `ch12`: loop moves into `agent.js`; earlier chapters keep it in `cli.js`.
- `ch13`: demo only — does not add sessions.
- `ch14`: final CLI shape.
- `ch15`: tests only, no product features.
- `ch16`: docs only, no runtime features.

---

## Required chapter layout

```text
chNN/
  package.json
  package-lock.json          # generated, reproducible install
  .gitignore
  CHAPTER.md                 # every chapter
  README.md                  # ch16 only
  src/                       # only modules that exist at this stage
  test/                      # only suites that exist at this stage
  workspace/.gitkeep         # always; generated contents ignored
```

Rules:

- **No `node_modules/`.** Reader runs `npm install`.
- **No per-chapter `.env` / `.env.example`.** One shared, git-ignored `.env` at
  the repository root; `config.js` walks up to find it. Distributed placeholder
  only (`OPENROUTER_API_KEY=sk-or-...`), never a real key.
- **No generated artifacts** from `workspace/`, memory writes, demo output, PDFs.
- **No later-stage modules or tests.**
- **Tests match the stage**; every test present must pass.
- `package.json` keeps the name `mini-coding-js` in every chapter.
- `CHAPTER.md` is the chapter README for `ch00`–`ch15`; `ch16` also gets the
  project `README.md` and must not overwrite `CHAPTER.md`.

### `CHAPTER.md` minimum template

```markdown
# Chapter 0 — Stage 0: Scaffold

**Book:** Stage 0, "Scaffold"
**Plan:** Stage 0
**Goal:** A flat project with one runtime dependency and one writable folder.

## What changed
- Created package.json, .gitignore, workspace/.gitkeep and src/.gitkeep.

## Run it
```bash
npm install
npm ls --depth=0
node --test
```

## It works when
- [ ] npm install installs only chalk.
- [ ] node --test reports 0 tests without failing.
- [ ] workspace/ is ignored except .gitkeep.

## Stage limits
- No UI, model client or CLI yet.

## Read next
- Book: `mini-js-coding-harness.md` Stage 0
- Theory: `mini-js-coding-harness.md` Stage 0
- Contract: `plan.md` Stage 0
```

The acceptance boxes must match the book's "Prove it" section. Use
"If it goes wrong" content for troubleshooting notes. Do not paste theory into
`CHAPTER.md`; link it.

---

## Generation workflow

1. Create `ch00` from the Stage 0 contract. Verify.
2. Copy `ch00` to `ch01`; apply **only** Stage 1 changes. Verify.
3. Repeat one chapter at a time: copy previous chapter → apply next stage → run
   stage acceptance → write `CHAPTER.md` → freeze folder.
4. Checklist per stage: plan's "Files to create", "Files to modify",
   "Acceptance criteria"; book's "Run the incremental stage" commands.
5. Keep one `DEVIATIONS.md` for every difference from `plan.md` or the
   reference (the canonical copy for this skill is in `references/`).
6. Never add a later stage "helpfully". Add a seam only when its stage arrives.
7. Optionally tag commits `chapter-00` … `chapter-16`; the folder is the
   deliverable, the tag is convenience.

### Use `references/chapter_project_requirements.md` for

- the exact per-stage "Added / Modified / Stage proof" table
- mapping from plan/book sections to code
- definitions of done
- known decisions

---

## Verification (every chapter)

Run from inside the chapter folder:

```bash
npm install
npm test
```

Then run the chapter-specific commands in `CHAPTER.md`. Requirements:

- All tests pass **offline**, with no API key.
- No test makes a real network call.
- `CHAPTER.md` acceptance boxes match the book's "Prove it".
- The chapter does not import modules that do not exist in it.
- The folder installs on a fresh machine with `npm install`.
- Live-mode checks are documented, never part of offline CI.

---

## Intentional deviations (must stay true)

These are decided. Do not "fix" them back without updating `references/DEVIATIONS.md`.

1. **`delete_file` is included.** `ch08`–`ch16` expose **nine** tools:
   `list_files`, `read_file`, `create_file`, `write_file`, `edit_file`,
   `delete_file`, `run_command`, `remember`, `recall`. Book/README/stage text
   says "nine tools". A future removal must change every chapter, never keep both
   counts.
2. **One shared `.env` at repository root.** No chapter carries its own.
3. **`package-lock.json` included** in every chapter; generated from `chalk`.
4. **No `node_modules/`** in chapters.
5. **`CHAPTER.md` only**, except `ch16`, which also has `README.md`.
6. **Shell scanning is best-effort.** The `run_command` write-target scan and
   deny-list are heuristics. The sandbox is not a container; this is a deliberate
   teaching choice stated in the book.
7. **Tests are offline.** No network, no API key. Live checks are manual.
8. **Numbering/location.** `chNN` = Stage `NN`, all at repository root.

---

## Definition of done for the set

- `ch00`–`ch16` exist (17 chapters), each standalone.
- `npm install` and `npm test` work offline for every chapter.
- Every chapter has `CHAPTER.md` with goal, changes, run commands, acceptance
  boxes, stage limits, links; `ch16` also has `README.md`.
- Shared root `.env` (placeholder, git-ignored); no chapter-local env files.
- No chapter contains a later stage's module or test.
- `ch16` passes the book's twenty acceptance checks.
- `references/DEVIATIONS.md` records every intentional difference.
- A reader can follow the book's stage instructions using the matching chapter.
