#!/usr/bin/env node
/**
 * Convert a long-form Markdown file into a styled HTML explainer.
 *
 * The output uses the canonical explainer design system (the plan.html look):
 * sticky numbered TOC, reading-progress bar, warm-neutral palette, dark code
 * blocks, callouts, tables, print styles and the "Aa" site customiser.
 *
 * Styling and behaviour live in assets/explainer.css and assets/explainer.js.
 * By default they are inlined so the page is a self-contained single file.
 *
 * Usage:
 *   node scripts/md-to-html.mjs input.md [output.html]
 *   node scripts/md-to-html.mjs input.md output.html --link
 *
 * Options:
 *   --title <text>    page / document title
 *   --eyebrow <text>  small label above the title (default: Reading guide)
 *   --lede <text>     subtitle paragraph
 *   --kicker <text>   sidebar kicker (default: explainer)
 *   --meta <text>     pipe-separated masthead details
 *   --foot <text>     sidebar footer line
 *   --colophon <text> closing colophon line
 *   --book            treat every H1 as a chapter and H2 as a subsection
 *   --link            reference assets/ instead of inlining them
 *   --out <file>      output path (same as the positional argument)
 */

import { readFileSync, writeFileSync } from 'node:fs';
import { basename, dirname, extname, join, relative, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const HERE = dirname(fileURLToPath(import.meta.url));
const ROOT = resolve(HERE, '..');
const ASSETS = join(ROOT, 'assets');

const args = process.argv.slice(2);
const opts = { link: false, book: false, out: '', title: '', eyebrow: '', lede: '', kicker: '', meta: '', foot: '', colophon: '', input: '' };

for (let i = 0; i < args.length; i++) {
  const a = args[i];
  if (a === '--link') opts.link = true;
  else if (a === '--book') opts.book = true;
  else if (a === '--out') opts.out = args[++i] || '';
  else if (a === '--title') opts.title = args[++i] || '';
  else if (a === '--eyebrow') opts.eyebrow = args[++i] || '';
  else if (a === '--lede') opts.lede = args[++i] || '';
  else if (a === '--kicker') opts.kicker = args[++i] || '';
  else if (a === '--meta') opts.meta = args[++i] || '';
  else if (a === '--foot') opts.foot = args[++i] || '';
  else if (a === '--colophon') opts.colophon = args[++i] || '';
  else if (a === '--help' || a === '-h') { usage(); process.exit(0); }
  else if (!opts.input) opts.input = a;
  else if (!opts.out) opts.out = a;
  else { console.error(`Unexpected argument: ${a}`); process.exit(2); }
}

if (!opts.input) { usage(); process.exit(2); }

const inputPath = resolve(process.cwd(), opts.input);
const outputPath = resolve(process.cwd(), opts.out || inputPath.replace(/\.md$/i, '') + '.html');
const sourceName = basename(inputPath);

function usage() {
  console.log('Usage: node scripts/md-to-html.mjs <input.md> [output.html] [options]');
  console.log('Options: --title --eyebrow --lede --kicker --meta --foot --colophon --book --link --out');
}

/* ------------------------------------------------------------------ */
/* inline formatting                                                   */
/* ------------------------------------------------------------------ */

const escapeHtml = (s) =>
  String(s)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');

function formatInline(escaped) {
  let s = escaped;
  s = s.replace(/!\[([^\]]*)\]\(([^)\s]+)\)/g, '<img src="$2" alt="$1">');
  s = s.replace(/\[([^\]]+)\]\(([^)\s]+)\)/g, '<a href="$2">$1</a>');
  s = s.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>');
  s = s.replace(/__([^_]+)__/g, '<strong>$1</strong>');
  s = s.replace(/(^|[^*])\*([^*\n]+)\*/g, '$1<em>$2</em>');
  s = s.replace(/(^|[^_])_([^_\n]+)_/g, '$1<em>$2</em>');
  return s;
}

function inline(text) {
  const parts = String(text).split(/(`[^`]+`)/g);
  return parts
    .map((part) => {
      if (/^`[^`]+`$/.test(part)) return `<code>${escapeHtml(part.slice(1, -1))}</code>`;
      return formatInline(escapeHtml(part));
    })
    .join('');
}

