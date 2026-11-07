# Chapter project requirements

**Status:** implemented. `ch00` through `ch16` exist as standalone snapshots; every chapter installs and passes `npm test` offline. See `DEVIATIONS.md` for the intentional decisions.

This document defines how the book's stage chapters map to runnable code projects under the repository root. It is the contract for the later generation work, so each chapter is consistent, runnable, and recognisably the result of implementing one stage of `plan.md`.

---

## 1. Purpose

The book needs supporting code that a reader can run at the end of every stage. Each chapter is a **snapshot project**: the complete, runnable state of the harness after that stage has been implemented, with no later-stage features present.

A reader should be able to open `ch07/`, run the stage's commands, and see exactly what the book says they should see. They should not have to subtract later code mentally.

---

## 2. Chapter numbering and folder names

The chapter suffix is the plan stage number. `ch00` is Stage 0, `ch01` is Stage 1, and so on through `ch16` for Stage 16.

| Folder | Stage |
|---|---|
| `ch00/` | Stage 0 — Scaffold |
| `ch01/` | Stage 1 — Terminal language |
| `ch02/` | Stage 2 — Config and model client |
| `ch03/` | Stage 3 — Simplest chat loop |
| `ch04/` | Stage 4 — Conversation history |
| `ch05/` | Stage 5 — System prompt |
| `ch06/` | Stage 6 — Path policy |
| `ch07/` | Stage 7 — Read-only tools |
| `ch08/` | Stage 8 — Sandbox and write tools |
| `ch09/` | Stage 9 — Command execution |
| `ch10/` | Stage 10 — Long-term memory |
| `ch11/` | Stage 11 — Lifecycle hooks |
| `ch12/` | Stage 12 — The ReAct loop |
| `ch13/` | Stage 13 — Offline demo |
| `ch14/` | Stage 14 — Sessions and CLI polish |
| `ch15/` | Stage 15 — Full test suite |
| `ch16/` | Stage 16 — Documentation and acceptance |

Every chapter is a complete, standalone project. The chapter folder is the project root.

---

## 3. Source order of truth

When generating and checking a chapter, use this order:

1. **`plan.md` — the stage contract.** It defines what exists at that stage, the API surface, defaults and acceptance criteria. This is authoritative for *what the stage contains*.
2. **`mini-js-coding-harness.md` — the reader-facing chapter.** It defines the commands, expected output, checkpoints and narrative. This is authoritative for *how the reader proves the stage*.
3. **`mini-coding-agent-js/` — the finished reference.** It defines implementation details that the plan leaves open. It is not copied wholesale; later-stage features must not leak backwards.

If the plan and the book disagree, follow the plan for feature scope and record the difference in the chapter's `CHAPTER.md`. If the plan and the finished reference disagree (for example, the extra `delete_file` tool), resolve it explicitly and record it in a shared `DEVIATIONS.md` rather than silently choosing one.

---

## 4. What every chapter folder contains

Each `chNN/` is a complete, standalone Node project:

```text
chNN/
  package.json
  package-lock.json          (recommended: reproducible install)
  .gitignore
  CHAPTER.md                 (book-facing metadata and run sheet)
  README.md                  (only in ch16, the final chapter)
  src/                       only the modules that exist at this stage
  test/                      only the suites that exist at this stage
  workspace/.gitkeep         always present; generated contents ignored
```

Rules:

- **No `node_modules/`.** A reader runs `npm install`.
- **One shared `.env` lives at the repository root**; chapters do not carry their own `.env` or `.env.example`. `config.js` walks up from the chapter root to find it. The shared file is git-ignored and the distributed copy contains only a placeholder such as `OPENROUTER_API_KEY=sk-or-...`, never a real key.
- **No generated artifacts** from `workspace/`, memory writes, demo output or PDFs.
- **No later-stage modules.** If `memory.js` is not introduced until Stage 10, it must not exist in `ch09`.
- **Tests match the stage.** A chapter may have fewer tests than a later chapter, but all tests present must pass.
- **`CHAPTER.md` is the chapter's own README.** `README.md` appears only in the final chapter (`ch16`) because the project README is itself a Stage 16 deliverable. Earlier chapters use `CHAPTER.md` only, so a later stage cannot overwrite the chapter metadata.
- `package.json` keeps the same project name (`mini-coding-js`) in every chapter. The folder identifies the chapter; the package identity stays stable.

### `CHAPTER.md` minimum contents

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

---

## 5. Per-chapter project state

This is the expected file/feature state after each stage. "Added" means new files. "Modified" means files carried forward with stage changes.

