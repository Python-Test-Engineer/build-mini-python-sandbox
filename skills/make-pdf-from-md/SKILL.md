---
name: make-pdf-from-md
description: Convert a Markdown article, explainer, lesson, report, or long document into a print-ready PDF with a generated Contents page, real page numbers, and two-level PDF bookmarks. Use when asked to "convert this Markdown to PDF", "make a PDF from this .md file", "add a contents page and bookmarks to my Markdown PDF", or after editing an existing Markdown source that must be re-exported to PDF.
---

# Make PDF from Markdown

Turn a Markdown document into a polished A4 PDF. The script converts Markdown to HTML, applies the bundled book-style print stylesheet, renders it with headless Chrome or Edge, then adds the two things a long PDF needs:

1. A **printed Contents page** with real page numbers.
2. A **two-level PDF outline** in the viewer's left pane: chapters at the top level, sections nested under them.

The Markdown source is never modified. Edit the `.md`, rerun the script, and the PDF is rebuilt.

## What the output contains

- A4 PDF with a warm, book-like print style: serif headings, dark code blocks, compact tables, callouts.
- A print-only **Contents** page generated from the document's `h2` chapters, with dotted leaders and page numbers filled in by a second render pass.
- PDF bookmarks for the document title, Contents, each `h2` chapter, and each `h3` section nested under its chapter.
- `/PageMode /UseOutlines`, so viewers open with the bookmark pane visible.
- Page numbers at the foot of every page except page 1.
- No browser headers, footers, file URLs, or dates.

## Requirements

- Python 3.10+
- `markdown` and `pypdf`
- Google Chrome or Microsoft Edge

Install the Python dependencies once:

```bash
python -m pip install markdown pypdf
```

If the browser is not found automatically, pass `--browser` or set `CHROME_PATH`.

## Quick start

From this skill directory:

```bash
python scripts/make_pdf.py path/to/article.md
```

The output defaults to the same filename with `.pdf`:

```text
path/to/article.pdf
```

Explicit output path:

```bash
python scripts/make_pdf.py input.md output.pdf
```

Useful options:

```bash
python scripts/make_pdf.py input.md --no-toc          # no printed Contents page
python scripts/make_pdf.py input.md --no-outline      # no PDF bookmarks
python scripts/make_pdf.py input.md --keep-html build/preview.html
python scripts/make_pdf.py input.md --title "My title"
python scripts/make_pdf.py input.md --browser "C:\Program Files\Google\Chrome\Application\chrome.exe"
```

Run `python scripts/make_pdf.py --help` for the full list.

## Markdown conventions

The converter handles normal Markdown, including tables, fenced code blocks, blockquotes, ordered and unordered lists, inline code, links, and horizontal rules. A few conventions produce the best result:

- Start with one `#` title.
- Use `##` for chapters. Each chapter starts on a new page.
- Use `###` for sections inside a chapter. These become nested bookmarks.
- Put the italic kicker on its own line before the H1:
  ```markdown
  *Explainer · the loop, the tools, the sandbox, the hooks*

  # How a coding agent actually works
  ```
- Put the standfirst in the first paragraph after the H1. It is styled as the lede.
- Use a fenced code block with a language tag for code and terminal output:
  ````markdown
  ```javascript
  console.log('hello');
  ```
  ````
- A bold caption line immediately before a code fence is styled as a code label:
  ````markdown
  **src/agent.js** · *javascript*

  ```javascript
  ...
  ```
  ````
- Use blockquotes for callouts:
  ```markdown
  > **The honest limit.** This is not a security boundary.
  ```
- Use pipe tables for tabular material. Wrap long cell text normally; the print CSS handles the layout.

Do not add a manual Contents section. The script generates one from the `h2` headings. If the source already contains a `nav.print-toc` or `nav.pdf-toc` block, the script removes it before injecting its own. It also removes an authored Markdown section headed `Table of contents` or `Contents` when it contains at least three anchor-link list items. This prevents the common duplicate-TOC result: a generated printed Contents page plus the document's own hand-written contents list. The generated Contents page is kept; the authored section is dropped only for the PDF render, never from the Markdown file on disk. If you pass `--no-toc`, the authored section is left in place because there is no generated Contents page to duplicate.

