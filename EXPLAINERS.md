# HTML explainer standard

Every HTML explainer in this repo uses the same shell, palette and behaviours as
the reference page:

> <https://github.com/Python-Test-Engineer/build-mini-js-coder-book/blob/main/plan.html>

That page is the visual source of truth. Do not redesign a page; reuse the
shared assets and the markup below.

## Files

| File | Purpose |
| --- | --- |
| `assets/explainer.css` | Canonical stylesheet (palette, type, layout, code, tables, callouts, Q&A, print, narrow screens). |
| `assets/explainer.js` | Theme boot sync, progress bar, TOC scrollspy, and the `Aa` site customiser. |
| `templates/explainer.html` | Starter page. Copy it, then fill in the content. |
| `scripts/md-to-html.mjs` | Canonical Markdown → HTML converter. Inlines the assets by default; `--link` references them. |
| `qa.html` | Live example: the architecture Q&A rendered with this standard. |

Pages stay build-free and dependency-free. Either inline the shared CSS/JS (the
generator default) or keep `assets/explainer.css` and `assets/explainer.js`
reachable by relative path.

## Generating from Markdown

For a long-form `.md` source, do not hand-build the shell:

```bash
node scripts/md-to-html.mjs INPUT.md OUTPUT.html
node scripts/md-to-html.mjs INPUT.md OUTPUT.html --link
node scripts/md-to-html.mjs INPUT.md OUTPUT.html --title "TITLE" --lede "One line."
```

- Default output is self-contained: the CSS and JS are inlined, so the page can
  be opened or copied anywhere.
- `--link` references `assets/explainer.css` and `assets/explainer.js` from the
  output directory instead. Use this when the page lives in the repo and you
  want style updates to apply without regenerating.
- The first `#` heading becomes the page title; `##` headings become numbered
  sections; `###` and `####` become `h3`/`h4` in the TOC.
- Blockquotes become callouts; a callout whose first line is `**Warning:**`,
  `**Caution:**` or `**Danger:**` gets the warning colour.
- Fenced code with a `lang file` info string renders the filename and language
  in the caption bar (for example ` ```python demo.py `).

The `make-html-from-md` skill wraps the same workflow. Prefer
`scripts/md-to-html.mjs` so there is one style source.

## The rules

1. **Same shell.** Reading column on the right, sticky TOC sidebar on the left,
   thin progress bar across the top.
2. **Same tokens.** Use the CSS custom properties (`--paper`, `--ink`, `--terra`,
   `--code-bg`, ...). Never hard-code a colour that the palette already defines.
   Both light and dark themes must work.
3. **Same type.** Serif headings, sans body, mono code. Section headings are
   numbered and carry a `.num` span.
4. **Same components.** Callouts (`div.callout`, `div.callout.warn`), code
   figures (`figure.code`), ASCII figures (`figure.ascii`), table wrappers
   (`div.table-wrap`) and the colophon.
5. **Same behaviour.** No page-local copies of the scrollspy, progress bar or
   customiser. Load `assets/explainer.js` once, at the end of `<body>`.
6. **Single content column.** Keep `--measure` at `46rem` unless the page is a
   wide reference table.
7. **Accessible.** Every TOC link points at a real `id`; interactive controls
   have labels; the page still reads with CSS disabled.

## Page skeleton

```html
<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Explainer title</title>
<link rel="stylesheet" href="assets/explainer.css">
<script>
/* Theme bootstrap — inline, before content, to avoid a light flash. */
(function () {
  try {
    var saved = JSON.parse(localStorage.getItem('mca-site-customiser:v2')) || {};
    var mode = saved.mode === 'light' || saved.mode === 'dark' ? saved.mode : 'auto';
    var dark = mode === 'dark' || (mode === 'auto' && window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches);
    document.documentElement.setAttribute('data-theme', dark ? 'dark' : 'light');
  } catch (e) { /* no stored preference */ }
})();
</script>
</head>
<body>
<div class="progress"><span id="bar"></span></div>
<div class="shell">
  <aside class="sidebar">
    <a class="side-kicker" href="#top">project &middot; explainer</a>
    <p class="side-title">TITLE</p>
    <p class="side-sub">One line describing the page.</p>
    <div class="side-rule"></div>
    <p class="side-label">Contents</p>
    <nav class="toc" id="toc">
      <a href="#s01" class="l2"><span class="n">01</span><span>First section</span></a>
      <a href="#s01-01" class="l3"><span class="n"></span><span>Subsection</span></a>
    </nav>
    <div class="side-foot">Built from <code>PLAN.md</code><br>2 sections</div>
  </aside>

  <main class="pane" id="top">
    <div class="inner">
      <header class="page-heading">
        <p class="eyebrow">Reading guide</p>
        <h1>TITLE</h1>
        <p class="lede">What this page explains and who it is for.</p>
        <p class="meta"><span>2 sections</span><span>generated page</span></p>
      </header>

      <section id="s01">
        <h2><span class="num">01</span><span>First section</span></h2>
        <p>Body copy.</p>
      </section>

      <div class="colophon">Built from <code>PLAN.md</code> &middot; 2 sections</div>
    </div>
  </main>
</div>
<script src="assets/explainer.js"></script>
</body>
</html>
```

`templates/explainer.html` is this skeleton with working examples of every
component. Copy it to the location you need and fix the two asset paths
(`../assets/` -> `assets/` when the page sits at the repo root).

## TOC conventions

- `l2` = a numbered section (`01`, `02`, ...). Always include `<span class="n">`.
- `l3` = a subsection (`h3`). Leave `<span class="n"></span>` empty.
- `l4` = a deep subsection (`h4`). Leave `<span class="n"></span>` empty.
- The scrollspy in `assets/explainer.js` highlights the last heading passed.
- If a page rebuilds its TOC dynamically (for example after a search filter),
  call `window.Explainer.refreshToc()` afterwards.

## Q&A pages

The Q&A layout is the same shell plus a search box and `<details>` accordions:

```html
<input id="search" class="search" type="search" placeholder="Search…" aria-label="Search">
...
<div id="qa-root"></div>

<details class="qa-item">
  <summary>Question text?</summary>
  <div class="answer"><p>Answer text.</p></div>
</details>
```

`qa.html` builds these from a `QA` data array. Reuse that pattern when the
content is a question bank; use static markup when it is prose.

## Do not

- Do not add a second palette, a second sidebar, or a page-local `:root` block.
- Do not import fonts, JS frameworks or icon libraries.
- Do not remove the print styles; printable explainers are part of the standard.
- Do not put content outside `.inner`; the measure and rhythm depend on it.

## Check before committing

1. Open the page in a browser at desktop width, at ~700 px, and with print preview.
2. Toggle the `Aa` panel: light, dark, and system modes all look correct.
3. Every sidebar link scrolls to its section and the active item updates.
4. No horizontal scroll except inside `figure.code`, `figure.ascii` and
   `.table-wrap`.