const plain = (text) =>
  String(text)
    .replace(/`([^`]+)`/g, '$1')
    .replace(/!\[([^\]]*)\]\([^)]*\)/g, '$1')
    .replace(/\[([^\]]+)\]\([^)]*\)/g, '$1')
    .replace(/\*\*([^*]+)\*\*/g, '$1')
    .replace(/__([^_]+)__/g, '$1')
    .replace(/\*([^*]+)\*/g, '$1')
    .replace(/_([^_]+)_/g, '$1')
    .replace(/<[^>]+>/g, '')
    .trim();

const pad = (n) => String(n).padStart(2, '0');

/* ------------------------------------------------------------------ */
/* block parser                                                        */
/* ------------------------------------------------------------------ */

function gatherList(lines, start, markerRe) {
  const values = [];
  let current = null;
  let i = start;

  while (i < lines.length) {
    const line = lines[i];
    if (markerRe.test(line)) {
      if (current !== null) values.push(current);
      current = line.replace(markerRe, '');
      i++;
      continue;
    }
    /* An indented continuation line belongs to the current item. */
    if (current !== null && /^\s{2,}\S/.test(line)) {
      current += ' ' + line.trim();
      i++;
      continue;
    }
    break;
  }
  if (current !== null) values.push(current);

  return { values, next: i };
}

function parseMarkdown(markdown, options) {
  const lines = String(markdown).replace(/\r\n?/g, '\n').split('\n');
  const toc = [];
  let body = '';
  let sectionOpen = false;
  let sectionCount = 0;
  let subCount = 0;
  let subSubCount = 0;
  let title = options.title || '';
  let sawH1 = false;
  let i = 0;

  const closeSection = () => {
    if (sectionOpen) { body += '</section>\n'; sectionOpen = false; }
  };

  const nextId = (level) => {
    if (level === 2) {
      sectionCount++; subCount = 0; subSubCount = 0;
      return `s${pad(sectionCount)}`;
    }
    if (level === 3) {
      subCount++; subSubCount = 0;
      return `s${pad(sectionCount)}-${pad(subCount)}`;
    }
    subSubCount++;
    return `s${pad(sectionCount)}-${pad(subCount)}-${pad(subSubCount)}`;
  };

  const addHeading = (level, text) => {
    const id = nextId(level);
    if (level === 2) {
      closeSection();
      if (!title) title = plain(text);
      body += `<section id="${id}">\n`;
      sectionOpen = true;
      body += `<h2><span class="num">${pad(sectionCount)}</span><span>${inline(text)}</span></h2>\n`;
      toc.push({ level: 2, id, label: plain(text) });
    } else if (level === 3) {
      body += `<h3 id="${id}">${inline(text)}</h3>\n`;
      toc.push({ level: 3, id, label: plain(text) });
    } else if (level === 4) {
      body += `<h4 id="${id}">${inline(text)}</h4>\n`;
      toc.push({ level: 4, id, label: plain(text) });
    } else {
      body += `<h5>${inline(text)}</h5>\n`;
    }
  };

  while (i < lines.length) {
    const line = lines[i];

    if (/^\s*$/.test(line)) { i++; continue; }

    /* fenced code */
    const fence = line.match(/^(\s*)(`{3,}|~{3,})\s*(.*)$/);
    if (fence) {
      const marker = fence[2][0];
      const info = fence[3].trim();
      i++;
      const code = [];
      while (i < lines.length && !new RegExp('^\\s*' + marker + '{3,}\\s*$').test(lines[i])) {
        code.push(lines[i]); i++;
      }
      i++; // closing fence
      const tokens = info.split(/\s+/).filter(Boolean);
      const lang = tokens[0] || 'text';
      const file = tokens.slice(1).join(' ');
      body += '<figure class="code"><figcaption><span>' + escapeHtml(file || lang) + '</span><span class="lang">' + escapeHtml(lang) + '</span></figcaption><pre>' + escapeHtml(code.join('\n')) + '</pre></figure>\n';
      continue;
    }

    /* headings */
    const heading = line.match(/^(#{1,6})\s+(.*)$/);
    if (heading) {
      const level = heading[1].length;
      const text = heading[2].replace(/\s*#+\s*$/, '');
      if (level === 1 && !sawH1 && sectionCount === 0 && !options.title) {
        /* Without an explicit title, the first H1 is the page title. */
        sawH1 = true;
        title = plain(text);
      } else if (level === 1) addHeading(2, text);
      else if (level === 2) addHeading(options.book ? 3 : 2, text);
      else if (level === 3) addHeading(options.book ? 4 : 3, text);
      else if (level === 4) addHeading(options.book ? 5 : 4, text);
      else addHeading(5, text);
      i++;
      continue;
    }

    /* horizontal rule */
    if (/^\s{0,3}(-{3,}|\*{3,}|_{3,})\s*$/.test(line)) {
      body += '<hr>\n'; i++; continue;
    }

    /* blockquote / callout */
    if (/^\s*>/.test(line)) {
      const inner = [];
      while (i < lines.length && /^\s*>/.test(lines[i])) {
        inner.push(lines[i].replace(/^\s*>\s?/, '')); i++;
      }
      body += renderCallout(inner);
      continue;
    }

    /* table */
    if (line.includes('|') && i + 1 < lines.length && /^\s*\|?[\s:|-]+\|?\s*$/.test(lines[i + 1]) && lines[i + 1].includes('-')) {
      const rows = [];
      while (i < lines.length && lines[i].includes('|') && lines[i].trim() !== '') {
        rows.push(lines[i]); i++;
      }
      body += renderTable(rows);
      continue;
    }

    /* unordered list */
    if (/^\s*[-*+]\s+/.test(line)) {
      const items = gatherList(lines, i, /^\s*[-*+]\s+/);
      i = items.next;
      body += '<ul>\n' + items.values.map((t) => `<li>${inline(t)}</li>`).join('\n') + '\n</ul>\n';
      continue;
    }

    /* ordered list */
    if (/^\s*\d+[.)]\s+/.test(line)) {
      const items = gatherList(lines, i, /^\s*\d+[.)]\s+/);
      i = items.next;
      body += '<ol>\n' + items.values.map((t) => `<li>${inline(t)}</li>`).join('\n') + '\n</ol>\n';
      continue;
    }

    /* paragraph: gather until a blank line or the start of another block */
    const para = [line];
    i++;
    while (i < lines.length && !/^\s*$/.test(lines[i])) {
      const nxt = lines[i];
      if (/^(#{1,6})\s+/.test(nxt)) break;
      if (/^(\s*)(`{3,}|~{3,})/.test(nxt)) break;
      if (/^\s*>/.test(nxt)) break;
      if (/^\s*[-*+]\s+/.test(nxt)) break;
      if (/^\s*\d+[.)]\s+/.test(nxt)) break;
      if (/^\s{0,3}(-{3,}|\*{3,}|_{3,})\s*$/.test(nxt)) break;
      para.push(nxt); i++;
    }
    body += `<p>${inline(para.join(' '))}</p>\n`;
  }

  closeSection();

  if (!title) title = basename(inputPath, extname(inputPath));

  return { body, toc, title, sectionCount };
}

function renderCallout(innerLines) {
  const text = innerLines.join('\n');
  const warn = /^\s*\*\*\s*(warning|caution|danger|alert)\b/i.test(text);
  let html = '<div class="callout' + (warn ? ' warn' : '') + '">';

  const blocks = text.split(/\n\s*\n/).map((b) => b.trim()).filter(Boolean);
  for (const block of blocks) {
    const lines = block.split('\n').filter((l) => l.trim() !== '');
    let j = 0;
    while (j < lines.length) {
      if (/^\s*[-*+]\s+/.test(lines[j])) {
        const items = [];
        while (j < lines.length && /^\s*[-*+]\s+/.test(lines[j])) {
          items.push(lines[j].replace(/^\s*[-*+]\s+/, '')); j++;
        }
        html += '<ul>' + items.map((t) => `<li>${inline(t)}</li>`).join('') + '</ul>';
      } else if (/^\s*\d+[.)]\s+/.test(lines[j])) {
        const items = [];
        while (j < lines.length && /^\s*\d+[.)]\s+/.test(lines[j])) {
          items.push(lines[j].replace(/^\s*\d+[.)]\s+/, '')); j++;
        }
        html += '<ol>' + items.map((t) => `<li>${inline(t)}</li>`).join('') + '</ol>';
      } else {
        const para = [];
        while (j < lines.length && !/^\s*[-*+]\s+/.test(lines[j]) && !/^\s*\d+[.)]\s+/.test(lines[j])) {
          para.push(lines[j]); j++;
        }
        html += `<p>${inline(para.join(' '))}</p>`;
      }
    }
  }

  return html + '</div>\n';
}

function splitRow(row) {
  let s = row.trim();
  if (s.startsWith('|')) s = s.slice(1);
  if (s.endsWith('|')) s = s.slice(0, -1);
  return s.split('|').map((c) => c.trim());
}

function renderTable(rows) {
  const header = splitRow(rows[0]);
  const aligns = splitRow(rows[1]).map((c) => {
    const left = c.startsWith(':');
    const right = c.endsWith(':');
    if (left && right) return 'center';
    if (right) return 'right';
    return 'left';
  });

  let html = '<div class="table-wrap"><table>\n<thead><tr>';
  header.forEach((cell, idx) => {
    html += `<th style="text-align:${aligns[idx] || 'left'}">${inline(cell)}</th>`;
  });
  html += '</tr></thead>\n<tbody>\n';
  rows.slice(2).forEach((row) => {
    html += '<tr>';
    splitRow(row).forEach((cell, idx) => {
      html += `<td style="text-align:${aligns[idx] || 'left'}">${inline(cell)}</td>`;
    });
    html += '</tr>\n';
  });
  html += '</tbody></table></div>\n';
  return html;
}

/* ------------------------------------------------------------------ */
/* page shell                                                          */
/* ------------------------------------------------------------------ */

function tocLink(entry) {
  const n = entry.level === 2 ? pad(Number(entry.id.replace(/^s/, ''))) : '';
  return `      <a href="#${entry.id}" class="l${entry.level}"><span class="n">${n}</span><span>${escapeHtml(entry.label)}</span></a>`;
}

const THEME_BOOTSTRAP = `<script>
(function () {
  try {
    var saved = JSON.parse(localStorage.getItem('mca-site-customiser:v2')) || {};
    var mode = saved.mode === 'light' || saved.mode === 'dark' ? saved.mode : 'auto';
    var dark = mode === 'dark' || (mode === 'auto' && window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches);
    document.documentElement.setAttribute('data-theme', dark ? 'dark' : 'light');
  } catch (e) { /* no stored preference */ }
})();
</script>`;

function buildPage(parsed, options) {
  const css = readFileSync(join(ASSETS, 'explainer.css'), 'utf8');
  const js = readFileSync(join(ASSETS, 'explainer.js'), 'utf8');
  const rel = (file) => relative(dirname(outputPath), join(ASSETS, file)).split('\\').join('/');

  const cssTag = options.link ? `<link rel="stylesheet" href="${rel('explainer.css')}">` : `<style>\n${css}\n</style>`;
  const jsTag = options.link ? `<script src="${rel('explainer.js')}"></script>` : `<script>\n${js}\n</script>`;

  const title = escapeHtml(parsed.title);
  const eyebrow = escapeHtml(options.eyebrow || 'Reading guide');
  const lede = escapeHtml(options.lede || `Converted from ${sourceName}.`);
  const kicker = escapeHtml(options.kicker || 'explainer');
  const sideSub = escapeHtml(options.lede || 'A styled explainer page.');
  const count = parsed.sectionCount;
  const toc = parsed.toc.map(tocLink).join('\n');
  const metaItems = options.meta
    ? options.meta.split('|').map((item) => item.trim()).filter(Boolean)
    : [`${count} section${count === 1 ? '' : 's'}`, 'generated page'];
  const metaHtml = metaItems
    .map((item) => `<span>${escapeHtml(item)}</span>`)
    .join('\n          ');
  const footText = options.foot || `Built from ${sourceName}`;
  const colophonText = options.colophon || `Built from ${sourceName} \u00b7 ${count} section${count === 1 ? '' : 's'} \u00b7 explainer series`;

  return `<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>${title}</title>
${cssTag}
${THEME_BOOTSTRAP}
</head>
<body>
<div class="progress"><span id="bar"></span></div>
<div class="shell">

  <aside class="sidebar">
    <a class="side-kicker" href="#top">${kicker} &middot; explainer</a>
    <p class="side-title">${title}</p>
    <p class="side-sub">${sideSub}</p>
    <div class="side-rule"></div>
    <p class="side-label">Contents</p>
    <nav class="toc" id="toc">
${toc}
    </nav>
    <div class="side-foot">
      ${escapeHtml(footText)}
    </div>
  </aside>

  <main class="pane" id="top">
    <div class="inner">
      <header class="page-heading">
        <p class="eyebrow">${eyebrow}</p>
        <h1>${title}</h1>
        <p class="lede">${lede}</p>
        <p class="meta">
          ${metaHtml}
        </p>
      </header>

${parsed.body}
      <div class="colophon">
        ${escapeHtml(colophonText)}
      </div>
    </div>
  </main>
</div>

${jsTag}
</body>
</html>
`;
}

/* ------------------------------------------------------------------ */

const markdown = readFileSync(inputPath, 'utf8');
const parsed = parseMarkdown(markdown, opts);
const html = buildPage(parsed, opts);
writeFileSync(outputPath, html, 'utf8');
console.log(`Wrote ${relative(process.cwd(), outputPath) || outputPath} (${parsed.sectionCount} sections, ${opts.link ? 'linked assets' : 'self-contained'})`);
