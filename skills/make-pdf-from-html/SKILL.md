---
name: make-pdf-from-html
description: Convert a self-contained HTML explainer, lesson, report, or long article into a print-ready PDF with a print-only contents page and two-level PDF bookmarks. Use when asked to "convert this HTML to PDF", "add a contents page to the PDF", or "add bookmarks/left-pane index to a PDF".
---

# Make PDF from HTML

Turn an HTML document into a polished PDF using headless Chrome or Edge, then add the two things a long PDF needs:

1. A **printed Contents page** with page numbers.
2. A **two-level PDF outline** in the viewer's left pane: chapters at the top level, sections nested under them.

The source HTML is never modified. The script uses a temporary copy.

## What the output contains

- A4 PDF rendered through the document's existing `@media print` styles.
- A print-only **Contents** page with dotted leaders and real page numbers.
- A PDF bookmark tree:
  - document title
  - Contents
  - each `h2` chapter
  - each `h3` section nested under its chapter
- `/PageMode /UseOutlines`, so viewers open with the bookmark pane visible.
- No browser headers or footers.

## Requirements

- Python 3.10+
- `pypdf`
- Google Chrome or Microsoft Edge

Install the Python dependency once:

```bash
python -m pip install pypdf
```

If the browser is not found automatically, pass `--browser` or set `CHROME_PATH`.

## Quick start

From this skill directory:

```bash
python scripts/make_pdf.py path/to/explainer.html
```

The output defaults to the same filename with `.pdf`:

```text
path/to/explainer.pdf
```

Explicit output path:

```bash
python scripts/make_pdf.py input.html output.pdf
```

Useful options:

```bash
python scripts/make_pdf.py input.html --no-toc
python scripts/make_pdf.py input.html --no-outline
python scripts/make_pdf.py input.html --browser "C:\Program Files\Google\Chrome\Application\chrome.exe"
python scripts/make_pdf.py input.html --keep-html build/preview.html
```

Run `python scripts/make_pdf.py --help` for the full list.

## Conventions the HTML should follow

For best results, the page should:

- Use `<h2>` for chapters and `<h3>` for subsections.
- Put chapters in `<section>` elements, ideally with an `id`, so Contents links work.
- Have print CSS that starts chapters on new pages (`section { break-before: page; }`).
- Have a title block before the first section; that becomes page 1.
- Be self-contained: no CDN fonts, remote scripts, or network assets.

The script injects its own print-only Contents styles and markup. It does not depend on the page's screen-side navigation.

## How it works

1. Copy the HTML to a temporary file beside the original, so relative assets still resolve.
2. Remove any previous print Contents block and inject the skill's own `nav.pdf-toc`.
3. Render pass 1 with placeholder page numbers.
4. Read the PDF with `pypdf`, locate each heading's page, and skip the Contents pages.
5. Replace the placeholders with the real page numbers.
6. Render pass 2, then build the PDF outline and set `/UseOutlines`.
7. Delete temporary files unless `--keep-html` was requested.

## Quality checks

After generating, verify:

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

Also check page 2 in a viewer or with `pdftotext -f 2 -l 2 -layout output.pdf -`.

The Contents page numbers must match where each chapter actually starts. If a heading is not found, the script fails with the heading text rather than silently producing a wrong index.

## Troubleshooting

- **Browser not found:** pass `--browser` or set `CHROME_PATH`.
- **`pypdf` missing:** run `python -m pip install pypdf`.
- **Heading not found:** make sure it is real visible text, not an image, and that it is not inside `script`, `style`, `aside`, or a pre-existing print Contents block.
- **Extra Contents page:** the script removes old `nav.print-toc` / `nav.pdf-toc` blocks before injecting. If a page builds its Contents with different markup, remove that block first.
- **Blank pages:** check the page's print CSS. A `break-before: page` on both sides of the Contents block can create a blank sheet.
- **Wrong page numbers:** confirm chapters start on new pages. If a section starts mid-page, the printed number is still the page where the heading appears.

## Lessons baked into the script

- Do not use Chrome's default header/footer; it duplicates page numbers and adds the file URL.
- Do not try to read page numbers from the HTML. Render once, read the PDF, then render again.
- Use `pypdf` after rendering; Chrome does not emit a useful PDF outline.
- Set `/PageMode /UseOutlines` explicitly. Adding bookmarks alone does not make every viewer open the left pane.
- Keep chapters at the top outline level and `h3` sections nested. Do not flatten the tree.
- Preserve the original HTML so the screen version keeps its sidebar and interactive controls.