## How it works

1. Read the Markdown source.
2. If a printed Contents page will be generated, remove an authored Markdown `Table of contents`/`Contents` section when it is followed by anchor-link list items. This keeps the generated page as the only contents list.
3. Convert the cleaned Markdown to HTML with Python-Markdown (`extra`, `sane_lists`, `toc` extensions).
4. Wrap the HTML in `assets/print.css` and add light structural classes (eyebrow, lede, code caption, callout).
5. Remove any previous print Contents block and inject a new `nav.pdf-toc` after the title block and before the first `h2`.
6. Render pass 1 with placeholder page numbers.
7. Read the PDF with `pypdf`, locate each `h2` heading's page, and replace the placeholders with the real page numbers.
8. Render pass 2.
9. Build the PDF outline (title, Contents, chapters, nested sections), set `/PageMode /UseOutlines`, and write the final PDF.
10. Delete temporary files unless `--keep-html` was requested.

The printed Contents page uses a marker sentence: *Page numbers refer to the folio at the foot of each page.* The script uses it to find and skip the Contents page when locating chapter headings.

## Quality checks

After generating, verify the page count, page mode, and outline:

```bash
python - <<'PY'
from pypdf import PdfReader
r = PdfReader("output.pdf")
print("pages:", len(r.pages))
print("mode:", r.trailer["/Root"].get("/PageMode"))
def walk(items, depth=0):
    for item in items:
        if isinstance(item, list):
            walk(item, depth + 1)
        else:
            print("  " * depth, item.title, "->", r.get_destination_page_number(item) + 1)
walk(r.outline)
PY
```

Also check the Contents page and the first chapter:

```bash
pdftotext -f 2 -l 3 -layout output.pdf -
```

The Contents page numbers must match where each chapter actually starts. If a heading cannot be found, the script fails with the heading text rather than silently producing a wrong index.

## Troubleshooting

- **Browser not found:** pass `--browser` or set `CHROME_PATH`.
- **`markdown` or `pypdf` missing:** run `python -m pip install markdown pypdf`.
- **Heading not found:** make sure it is real visible `h2` text, not an image, and that it is not inside `script`, `style`, `aside`, or a pre-existing print Contents block.
- **Two contents lists in the PDF:** remove the authored Markdown `Table of contents` section, or let the script remove it automatically. The script drops a `Table of contents`/`Contents` heading followed by at least three anchor-link list items when a generated Contents page is enabled.
- **Blank page after Contents:** avoid adding both `break-before: page` and `break-after: page` around the generated Contents page. The bundled CSS uses `break-before` on the Contents page and `break-before` on `h2` chapters; the two collapse into one break.
- **Code or table overflows the page:** keep `white-space: pre-wrap` and `overflow-wrap: anywhere` on `pre` (already in `assets/print.css`). Very wide tables may need fewer columns or shorter prose.
- **Wrong page numbers:** confirm the Contents marker text is present and not edited. The script uses it to find the Contents page.
- **Custom styling:** edit `assets/print.css`. The script reads it on every run, so no reinstall is needed.

## Lessons baked into the script

- Do not use Chrome's default header/footer; it duplicates page numbers and adds the file URL.
- Do not try to read page numbers from the Markdown or HTML. Render once, read the PDF, then render again.
- Use `pypdf` after rendering; Chrome does not emit a useful PDF outline.
- Set `/PageMode /UseOutlines` explicitly. Adding bookmarks alone does not make every viewer open the left pane.
- Keep chapters at the top outline level and `h3` sections nested. Do not flatten the tree.
- Keep the Markdown source as the single editable source of truth; never hand-edit the generated HTML.
- Generate one contents list, not two. If the Markdown already has an authored TOC and the converter generates a printed Contents page, remove the authored section during conversion rather than shipping both.
