---
name: make-explainer-template
description: Scaffold, write, and build a staged explainer book project from a topic and an implementation language. Use when creating a new chapter-based educational build-along, extending a book with chapters, or rebuilding book and chapter pages to the house-styled Markdown, HTML, and PDF format with a prominent educational-use disclaimer.
---

# Make Explainer Template

Create a complete build-along explainer project from two inputs: a **topic** and an **implementation language** (`python` or `javascript`). The result follows the existing house format:

- one runnable checkpoint per chapter (`ch00/`, `ch01/`, …),
- a chapter run sheet (`chNN/CHAPTER.md`),
- an explainer book (`book/BOOK.md`),
- a styled single-file HTML edition (`book/BOOK.html`),
- a print-ready PDF (`book/BOOK.pdf`),
- the same web styling as the existing explainer pages (`assets/book.css`).

Every generated document starts with a prominent **educational purposes only / not production grade** disclaimer. The HTML build also injects the disclaimer into the page header.

## Inputs

Ask for or infer:

| Input | Required | Notes |
|---|---|---|
| topic | yes | What the book teaches, e.g. "a small coding agent" or "a Python data pipeline". |
| language | yes | Only `python` or `javascript` (aliases `py`, `js`, `node` are accepted). |
| output directory | yes | Where the new project should be created. |
| title | no | Default: `Build a Mini <topic> in <Language>`. |
| chapter count | no | Default: 12. Creates `ch00` … `chNN-1`. |
| stage titles | no | Comma-separated list. Overrides chapter count. |
| author | no | Default: `Your Name`. |

If the user supplies a topic that does not fit the default software-build arc, pass a custom `--stages` list instead of forcing the default stage names.

## Workflow

### 1. Scaffold the project

Run the scaffold from this skill directory. Paths are relative to the skill directory.

```bash
node scripts/scaffold.mjs \
  --out /absolute/path/to/new-book \
  --topic "a small coding agent" \
  --language python \
  --title "Build a Mini Coding Agent in Python" \
  --author "Author Name" \
  --chapters 12
```

Or provide an explicit structure:

```bash
node scripts/scaffold.mjs \
  --out ./my-book \
  --topic "a small coding agent" \
  --language javascript \
  --stages "Project setup,Configuration,Model client,First loop,Memory,Tests,Docs"
```

Use `--force` only when the user explicitly wants to overwrite or fill an existing scaffold.

### 2. Replace the placeholders

The scaffold creates a runnable skeleton with placeholders. Do not stop there. Fill the project with real teaching content:

- Rewrite `plan.md` stage contracts for the actual topic.
- Rewrite each `chNN/CHAPTER.md` run sheet.
- Write the full chapter text in `book/BOOK.md`.
- Add the chapter's runnable source and offline checks in `chNN/src/` and `chNN/test/`.
- Keep the generated `assets/book.css` unchanged unless the user asks for a design change.

Use `references/FORMAT.md` for the exact document shapes and `references/WRITING.md` for the house voice and chapter checklist.

### 2a. Keep the educational disclaimer

The disclaimer **must** remain at the beginning of:

- `README.md`
- `plan.md`
- `book/BOOK.md`
- every `chNN/CHAPTER.md`

The generator also injects a visible disclaimer block at the top of every HTML page. Do not remove it, water it down, or move it to the end. It must say this is for educational purposes only and not a production-grade system.

### 3. Build Markdown, HTML, and PDF

From the new project root:

```bash
node scripts/build.mjs              # book + every chapter
node scripts/build.mjs --no-pdf     # fast HTML-only iteration
node scripts/build.mjs --book-only  # book only
```

The builder uses the copied house stylesheet and produces:

```text
book/BOOK.html
book/BOOK.pdf
ch00/CHAPTER.html
ch00/CHAPTER.pdf
ch01/CHAPTER.html
ch01/CHAPTER.pdf
...
```