| Chapter | Stage | Project state after this chapter | Added | Modified | Stage proof |
|---|---|---|---|---|---|
| `ch00` | 0 | Flat scaffold; one dependency; no runnable CLI | `package.json`, `.gitignore`, `src/.gitkeep`, `workspace/.gitkeep` | — | `npm install`; `npm ls --depth=0`; `node --test` (0 tests) |
| `ch01` | 1 | Terminal output helpers; returns strings only | `src/ui.js`, `test/ui.test.js` | — | `node --test test/ui.test.js`; one-liner imports `ui.js` |
| `ch02` | 2 | Config with provenance; one OpenRouter POST; no CLI | `src/config.js`, `src/llm.js`, `test/config.test.js`, `test/llm.test.js` | — | `node --test test/config.test.js test/llm.test.js` |
| `ch03` | 3 | First runnable chatbot; one task, one reply; no tools | `src/cli.js` (minimal), `test/input.test.js` | — | `node src/cli.js --help`; live `node src/cli.js "Say hello"`; non-TTY exits 2 |
| `ch04` | 4 | Interactive session; `messages` array; `/new`, `/quit`, `/exit` | — | `src/cli.js` | Live multi-turn session; `/new`; session summary |
| `ch05` | 5 | System prompt module; rules injected; no tools | `src/prompt.js`, `test/prompt.test.js` | `src/cli.js` | `node --test test/prompt.test.js`; live prompt question |
| `ch06` | 6 | Path policy; reads open, writes fenced; no tools yet | `src/workspace.js`, `test/workspace.test.js` | — | `node --test test/workspace.test.js` |
| `ch07` | 7 | Read-only tools and manual tool loop in `cli.js` | `src/tools.js` (partial), `test/tools.test.js` | `src/prompt.js`, `src/cli.js` | Live list/read task; `node --test test/tools.test.js` |
| `ch08` | 8 | Sandbox plus create/write/edit tools | `src/sandbox.js`, `test/sandbox.test.js` | `src/tools.js`, `src/cli.js` | Live create/edit task; escape write refused; sandbox tests |
| `ch09` | 9 | `run_command` with tokeniser, write scan, deny-list, policy, safe env | `test/shell-sandbox.test.js` | `src/sandbox.js`, `src/tools.js`, `src/cli.js` | Live command; `CMD_POLICY=deny`; Desktop-copy refusal |
| `ch10` | 10 | File-backed memory; digest injection; `remember`/`recall`; side doors | `src/memory.js`, `src/memory.md`, `test/memory.test.js` | `src/prompt.js`, `src/tools.js`, `src/cli.js` | `node src/cli.js --memory`; remember then recall across runs |
| `ch11` | 11 | Nine lifecycle hooks; catalogue, trace, deciding hooks | `src/hooks.js`, `test/hooks.test.js` | `src/cli.js` | `node src/cli.js --hooks`; `--no-hooks`; hooks tests |
| `ch12` | 12 | ReAct loop extracted to library; heartbeat; step limit; truncation guard | `src/agent.js`, `src/heartbeat.js`, `test/agent.test.js` | `src/cli.js` | `node --test test/agent.test.js`; `node src/agent.js` hint; live task |
| `ch13` | 13 | Scripted offline demo and scorecard | `src/demo.js` | `src/cli.js`, `test/agent.test.js` | `node src/cli.js --demo` → 7/7, exit 0; second run recovers |
| `ch14` | 14 | Sessions, history trimming, banner, warnings, exit-code mapping, entry guard | — | `src/cli.js`, `test/session.test.js` | Session flow; max-step task exits 3; no-TTY exits 2 |
| `ch15` | 15 | Full offline test suite across all modules | Remaining `test/*.test.js` completions | Existing test files | `npm test` fully offline |
| `ch16` | 16 | Documentation and final acceptance; project README in addition to `CHAPTER.md` | `README.md`, `demo_prompt.md` | `CHAPTER.md` (stage links) | Final acceptance checks; `--help`, `--hooks`, `--memory`, `--demo` |

### Deliberate stage boundaries

- `ch00`–`ch02` have no `cli.js`. A reader cannot chat until `ch03`.
- `ch03`–`ch05` have no tools. The model can talk, but not act.
- `ch06` has a path policy but no tool calls. It is a library-only stage.
- `ch07` has read-only tools. Writes do not exist yet.
- `ch08` introduces writes; `ch09` introduces shell execution; `ch10` introduces memory; `ch11` introduces hooks.
- `ch12` is the first chapter where the loop lives in `agent.js`; earlier chapters keep the manual loop in `cli.js`.
- `ch13` adds only the demo; it does not add sessions.
- `ch14` is the final CLI shape.
- `ch15` does not add product features; it hardens tests.
- `ch16` does not add runtime features; it documents and proves.

