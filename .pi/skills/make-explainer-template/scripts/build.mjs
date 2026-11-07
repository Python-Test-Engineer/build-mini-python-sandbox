#!/usr/bin/env node
/**
 * make-explainer-template - Markdown -> styled HTML -> PDF
 *
 * Dependency-free. Uses the house stylesheet (assets/book.css) and a local
 * Chrome/Edge install for PDF generation.
 *
 * Usage (from a scaffolded project):
 *   node scripts/build.mjs
 *   node scripts/build.mjs --no-pdf
 *   node scripts/build.mjs --book-only
 *   node scripts/build.mjs --source book/BOOK.md --out book/BOOK.html --pdf book/BOOK.pdf
 */

import fs from 'node:fs';
import path from 'node:path';
import { spawnSync } from 'node:child_process';
import { fileURLToPath, pathToFileURL } from 'node:url';

const HERE = path.dirname(fileURLToPath(import.meta.url));

/* ------------------------------------------------------------------ */
/* arguments                                                           */
/* ------------------------------------------------------------------ */

function parseArgs(argv) {
  const out = { _: [] };
  for (let i = 0; i < argv.length; i++) {
    const a = argv[i];
    if (!a.startsWith('--')) { out._.push(a); continue; }
    const key = a.slice(2);
    const next = argv[i + 1];
    if (next !== undefined && !next.startsWith('--')) {
      out[key] = next;
      i++;
    } else {
      out[key] = true;
    }
  }
  return out;
}

const ARGS = parseArgs(process.argv.slice(2));
const ROOT = path.resolve(ARGS.root || ARGS.project || path.dirname(HERE));

/* ------------------------------------------------------------------ */
/* small utilities                                                     */
/* ------------------------------------------------------------------ */

const pad = (n) => String(n).padStart(2, '0');

