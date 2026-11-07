# Project format

This is the house structure produced by `scripts/scaffold.mjs` and consumed by `scripts/build.mjs`.

```text
<project>/
├── README.md                 # Course landing page + prominent disclaimer
├── plan.md                   # Stage contract + prominent disclaimer
├── book.config.json          # Title, language, paths, disclaimer, chapter count
├── .env.example
├── .gitignore
├── assets/
│   └── book.css              # House stylesheet (do not fork per project)
├── book/
│   ├── BOOK.md               # Explainer book + prominent disclaimer
│   ├── BOOK.html             # Generated, single-file
│   └── BOOK.pdf              # Generated, print-ready
├── scripts/
│   └── build.mjs             # Markdown -> HTML -> PDF
└── ch00/ … chNN/
    ├── CHAPTER.md            # Run sheet + prominent disclaimer
    ├── CHAPTER.html          # Generated
    ├── CHAPTER.pdf           # Generated
    ├── .gitignore
    ├── src/
    ├── test/
    └── workspace/
```

## Required document order

### README.md

1. Title.
2. **Disclaimer block** immediately after the title.
3. One-sentence description of the course and language.
4. Repository map.
5. Quick start for the implementation language.
6. How to build the book.
7. Configuration notes.
8. Author.
9. Closing reminder that the project is educational only.

### plan.md

1. Title (`# Build Plan: <slug>`).
2. **Disclaimer block** immediately after the title.
3. Goal, method, and why.
4. How to use the plan.
5. Full architecture (end state).
6. Stage map table.
7. One stage contract per chapter.
8. Final checklist.
9. Closing reminder that the project is educational only.

A stage contract contains:

- stage number and title,
- what the reader will learn,
- files to create or modify,
- acceptance criteria as checkboxes.

### book/BOOK.md

1. Book title.
2. **Disclaimer block** immediately after the title.
3. About this book.
4. Who it is for.
5. How to use it.
6. The educational contract.
7. One `# Chapter N — Stage N: Title` section per chapter. The folder
   `chNN/` and `Stage NN` always use the same number: `ch00` is Stage 0,
   `ch01` is Stage 1, and so on.
8. Appendix: study and review.
9. Closing reminder.

Each chapter section should contain:

- a warning callout repeating the educational limit,
- what the chapter builds,
- why it matters,
- the build walkthrough,
- acceptance criteria,
- what to notice,
- limits and production notes,
- read-next links.

### chNN/CHAPTER.md

1. `# Chapter N — Stage N: Title`. The folder number and stage number are
   identical (`chNN/` = Stage NN).
2. **Disclaimer block** immediately after the title.
3. Book/plan/goal metadata.
4. What you will build.
5. What changed.
6. Key concepts.
7. Files to create or modify.
8. Build/run command.
9. Acceptance criteria.
10. If it goes wrong.
11. Read next.

## Markdown features supported by the builder

The builder is dependency-free and deliberately supports the subset used by the house books:

- headings (`#` … `######`),
- paragraphs with hard breaks (two trailing spaces),
- fenced code blocks with an optional language,
- ordered and unordered lists, including nested lists,
- pipe tables,
- horizontal rules,
- blockquotes,
- GitHub-style warning callouts: `> [!WARNING]`, `> [!NOTE]`, `> [!TIP]`, `> [!IMPORTANT]`, `> [!CAUTION]`,
- inline code, bold, italic, strikethrough, links, images, and bare URLs,
- raw block HTML (for anchors and advanced embeds).

Heading levels are shifted down for styling:

| Markdown | Page output | Sidebar |
|---|---|---|
| `#` | `<h2>` inside a `<section>` | level 2 |
| `##` | `<h3>` | level 3 |
| `###` | `<h4>` | level 4 |
| `####` | `<h5>` | not listed |

Use `#` for chapters or major parts. Use `##` for subsections. Do not start documents with `##` only; start with a single `#` heading so the sidebar and section IDs stay coherent.

## Stylesheet contract

`assets/book.css` defines the page palette, typography, sidebar, code blocks, callouts, tables, print rules, and disclaimer styling. The builder copies it into every generated HTML page. Do not replace it per project unless the user specifically asks for a new visual design.

The generated page shell provides:

- the sticky sidebar and table of contents,
- the reading-progress bar,
- the scroll-spy active section,
- the circular `Aa` light/dark theme toggle,
- the top-of-page disclaimer block,
- the colophon.

## PDF contract

PDF is produced by headless Chrome or Edge using the stylesheet's `@media print` rules. The print stylesheet hides the sidebar, theme button, and progress bar, and forces a white background. If PDF generation fails, install Chrome/Edge or set `CHROME_PATH`; do not silently ship only HTML unless the user agrees.