PDF generation uses a local Chrome or Edge install. If no browser is found, set `CHROME_PATH` or run with `--no-pdf` while drafting; do not declare the build complete until the PDF has been produced or the user accepts an HTML-only deliverable.

### 4. Verify

Before reporting completion:

- [ ] `book/BOOK.md`, `book/BOOK.html`, and `book/BOOK.pdf` all exist and are non-empty.
- [ ] Each `chNN/CHAPTER.md`, `chNN/CHAPTER.html`, and `chNN/CHAPTER.pdf` exists.
- [ ] The HTML opens with no server and uses the house stylesheet.
- [ ] The disclaimer is the first prominent block in every Markdown document and appears at the top of the HTML page.
- [ ] Code blocks, tables, callouts, and sidebar contents render correctly.
- [ ] The chapter code runs from a clean checkout, or the chapter explicitly says what is intentionally incomplete.
- [ ] No document claims the result is production-grade.

Useful smoke test:

```bash
node scripts/build.mjs --no-pdf
node -e "const fs=require('fs'); for (const f of ['book/BOOK.html','ch00/CHAPTER.html']) { const s=fs.readFileSync(f,'utf8'); if(!s.includes('Educational use only')) throw new Error(f+' missing disclaimer'); }"
```

## House rules

1. **One idea per stage.** Each chapter adds one visible capability and remains runnable on its own.
2. **Runnable checkpoints.** Every chapter has a short run command and observable acceptance criteria.
3. **Honest scope.** State what the teaching code skips: validation, isolation, scale, monitoring, error handling, and production operations.
4. **Same styling.** Use `assets/book.css` and the generated page shell. Do not invent a second design system.
5. **No fabricated evidence.** Do not claim tests pass, PDFs were generated, or features work unless you ran them.
6. **Language fidelity.** Python chapters use Python idioms and tooling; JavaScript chapters use modern Node ESM. Do not mix languages in one book.
7. **No production claims.** The disclaimer is not decoration. Repeat the limitation in the final docs and appendix.

## Language profiles

### Python

- Runtime: Python 3.11+.
- Source: `src/main.py`, modules under `src/`.
- Package marker: `src/__init__.py`.
- Tests: standard-library `unittest`, run with `python -m unittest discover -s test`.
- Dependencies: `requirements.txt`; keep them minimal and explicit.
- Use virtual environments in the README.
- Prefer type hints on public functions and small, testable modules.

### JavaScript

- Runtime: Node.js 20+.
- Module system: ES modules (`"type": "module"`).
- Source: `src/main.js`, modules under `src/`.
- Tests: built-in `node --test`.
- Dependencies: `package.json`; keep runtime dependencies minimal.
- Prefer named exports and explicit dependency injection over hidden global state.

## Files in this skill

| Path | Purpose |
|---|---|
| `scripts/scaffold.mjs` | Creates the project tree, config, chapter folders, source placeholders, and copies the builder and stylesheet. |
| `scripts/build.mjs` | Converts Markdown to house-styled HTML and uses Chrome/Edge for PDF. |
| `assets/book.css` | The house web styling. Copy only; do not fork per project. |
| `templates/` | README, plan, book, and chapter templates with language/topic placeholders. |
| `references/FORMAT.md` | Required document structure and file layout. |
| `references/WRITING.md` | Voice, chapter checklist, and common failure modes. |

## Extending an existing explainer project

If the project already exists:

1. Read `book/BOOK.md`, `plan.md`, and the latest chapter first.
2. Add a new `chNN/` folder with `CHAPTER.md`, source, and tests.
3. Add the chapter to `plan.md` and `book/BOOK.md` in the same order.
4. Run `node scripts/build.mjs` to regenerate all HTML and PDF outputs.
5. Re-check that the disclaimer still appears at the top of every edited document.

Do not regenerate an existing project from the scaffold unless the user asks for a reset; the scaffold is for new books, while the builder is safe to rerun at any time.