function esc(value) {
  return String(value ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

function escAttr(value) {
  return esc(value).replace(/'/g, '&#39;');
}

function readText(file) {
  return fs.readFileSync(file, 'utf8').replace(/^\uFEFF/, '');
}

function ensureDir(file) {
  fs.mkdirSync(path.dirname(file), { recursive: true });
}

function relish(p) {
  return path.relative(ROOT, p).split(path.sep).join('/');
}

/* ------------------------------------------------------------------ */
/* markdown -> html                                                    */
/* ------------------------------------------------------------------ */

const RAW_BLOCK_TAGS = new Set([
  'address', 'article', 'aside', 'blockquote', 'body', 'caption', 'center',
  'col', 'colgroup', 'dd', 'details', 'dialog', 'dir', 'div', 'dl', 'dt',
  'fieldset', 'figcaption', 'figure', 'footer', 'form', 'h1', 'h2', 'h3',
  'h4', 'h5', 'h6', 'head', 'header', 'hr', 'html', 'iframe', 'legend',
  'li', 'link', 'main', 'menu', 'menuitem', 'nav', 'noframes', 'ol',
  'optgroup', 'option', 'p', 'param', 'section', 'source', 'summary',
  'table', 'tbody', 'td', 'tfoot', 'th', 'thead', 'title', 'tr', 'track',
  'ul', 'pre', 'script', 'style'
]);

const LIST_RE = /^(\s*)([-*+]|\d+[.)])\s+(.*)$/;

function listMatch(line) {
  const m = line.match(LIST_RE);
  if (!m) return null;
  return {
    indent: m[1].replace(/\t/g, '    ').length,
    ordered: /^\d/.test(m[2]),
    text: m[3],
    marker: m[2],
  };
}

function indentOf(line) {
  return (line.match(/^\s*/) || [''])[0].replace(/\t/g, '    ').length;
}

function isBlank(line) {
  return /^\s*$/.test(line);
}

function isFence(line) {
  return /^\s*(```|~~~)/.test(line);
}

function isHeading(line) {
  return /^#{1,6}\s+/.test(line);
}

function isHr(line) {
  return /^\s*((\*\s*){3,}|(-\s*){3,}|(_\s*){3,})$/.test(line);
}

function isQuote(line) {
  return /^\s*>/.test(line);
}

function isRawBlock(line) {
  const m = line.match(/^\s*<([a-zA-Z][\w-]*)/);
  if (!m) return false;
  return RAW_BLOCK_TAGS.has(m[1].toLowerCase()) || /^\s*<!--/.test(line);
}

function isTableStart(lines, i) {
  if (!lines[i] || !lines[i].includes('|')) return false;
  const next = lines[i + 1];
  if (!next || !next.includes('|')) return false;
  return /^\s*\|?\s*:?-{2,}/.test(next);
}

function isBlockStart(lines, i) {
  const line = lines[i];
  if (isBlank(line)) return true;
  if (isFence(line) || isHeading(line) || isHr(line) || isQuote(line)) return true;
  if (listMatch(line)) return true;
  if (isTableStart(lines, i)) return true;
  if (isRawBlock(line)) return true;
  return false;
}

/* inline formatting ------------------------------------------------- */

function inline(text) {
  const stash = [];
  let s = esc(String(text ?? ''));

  // Inline code first, so markdown inside code is untouched.
  s = s.replace(/`([^`]+)`/g, (_, code) => {
    stash.push(`<code>${code}</code>`);
    return `\u0000${stash.length - 1}\u0000`;
  });

  // Images
  s = s.replace(/!\[([^\]]*)\]\(([^)\s]+)(?:\s+&quot;([^&]*)&quot;)?\)/g, (_, alt, src, title) => {
    const t = title ? ` title="${escAttr(title)}"` : '';
    return `<img src="${src}" alt="${alt}"${t}>`;
  });

  // Links
  s = s.replace(/\[([^\]]+)\]\(([^)\s]+)(?:\s+&quot;([^&]*)&quot;)?\)/g, (_, label, href, title) => {
    const t = title ? ` title="${escAttr(title)}"` : '';
    const external = /^https?:\/\//i.test(href) ? ' target="_blank" rel="noopener noreferrer"' : '';
    return `<a href="${href}"${t}${external}>${label}</a>`;
  });

  // Auto-links
  s = s.replace(/(^|[\s(])(https?:\/\/[^\s<)]+)/g, (_, pre, url) => {
    return `${pre}<a href="${url}" target="_blank" rel="noopener noreferrer">${url}</a>`;
  });

  // Strong / emphasis / strike
  s = s
    .replace(/\*\*([^*\n]+)\*\*/g, '<strong>$1</strong>')
    .replace(/__([^_\n]+)__/g, '<strong>$1</strong>')
    .replace(/(^|[^*])\*([^*\n]+)\*/g, '$1<em>$2</em>')
    .replace(/(^|[^_])_([^_\n]+)_/g, '$1<em>$2</em>')
    .replace(/~~([^~]+)~~/g, '<del>$1</del>');

  return s.replace(/\u0000(\d+)\u0000/g, (_, n) => stash[Number(n)]);
}