---

## 6. How the chapter code should be produced later

This is the generation workflow, not part of the current step.

1. Create `ch00` from the Stage 0 contract. Verify it.
2. Copy `ch00` to `ch01`, then apply **only** Stage 1's changes. Verify.
3. Continue one chapter at a time: copy the previous chapter, apply the next stage, run the stage's acceptance checks, write `CHAPTER.md`, freeze the folder.
4. For each stage, use the plan's "Files to create", "Files to modify" and "Acceptance criteria" as the checklist. Use the book stage's "Run the incremental stage" block as the command list.
5. Keep a single `DEVIATIONS.md` at the repository root level recording any place the generated chapter differs from `plan.md` or `mini-coding-agent-js`.
6. Do not "helpfully" add later-stage code to an earlier chapter. If a later stage needs a seam, add the seam only when that stage is reached.
7. Optionally tag or commit each chapter in git (`chapter-00` … `chapter-16`) so each snapshot is reproducible. The folder is the deliverable; the tag is convenience.

### Verification for every chapter

Run from inside the chapter folder:

```bash
npm install
npm test
```

Then run the chapter-specific commands in `CHAPTER.md`. Requirements:

- All tests pass offline, with no API key.
- No test makes a real network call.
- The chapter's `CHAPTER.md` acceptance boxes match the book's "Prove it" section for that stage.
- The chapter's code does not import modules that do not exist in that chapter.
- The chapter can be copied to a fresh machine and installed with `npm install`.
- Live-mode checks are documented but are not part of the offline CI proof.

---

## 7. Mapping from plan/book sections to project code

The mapping is one stage to one chapter, but the relationship is more specific than that:

| Book section | Code representation |
|---|---|
| `Book Stage N — title` / `Plan Stage N` | One `chNN` project snapshot |
| `Plan` bullets | Ordered implementation checklist for that chapter |
| `Build` files | Files added or modified in that chapter |
| `Run the incremental stage` | Commands in `CHAPTER.md` and verification script |
| `Prove it` | `CHAPTER.md` acceptance checkboxes and test assertions |
| `If it goes wrong` | `CHAPTER.md` troubleshooting notes |
| `Checkpoint` | Not code; links only to the book and manual |
| Theory in `mini-js-coding-harness.md` | Not copied into code comments; linked from `CHAPTER.md` |
| Final `README.md` | Only exists in `ch16`; every chapter, including `ch16`, also has `CHAPTER.md` |

The code should be *the result*, not a second copy of the book. Prose belongs in `CHAPTER.md`; code comments should explain non-obvious implementation choices only.

---

## 8. Known decisions and open questions

These need a decision before generation. Recommended defaults are given.

1. **Naming.** Resolved: `ch00` = Stage 0 through `ch16` = Stage 16.
2. **Standalone project or source-only chapter.** Recommended: standalone project. A reader can `cd chNN && npm install && npm test`.
3. **`delete_file` at Stage 8.** Resolved: follow `plan.md` and expose nine tools from `ch08` onward, including `delete_file`. Recorded in `DEVIATIONS.md`.
4. **`.env` placement.** Resolved: one shared `.env` lives at the repository root; chapters do not carry their own. It is git-ignored and contains only a placeholder unless the reader adds their own key locally.
5. **`package-lock.json` in every chapter.** Recommended: yes, for reproducible installs. It is generated, not hand-written.
6. **Chapter metadata filename.** Resolved: `CHAPTER.md` in every chapter. The final chapter also has the project `README.md`.
7. **Stage 16 README source.** Resolved: `ch16/README.md` is the final project README and reflects the chapter's actual nine-tool behaviour.
8. **Live checks in CI.** Recommended: never. Live checks are manual; offline tests and `--demo` are the automated gate.
9. **Comments and prose.** Recommended: keep code comments minimal; put explanations in `CHAPTER.md` and the book. Do not duplicate the book in source comments.

---

## 9. Definition of done for the chapter set

The chapter set is complete when:

- `ch00` through `ch16` exist (17 chapters).
- Each chapter is standalone, installs with `npm install`, and passes `npm test` offline.
- Each chapter has a `CHAPTER.md` with goal, changes, run commands, acceptance boxes, stage limits and links. The final chapter also has `README.md`.
- A shared `.env` lives at the repository root (placeholder only, git-ignored); no chapter carries its own `.env` or `.env.example`.
- No chapter contains a later stage's module or test.
- The final chapter passes the book's twenty acceptance checks.
- `DEVIATIONS.md` records every intentional difference from `plan.md` and the finished reference.
- The book's stage instructions can be followed using the matching chapter as the reference implementation.
