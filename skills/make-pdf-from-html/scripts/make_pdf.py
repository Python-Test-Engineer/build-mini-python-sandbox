#!/usr/bin/env python3
"""Render a self-contained HTML document to PDF, with a printed contents page
and a two-level PDF outline (chapters and sections).

Usage:
    python make_pdf.py input.html [output.pdf]
"""

from __future__ import annotations

import argparse
import html as html_lib
import itertools
import os
import re
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path

try:
    from pypdf import PdfReader, PdfWriter
    from pypdf.generic import NameObject
except ImportError:
    sys.exit("Missing dependency: pypdf. Install it with: python -m pip install pypdf")


VOID_TAGS = {
    "area", "base", "br", "col", "embed", "hr", "img", "input", "link",
    "meta", "param", "source", "track", "wbr",
}

TOC_MARKER = "Page numbers refer to the folio at the foot of each page."


@dataclass
class Heading:
    level: int
    text: str
    anchor: str | None
    page: int | None = None


class HeadingParser(HTMLParser):
    """Collect visible h2/h3 headings, skipping app chrome and print TOCs."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.headings: list[Heading] = []
        self.stack: list[tuple[str, bool, bool]] = []
        self.sections: list[str | None] = []
        self.skip_depth = 0
        self.capture: dict | None = None

    def handle_starttag(self, tag: str, attrs) -> None:
        attrs = dict(attrs)
        if tag in VOID_TAGS:
            if self.capture is not None:
                self.capture["parts"].append(" ")
            return

        if tag == "section":
            self.sections.append(attrs.get("id"))

        classes = set((attrs.get("class") or "").split())
        skip = (
            tag in {"script", "style", "aside"}
            or "print-toc" in classes
            or "pdf-toc" in classes
            or attrs.get("id") in {"stylepanel", "stylebtn"}
        )

        if self.skip_depth:
            self.stack.append((tag, False, False))
        elif skip:
            self.stack.append((tag, True, False))
            self.skip_depth += 1
        else:
            self.stack.append((tag, False, False))
            if tag in {"h2", "h3"}:
                anchor = attrs.get("id") or (self.sections[-1] if self.sections else None)
                self.capture = {"tag": tag, "parts": [], "anchor": anchor}
                self.stack[-1] = (tag, False, True)

        if self.capture is not None:
            self.capture["parts"].append(" ")

    def handle_startendtag(self, tag: str, attrs) -> None:
        if self.capture is not None:
            self.capture["parts"].append(" ")

    def handle_endtag(self, tag: str) -> None:
        if tag in VOID_TAGS:
            return
        if self.capture is not None:
            if tag == self.capture["tag"]:
                text = re.sub(r"\s+", " ", "".join(self.capture["parts"])).strip()
                if text:
                    self.headings.append(
                        Heading(int(tag[1]), text, self.capture["anchor"])
                    )
                self.capture = None
            else:
                self.capture["parts"].append(" ")

        if tag == "section" and self.sections:
            self.sections.pop()

        while self.stack:
            opened, was_skip, _ = self.stack.pop()
            if was_skip:
                self.skip_depth -= 1
            if opened == tag:
                break

    def handle_data(self, data: str) -> None:
        if self.capture is not None:
            self.capture["parts"].append(data)


def find_browser(explicit: str | None) -> str:
    if explicit:
        path = Path(explicit).expanduser()
        if path.is_file():
            return str(path)
        sys.exit(f"Browser not found: {path}")

    env = os.environ.get("CHROME_PATH") or os.environ.get("EDGE_PATH")
    if env and Path(env).is_file():
        return env

    candidates = [
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
        "/usr/bin/google-chrome",
        "/usr/bin/google-chrome-stable",
        "/usr/bin/chromium",
        "/usr/bin/chromium-browser",
        "/usr/bin/microsoft-edge",
    ]
    for candidate in candidates:
        if Path(candidate).is_file():
            return candidate
    for name in (
        "google-chrome", "google-chrome-stable", "chromium",
        "chromium-browser", "chrome", "msedge", "microsoft-edge",
    ):
        found = shutil.which(name)
        if found:
            return found
    sys.exit("Chrome/Edge not found. Pass --browser or set CHROME_PATH.")


def render(browser: str, html_path: Path, pdf_path: Path, timeout: int) -> None:
    cmd = [
        browser,
        "--headless",
        "--disable-gpu",
        "--no-sandbox",
        "--no-pdf-header-footer",
        "--virtual-time-budget=3000",
        f"--print-to-pdf={pdf_path.resolve()}",
        html_path.resolve().as_uri(),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    if result.returncode != 0 or not pdf_path.is_file():
        detail = (result.stderr or result.stdout or "").strip()
        raise RuntimeError(f"Browser failed to render PDF.\n{detail}")
    if pdf_path.stat().st_size == 0:
        raise RuntimeError("Browser wrote an empty PDF.")


def page_key(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", value.lower()).strip()


def read_pages(pdf_path: Path) -> list[str]:
    reader = PdfReader(str(pdf_path))
    return [page.extract_text() or "" for page in reader.pages]


def locate_headings(
    pages: list[str], headings: list[Heading], start_page: int
) -> None:
    keys = [f" {page_key(text)} " for text in pages]
    current = start_page

    for heading in headings:
        candidates = [heading.text]
        stripped = re.sub(r"^\d+\s+", "", heading.text)
        if stripped != heading.text:
            candidates.append(stripped)

        found = None
        for candidate in candidates:
            key = page_key(candidate)
            if not key:
                continue
            needle = f" {key} "
            for index in range(current - 1, len(keys)):
                if needle in keys[index]:
                    found = index + 1
                    break
            if found:
                break

        if not found:
            raise RuntimeError(
                f'Could not find heading in the PDF: "{heading.text}". '
                "Make sure it is visible text and not inside an image or hidden element."
            )

        heading.page = found
        current = found


def find_toc_page(pages: list[str]) -> int | None:
    marker = page_key(TOC_MARKER)
    for index, text in enumerate(pages, 1):
        if marker in page_key(text):
            return index
    return None


def first_match(pattern: str, text: str) -> str | None:
    match = re.search(pattern, text, re.S | re.I)
    if not match:
        return None
    value = re.sub(r"<[^>]+>", " ", match.group(1))
    value = html_lib.unescape(value)
    return re.sub(r"\s+", " ", value).strip()


def build_toc(headings: list[Heading]) -> str:
    entries = []
    chapters = [heading for heading in headings if heading.level == 2]
    for index, heading in enumerate(chapters, 1):
        numbered = re.match(r"(\d+)\s+(.*)", heading.text)
        number = numbered.group(1) if numbered else ""
        title = numbered.group(2) if numbered else heading.text

        if heading.anchor:
            open_tag = f'<a href="#{html_lib.escape(heading.anchor, quote=True)}">'
            close_tag = "</a>"
        else:
            open_tag = "<span>"
            close_tag = "</span>"

        entries.append(
            "<li>"
            f'{open_tag}'
            f'<span class="pdf-toc-num">{html_lib.escape(number)}</span>'
            f'<span class="pdf-toc-title-text">{html_lib.escape(title)}</span>'
            '<span class="pdf-toc-dots"></span>'
            '<span class="pdf-toc-page">00</span>'
            f"{close_tag}"
            "</li>"
        )

    return (
        '<nav class="pdf-toc" aria-label="Contents">'
        '<header class="pdf-toc-head">'
        '<p class="pdf-toc-kicker">Contents</p>'
        '<p class="pdf-toc-title">Contents</p>'
        "</header>"
        '<ol class="pdf-toc-list">'
        + "".join(entries)
        + "</ol>"
        f'<p class="pdf-toc-note">{TOC_MARKER}</p>'
        "</nav>"
    )


TOC_CSS = """<style>
/* make-pdf-from-html:start */
.pdf-toc{display:none}
@media print{
  .pdf-toc{
    display:block; break-after:page; margin:0; padding:0;
    color:var(--ink,#1f1e1d); background:#fff;
  }
  .pdf-toc-head{
    margin:0 0 1.4em; padding:0 0 .55em;
    border-bottom:0.5pt solid var(--line,#d8d3c8);
  }
  .pdf-toc-kicker{
    margin:0 0 .35em; color:var(--terra-dark,#a14e2f);
    font:600 7.5pt/1.3 var(--sans,-apple-system,'Segoe UI',Arial,sans-serif);
    letter-spacing:.15em; text-transform:uppercase;
  }
  .pdf-toc-title{
    margin:0; color:var(--ink,#1f1e1d);
    font:500 24pt/1.15 var(--serif,Georgia,'Times New Roman',serif);
    letter-spacing:-.015em;
  }
  .pdf-toc-list{margin:0; padding:0; list-style:none}
  .pdf-toc-list li{
    margin:0; padding:0; break-inside:avoid;
    position:static;
  }
  .pdf-toc-list li::before{content:none !important}
  .pdf-toc-list a,
  .pdf-toc-list li > span{
    display:flex; gap:.65em; align-items:baseline;
    padding:.38em 0; border-bottom:0.5pt solid var(--line-soft,#e8e4da);
    color:var(--ink,#1f1e1d); text-decoration:none;
  }
  .pdf-toc-num{
    flex:0 0 2.1em; color:var(--terra-dark,#a14e2f);
    font:600 8pt/1.3 var(--mono,Consolas,monospace); letter-spacing:.05em;
  }
  .pdf-toc-title-text{
    font:500 10.8pt/1.35 var(--serif,Georgia,'Times New Roman',serif);
  }
  .pdf-toc-dots{
    flex:1; min-width:1.5em; border-bottom:0.5pt dotted #b9b2a5;
    transform:translateY(-.18em);
  }
  .pdf-toc-page{
    flex:0 0 auto; color:var(--muted,#44423d);
    font:8pt/1.3 var(--mono,Consolas,monospace);
    font-variant-numeric:tabular-nums;
  }
  .pdf-toc-note{
    margin:1.6em 0 0; color:var(--stone,#6b675f);
    font:7.6pt/1.5 var(--sans,-apple-system,'Segoe UI',Arial,sans-serif);
  }
}
/* make-pdf-from-html:end */
</style>"""


def prepare_html(source: str, headings: list[Heading], with_toc: bool) -> str:
    chapters = [heading for heading in headings if heading.level == 2]
    result = re.sub(
        r"<nav\b[^>]*(?:print-toc|pdf-toc)[^>]*>.*?</nav>\s*",
        "",
        source,
        flags=re.S | re.I,
    )
    result = re.sub(
        r"/\* make-pdf-from-html:start \*/.*?/\* make-pdf-from-html:end \*/\s*",
        "",
        result,
        flags=re.S,
    )

    if not with_toc or not chapters:
        return result

    head_close = re.search(r"</head\s*>", result, re.I)
    css = TOC_CSS
    if head_close:
        result = result[: head_close.start()] + css + result[head_close.start():]
    else:
        result = css + result

    section = re.search(r"<section\b", result, re.I)
    if section:
        position = section.start()
    else:
        body = re.search(r"<body\b[^>]*>", result, re.I)
        position = body.end() if body else 0

    return result[:position] + build_toc(chapters) + "\n" + result[position:]


def fill_page_numbers(source: str, headings: list[Heading]) -> str:
    numbers = iter(
        heading.page for heading in headings if heading.level == 2
    )

    def replace(_match: re.Match) -> str:
        try:
            page = next(numbers)
        except StopIteration:
            return _match.group(0)
        return f'<span class="pdf-toc-page">{page or "?"}</span>'

    return re.sub(
        r'<span class="pdf-toc-page">[^<]*</span>',
        replace,
        source,
    )


def add_outline(
    source_pdf: Path,
    output_pdf: Path,
    headings: list[Heading],
    toc_page: int | None,
    document_title: str,
) -> None:
    reader = PdfReader(str(source_pdf))
    writer = PdfWriter()
    writer.clone_document_from_reader(reader)

    # Replace any outline copied from the source PDF.
    writer._root_object.pop(NameObject("/Outlines"), None)
    writer._root_object.pop(NameObject("/PageMode"), None)

    writer.add_outline_item(document_title, 0)
    if toc_page:
        writer.add_outline_item("Contents", toc_page - 1)

    parent = None
    for heading in headings:
        if not heading.page:
            continue
        if heading.level == 2:
            parent = writer.add_outline_item(heading.text, heading.page - 1)
        elif parent is not None:
            writer.add_outline_item(heading.text, heading.page - 1, parent=parent)
        else:
            writer.add_outline_item(heading.text, heading.page - 1)

    writer.page_mode = "/UseOutlines"
    writer.create_viewer_preferences()
    writer.viewer_preferences.display_doc_title = True
    writer.write(str(output_pdf))


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Render HTML to PDF with a printed contents page and PDF bookmarks."
    )
    parser.add_argument("input", type=Path, help="input HTML file")
    parser.add_argument("output", nargs="?", type=Path, help="output PDF (default: input.pdf)")
    parser.add_argument("--browser", help="path to Chrome or Edge")
    parser.add_argument("--no-toc", action="store_true", help="do not add a printed Contents page")
    parser.add_argument("--no-outline", action="store_true", help="do not add PDF bookmarks")
    parser.add_argument("--keep-html", type=Path, help="also save the transformed HTML here")
    parser.add_argument("--title", help="PDF outline title (default: first h1 or <title>)")
    parser.add_argument("--timeout", type=int, default=120, help="browser timeout in seconds")
    args = parser.parse_args()

    source_path = args.input.expanduser().resolve()
    if not source_path.is_file():
        sys.exit(f"Input not found: {source_path}")
    output_path = (args.output or source_path.with_suffix(".pdf")).expanduser().resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)

    browser = find_browser(args.browser)
    source = source_path.read_text(encoding="utf-8")

    heading_parser = HeadingParser()
    heading_parser.feed(source)
    headings = heading_parser.headings

    transformed = prepare_html(source, headings, with_toc=not args.no_toc)
    if args.keep_html:
        keep_path = args.keep_html.expanduser().resolve()
        keep_path.parent.mkdir(parents=True, exist_ok=True)
        keep_path.write_text(transformed, encoding="utf-8")

    temp_html = Path(
        tempfile.NamedTemporaryFile(
            prefix=source_path.stem + ".make-pdf-",
            suffix=".html",
            dir=source_path.parent,
            delete=False,
        ).name
    )
    first_pdf = Path(
        tempfile.NamedTemporaryFile(
            prefix=source_path.stem + ".pass1-", suffix=".pdf", delete=False
        ).name
    )
    final_pdf = Path(
        tempfile.NamedTemporaryFile(
            prefix=source_path.stem + ".pass2-", suffix=".pdf", delete=False
        ).name
    )

    try:
        temp_html.write_text(transformed, encoding="utf-8")
        render(browser, temp_html, first_pdf, args.timeout)

        toc_page = find_toc_page(read_pages(first_pdf)) if not args.no_toc else None
        start_page = (toc_page + 1) if toc_page else 1

        if headings:
            locate_headings(read_pages(first_pdf), headings, start_page)
            transformed = fill_page_numbers(transformed, headings)
            temp_html.write_text(transformed, encoding="utf-8")
            render(browser, temp_html, final_pdf, args.timeout)
        else:
            shutil.copyfile(first_pdf, final_pdf)

        if args.no_outline:
            shutil.copyfile(final_pdf, output_path)
        else:
            document_title = (
                args.title
                or first_match(r"<h1\b[^>]*>(.*?)</h1>", source)
                or first_match(r"<title\b[^>]*>(.*?)</title>", source)
                or source_path.stem
            )
            if headings:
                locate_headings(read_pages(final_pdf), headings, start_page)
            add_outline(final_pdf, output_path, headings, toc_page, document_title)

        print(f"PDF written: {output_path}")
        print(f"Pages: {len(PdfReader(str(output_path)).pages)}")
        if headings and not args.no_toc:
            print(f"Contents page: {toc_page}")
        if not args.no_outline:
            print("Bookmarks: chapters + nested sections")
    finally:
        for path in (temp_html, first_pdf, final_pdf):
            try:
                path.unlink()
            except OSError:
                pass


if __name__ == "__main__":
    main()