function plainInline(text) {
  return String(text ?? '')
    .replace(/!\[([^\]]*)\]\([^)]*\)/g, '$1')
    .replace(/\[([^\]]+)\]\([^)]*\)/g, '$1')
    .replace(/[*_~`]/g, '')
    .replace(/<[^>]+>/g, '')
    .replace(/\s+/g, ' ')
    .trim();
}

/* block parsers ----------------------------------------------------- */

function parseTable(lines, start) {
  const rows = [];
  let i = start;
  while (i < lines.length && lines[i].includes('|') && !/^\s*$/.test(lines[i])) {
    const row = lines[i].trim().replace(/^\|/, '').replace(/\|$/, '');
    const cells = row.split('|').map((cell) => cell.trim());
    if (!/^:?-{2,}/.test(cells[0] || '')) rows.push(cells);
    i++;
  }
  const header = rows.shift() || [];
  const body = rows;

  let html = '<div class="table-wrap"><table>';
  if (header.length) {
    html += '<thead><tr>' + header.map((c) => `<th>${inline(c)}</th>`).join('') + '</tr></thead>';
  }
  html += '<tbody>';
  for (const row of body) {
    html += '<tr>' + row.map((c) => `<td>${inline(c)}</td>`).join('') + '</tr>';
  }
  html += '</tbody></table></div>';
  return { html, next: i };
}

function parseQuote(lines, start) {
  const buf = [];
  let i = start;
  while (i < lines.length && isQuote(lines[i])) {
    buf.push(lines[i].replace(/^\s*>\s?/, ''));
    i++;
  }
  let text = buf.join('\n').trim();
  let kind = 'note';
  const marker = text.match(/^\[!(NOTE|TIP|IMPORTANT|WARNING|CAUTION)\]\s*/i);
  if (marker) {
    kind = marker[1].toLowerCase();
    text = text.slice(marker[0].length);
  }

  const blocks = text.split(/\n\s*\n/).filter((b) => b.trim());
  const inner = blocks.map((block) => {
    const body = block.split('\n').map((line) => {
      const hard = /  $/.test(line);
      const t = inline(line.trim());
      return hard ? `${t}<br>` : t;
    }).join(' ');
    return `<p>${body}</p>`;
  }).join('');

  const warn = kind === 'warning' || kind === 'caution';
  return { html: `<div class="callout${warn ? ' warn' : ''}">${inner}</div>`, next: i };
}

function parseList(lines, start, baseIndent) {
  const first = listMatch(lines[start]);
  const ordered = first.ordered;
  const items = [];
  let i = start;

  while (i < lines.length) {
    const line = lines[i];

    if (isBlank(line)) {
      // A blank line stays in the list only when an indented line or a list
      // item follows. Otherwise the list ends.
      let j = i + 1;
      while (j < lines.length && isBlank(lines[j])) j++;
      if (j >= lines.length) break;
      const nextMatch = listMatch(lines[j]);
      const nextIndent = indentOf(lines[j]);
      if (nextIndent > baseIndent || (nextMatch && nextIndent >= baseIndent)) {
        i++;
        continue;
      }
      break;
    }

    const m = listMatch(line);
    if (m) {
      if (m.indent < baseIndent) break;
      if (m.indent > baseIndent) {
        if (!items.length) break;
        const nested = parseList(lines, i, m.indent);
        items[items.length - 1].children.push(nested.html);
        i = nested.next;
        continue;
      }
      if (m.indent === baseIndent) {
        if (m.ordered !== ordered) break;
        items.push({ text: m.text, extra: [], children: [] });
        i++;
        continue;
      }
    }

    const ind = indentOf(line);
    if (ind > baseIndent && items.length) {
      items[items.length - 1].extra.push(line.trim());
      i++;
      continue;
    }
    break;
  }

  let html = ordered ? '<ol>' : '<ul>';
  for (const item of items) {
    let body = inline(item.text);
    if (item.extra.length) body += '<br>' + item.extra.map(inline).join('<br>');
    body += item.children.join('');
    html += `<li>${body}</li>`;
  }
  html += ordered ? '</ol>' : '</ul>';
  return { html, next: i };
}

/* document renderer ------------------------------------------------- */

function renderMarkdown(md, options = {}) {
  const lines = md.replace(/\r\n?/g, '\n').split('\n');
  const out = [];
  const toc = [];
  let i = 0;
  let sectionOpen = false;
  let h1 = 0;
  let h2 = 0;
  let h3 = 0;

  const closeSection = () => {
    if (sectionOpen) {
      out.push('</section>');
      sectionOpen = false;
    }
  };

  while (i < lines.length) {
    const line = lines[i];

    if (isBlank(line)) { i++; continue; }

    // fenced code
    if (isFence(line)) {
      const fence = line.match(/^\s*(```|~~~)\s*([^\s`]*)/);
      const marker = fence[1];
      const lang = (fence[2] || '').trim();
      const code = [];
      i++;
      while (i < lines.length && !new RegExp(`^\\s*${marker}`).test(lines[i])) {
        code.push(lines[i]);
        i++;
      }
      if (i < lines.length) i++;
      const caption = lang
        ? `<figcaption><span>${esc(lang)}</span><span class="lang">code</span></figcaption>`
        : '';
      out.push(`<figure class="code">${caption}<pre>${esc(code.join('\n'))}</pre></figure>`);
      continue;
    }

    // headings
    const heading = line.match(/^(#{1,6})\s+(.*)$/);
    if (heading) {
      const level = heading[1].length;
      const text = heading[2].trim();
      let id;

      if (level === 1) {
        closeSection();
        h1++;
        h2 = 0;
        h3 = 0;
        id = `s${pad(h1)}`;
        out.push(`<section id="${id}">`);
        sectionOpen = true;
        out.push(`<h2><span class="num">${pad(h1)}</span><span>${inline(text)}</span></h2>`);
        toc.push({ id, level: 2, label: plainInline(text), num: pad(h1) });
      } else if (level === 2) {
        h2++;
        h3 = 0;
        id = `s${pad(h1)}-${pad(h2)}`;
        out.push(`<h3 id="${id}">${inline(text)}</h3>`);
        toc.push({ id, level: 3, label: plainInline(text), num: '' });
      } else if (level === 3) {
        h3++;
        id = `s${pad(h1)}-${pad(h2)}-${pad(h3)}`;
        out.push(`<h4 id="${id}">${inline(text)}</h4>`);
        toc.push({ id, level: 4, label: plainInline(text), num: '' });
      } else {
        id = `h${pad(h1)}-${pad(h2)}-${pad(h3)}-${level}`;
        out.push(`<h5 id="${id}">${inline(text)}</h5>`);
      }
      i++;
      continue;
    }

    if (isHr(line)) {
      out.push('<hr>');
      i++;
      continue;
    }

    if (isTableStart(lines, i)) {
      const table = parseTable(lines, i);
      out.push(table.html);
      i = table.next;
      continue;
    }

    if (isQuote(line)) {
      const quote = parseQuote(lines, i);
      out.push(quote.html);
      i = quote.next;
      continue;
    }

    const lm = listMatch(line);
    if (lm) {
      const list = parseList(lines, i, lm.indent);
      out.push(list.html);
      i = list.next;
      continue;
    }

    if (isRawBlock(line)) {
      const raw = [];
      while (i < lines.length && !isBlank(lines[i])) {
        raw.push(lines[i]);
        i++;
      }
      out.push(raw.join('\n'));
      continue;
    }

    // paragraph
    const para = [];
    while (i < lines.length && !isBlockStart(lines, i)) {
      para.push(lines[i]);
      i++;
    }
    if (!para.length) { i++; continue; }

    const body = para.map((raw) => {
      const hard = /  $/.test(raw);
      const text = inline(raw.trim());
      return hard ? `${text}<br>` : text;
    }).join(' ');
    out.push(`<p>${body}</p>`);
  }

  closeSection();
  return { html: out.join('\n'), toc };
}

/* ------------------------------------------------------------------ */
/* page shell                                                          */
/* ------------------------------------------------------------------ */

function renderPage({ content, toc, title, kicker, subtitle, language, disclaimer, meta, source, colophon }) {
  const cssPath = path.resolve(ROOT, 'assets', 'book.css');
  if (!fs.existsSync(cssPath)) {
    throw new Error(`Stylesheet not found: ${cssPath}`);
  }
  const css = readText(cssPath);

  const tocHtml = toc.map((item) => {
    const cls = item.level === 2 ? 'l2' : item.level === 3 ? 'l3' : 'l4';
    const num = item.num ? `<span class="n">${esc(item.num)}</span>` : '<span class="n"></span>';
    return `<a href="#${escAttr(item.id)}" class="${cls}">${num}<span>${esc(item.label)}</span></a>`;
  }).join('\n      ');

  const metaHtml = (meta || [])
    .filter(Boolean)
    .map((m) => `<span>${esc(m)}</span>`)
    .join('\n          ');

  const sourceName = source ? path.basename(source) : 'Markdown';

  return `<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>${esc(title)}</title>
<meta name="description" content="${escAttr(subtitle || title)}">
<style>
${css}
</style>
<script>
(function () {
  try {
    var saved = localStorage.getItem('explainer-theme');
    var mode = saved === 'light' || saved === 'dark' ? saved : 'auto';
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
    <a class="side-kicker" href="#top">${esc(kicker || 'Explainer book')}</a>
    <p class="side-title">${esc(title)}</p>
    <p class="side-sub">${esc(subtitle || '')}</p>
    <div class="side-rule"></div>
    <p class="side-label">Contents</p>
    <nav class="toc" id="toc">
      ${tocHtml}
    </nav>
    <div class="side-foot">
      Built from <code>${esc(sourceName)}</code><br>
      ${toc.length} sections${language ? ` &middot; ${esc(language)}` : ''}
    </div>
  </aside>

  <main class="pane" id="top">
    <div class="inner">
      <header class="page-heading">
        <p class="eyebrow">${esc(kicker || 'Explainer book')}</p>
        <h1>${esc(title)}</h1>
        <p class="lede">${esc(subtitle || '')}</p>
        <p class="meta">
          ${metaHtml}
        </p>
      </header>

      <div class="disclaimer" role="note">
        <span class="label">Educational use only &middot; not production grade</span>
        ${esc(disclaimer || 'This material is for educational purposes only. It is a deliberately simplified teaching system, not a production-grade implementation. Do not deploy it as-is.')}
      </div>

${content}

      <div class="colophon">
        ${colophon || `Built from <code>${esc(sourceName)}</code> &middot; ${toc.length} sections${language ? ` &middot; ${esc(language)}` : ''}`}
      </div>
    </div>
  </main>
</div>

<script>
(function(){
  var toc = document.getElementById('toc');
  if (!toc) return;
  var links = toc.querySelectorAll('a');
  var sections = [];
  links.forEach(function(a){
    var id = a.getAttribute('href').slice(1);
    var el = document.getElementById(id);
    if (el) sections.push({link:a, el:el});
  });
  function onScroll(){
    var y = window.scrollY + 80;
    var active = null;
    for (var i = 0; i < sections.length; i++){
      if (y >= sections[i].el.offsetTop) active = sections[i];
    }
    sections.forEach(function(s){ s.link.classList.remove('active'); });
    if (active) active.link.classList.add('active');
    var bar = document.getElementById('bar');
    var doc = document.documentElement;
    var pct = doc.scrollTop / (doc.scrollHeight - doc.clientHeight);
    bar.style.width = Math.max(0, Math.min(1, pct || 0)) * 100 + '%';
  }
  window.addEventListener('scroll', onScroll, {passive:true});
  onScroll();
})();
</script>

<button id="stylebtn" type="button" aria-label="Toggle colour theme" title="Toggle colour theme">Aa</button>
<script>
(function(){
  var btn = document.getElementById('stylebtn');
  if (!btn) return;
  btn.addEventListener('click', function(){
    var dark = document.documentElement.getAttribute('data-theme') === 'dark';
    var next = dark ? 'light' : 'dark';
    document.documentElement.setAttribute('data-theme', next);
    try { localStorage.setItem('explainer-theme', next); } catch (e) {}
  });
})();
</script>
</body>
</html>
`;
}

/* ------------------------------------------------------------------ */
/* pdf                                                                 */
/* ------------------------------------------------------------------ */

function findBrowser() {
  const explicit = process.env.CHROME_PATH || process.env.BROWSER_PATH;
  if (explicit && fs.existsSync(explicit)) return explicit;

  const candidates = [];
  const add = (p) => { if (p) candidates.push(p); };

  if (process.platform === 'win32') {
    for (const base of [process.env.ProgramFiles, process.env['ProgramFiles(x86)'], process.env.LOCALAPPDATA]) {
      add(base && path.join(base, 'Google', 'Chrome', 'Application', 'chrome.exe'));
      add(base && path.join(base, 'Microsoft', 'Edge', 'Application', 'msedge.exe'));
    }
  } else if (process.platform === 'darwin') {
    add('/Applications/Google Chrome.app/Contents/MacOS/Google Chrome');
    add('/Applications/Chromium.app/Contents/MacOS/Chromium');
    add('/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge');
  } else {
    for (const name of ['google-chrome', 'google-chrome-stable', 'chromium', 'chromium-browser', 'microsoft-edge', 'msedge']) {
      const found = spawnSync('which', [name], { encoding: 'utf8' });
      if (found.status === 0 && found.stdout.trim()) candidates.push(found.stdout.trim());
    }
  }

  for (const candidate of candidates) {
    if (candidate && fs.existsSync(candidate)) return candidate;
  }

  if (process.platform === 'win32') {
    for (const name of ['chrome', 'msedge']) {
      const found = spawnSync('where', [name], { encoding: 'utf8' });
      if (found.status === 0 && found.stdout.trim()) {
        return found.stdout.split(/\r?\n/)[0].trim();
      }
    }
  }
  return null;
}

function writePdf(htmlFile, pdfFile) {
  const browser = findBrowser();
  if (!browser) {
    throw new Error(
      'No Chrome/Edge found for PDF generation. Set CHROME_PATH, install Chrome/Edge, or run with --no-pdf.'
    );
  }

  ensureDir(pdfFile);
  const url = pathToFileURL(htmlFile).href;
  const common = [
    '--disable-gpu',
    '--no-sandbox',
    '--disable-extensions',
    '--hide-scrollbars',
    '--run-all-compositor-stages-before-draw',
    '--virtual-time-budget=8000',
    '--no-pdf-header-footer',
    `--print-to-pdf=${pdfFile}`,
    url,
  ];

  for (const headless of ['--headless=new', '--headless']) {
    const result = spawnSync(browser, [headless, ...common], {
      encoding: 'utf8',
      timeout: 120_000,
      windowsHide: true,
    });
    if (result.status === 0 && fs.existsSync(pdfFile) && fs.statSync(pdfFile).size > 0) {
      return { browser, pdfFile };
    }
  }

  throw new Error(`PDF generation failed for ${relish(pdfFile)} (browser: ${browser})`);
}

/* ------------------------------------------------------------------ */
/* build one document                                                  */
/* ------------------------------------------------------------------ */

function buildDocument(opts) {
  const source = path.resolve(ROOT, opts.source);
  if (!fs.existsSync(source)) throw new Error(`Markdown source not found: ${source}`);

  let md = readText(source);

  // Drop a leading YAML front-matter block.
  md = md.replace(/^---\n[\s\S]*?\n---\n/, '');

  const { html, toc } = renderMarkdown(md);
  const page = renderPage({
    content: html,
    toc,
    title: opts.title,
    kicker: opts.kicker,
    subtitle: opts.subtitle,
    language: opts.language,
    disclaimer: opts.disclaimer,
    meta: opts.meta,
    source,
    colophon: opts.colophon,
  });

  const outHtml = path.resolve(ROOT, opts.outHtml);
  ensureDir(outHtml);
  fs.writeFileSync(outHtml, page, 'utf8');
  console.log(`HTML  ${relish(outHtml)}  (${toc.length} sections)`);

  if (opts.pdf && !ARGS['no-pdf']) {
    const outPdf = path.resolve(ROOT, opts.pdf);
    const result = writePdf(outHtml, outPdf);
    console.log(`PDF   ${relish(outPdf)}  (${path.basename(result.browser)})`);
  }
}

/* ------------------------------------------------------------------ */
/* config + chapter discovery                                          */
/* ------------------------------------------------------------------ */

function loadConfig() {
  const configPath = path.resolve(ROOT, ARGS.config || 'book.config.json');
  let config = {};
  if (fs.existsSync(configPath)) {
    config = JSON.parse(readText(configPath));
  }
  return config;
}

function firstHeading(file) {
  const md = readText(file);
  const m = md.match(/^#\s+(.+)$/m);
  return m ? plainInline(m[1]) : null;
}

function chapterTitle(file, config) {
  const heading = firstHeading(file);
  if (heading) return heading;
  return path.basename(path.dirname(file));
}

function main() {
  const config = loadConfig();
  const title = ARGS.title || config.title || 'Explainer Book';
  const language = ARGS.language || config.language || '';
  const kicker = ARGS.kicker || config.kicker || 'Explainer book';
  const subtitle = ARGS.subtitle || config.subtitle || '';
  const disclaimer = ARGS.disclaimer || config.disclaimer || undefined;

  // Single-document override.
  if (ARGS.source) {
    buildDocument({
      source: ARGS.source,
      outHtml: ARGS.out || String(ARGS.source).replace(/\.md$/i, '.html'),
      pdf: ARGS.pdf === undefined ? String(ARGS.source).replace(/\.md$/i, '.pdf') : ARGS.pdf,
      title,
      kicker,
      subtitle,
      language,
      disclaimer,
      meta: [language, 'Markdown · HTML · PDF'],
      colophon: `Built from <code>${esc(path.basename(ARGS.source))}</code>`,
    });
    return;
  }

  const bookSource = config.source || 'book/BOOK.md';
  buildDocument({
    source: bookSource,
    outHtml: config.outputHtml || 'book/BOOK.html',
    pdf: config.outputPdf || 'book/BOOK.pdf',
    title: config.title || title,
    kicker: config.kicker || kicker,
    subtitle: config.subtitle || subtitle,
    language: config.language || language,
    disclaimer: config.disclaimer || disclaimer,
    meta: [
      config.language || language,
      config.chapters ? `${config.chapters} chapters` : null,
      'Markdown · HTML · PDF',
    ],
    colophon: config.colophon,
  });

  if (ARGS['book-only'] || ARGS['no-chapters'] || config.buildChapters === false) return;

  const dirs = fs.readdirSync(ROOT, { withFileTypes: true })
    .filter((entry) => entry.isDirectory() && /^ch\d+$/.test(entry.name))
    .map((entry) => entry.name)
    .sort();

  for (const dir of dirs) {
    const source = path.join(dir, 'CHAPTER.md');
    if (!fs.existsSync(path.join(ROOT, source))) continue;
    const chapterName = chapterTitle(path.join(ROOT, source), config);
    buildDocument({
      source,
      outHtml: path.join(dir, 'CHAPTER.html'),
      pdf: path.join(dir, 'CHAPTER.pdf'),
      title: chapterName,
      kicker: config.title || title,
      subtitle: `Chapter run sheet · ${config.title || title}`,
      language: config.language || language,
      disclaimer: config.disclaimer || disclaimer,
      meta: [dir.toUpperCase(), config.language || language, 'Markdown · HTML · PDF'],
      colophon: `Built from <code>${esc(path.basename(source))}</code> &middot; ${esc(config.title || title)}`,
    });
  }
}

try {
  main();
} catch (error) {
  console.error(`build: ${error.message}`);
  process.exit(1);
}
