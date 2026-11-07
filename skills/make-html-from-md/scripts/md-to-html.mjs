#!/usr/bin/env node
/**
 * Convert a long-form markdown file into a reading-guide HTML page
 * styled like sandbox-guide.html in the same directory.
 */
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));

function mdToHtml(md) {
  let html = '';
  const lines = md.split(/\r?\n/);
  let i = 0;
  let sectionOpen = false;
  let inCode = false;
  let codeLang = '';
  let codeCaption = '';
  let codeBuffer = [];
  let inTable = false;
  let tableBuffer = [];
  let inList = false;
  let listType = null; // 'ul' or 'ol'
  let listBuffer = [];
  let inBlockquote = false;
  let bqBuffer = [];

  function flushCode() {
    if (!inCode || codeBuffer.length === 0) return;
    const body = escapeHtml(codeBuffer.join('\n'));
    const cap = codeCaption ? `<figcaption><span>${codeCaption}</span><span class="lang">${codeLang || 'text'}</span></figcaption>` : '';
    html += `\n<figure class="code">${cap}<pre>${body}</pre></figure>\n`;
    codeBuffer = [];
    inCode = false;
    codeLang = '';
    codeCaption = '';
  }

  function flushTable() {
    if (!inTable || tableBuffer.length === 0) return;
    const rows = tableBuffer.map((row, idx) => {
      const cells = row.split('|').map(c => c.trim()).filter(c => c !== '');
      if (idx === 1) return ''; // separator row
      const tag = idx === 0 ? 'th' : 'td';
      return `<tr>${cells.map(c => `<${tag}>${inline(c)}</${tag}>`).join('')}</tr>`;
    }).filter(Boolean);
    html += `\n<div class="table-wrap"><table>\n${rows.join('\n')}\n</table></div>\n`;
    tableBuffer = [];
    inTable = false;
  }

  function flushList() {
    if (!inList || listBuffer.length === 0) return;
    const items = listBuffer.map(item => `<li>${inline(item)}</li>`).join('\n');
    html += `\n<${listType}>\n${items}\n</${listType}>\n`;
    listBuffer = [];
    inList = false;
    listType = null;
  }

  // A callout may contain paragraphs AND lists. Joining every quoted line into
  // one string turned `> - item` bullets into a literal "- item" paragraph, so
  // the body is parsed here: blank quoted lines split paragraphs, `-`/`*` and
  // `1.` lines become real <ul>/<ol> lists, everything else is inline text.
  function renderCalloutBody(lines) {
    const blocks = [];
    let paragraph = [];
    let list = null; // { type: 'ul' | 'ol', items: string[] }

    const flushParagraph = () => {
      if (!paragraph.length) return;
      blocks.push(`<p>${inline(paragraph.join(' '))}</p>`);
      paragraph = [];
    };

    const flushCalloutList = () => {
      if (!list) return;
      const items = list.items.map(item => `<li>${inline(item)}</li>`).join('\n');
      blocks.push(`<${list.type}>\n${items}\n</${list.type}>`);
      list = null;
    };

    for (const entry of lines) {
      const text = String(entry ?? '');
      if (text.trim() === '') {
        flushParagraph();
        flushCalloutList();
        continue;
      }

      const ulItem = text.match(/^\s*[-*]\s+(.+)$/);
      const olItem = text.match(/^\s*\d+\.\s+(.+)$/);
      if (ulItem || olItem) {
        flushParagraph();
        const type = ulItem ? 'ul' : 'ol';
        if (list && list.type !== type) flushCalloutList();
        if (!list) list = { type, items: [] };
        list.items.push(ulItem ? ulItem[1] : olItem[1]);
        continue;
      }

      flushCalloutList();
      paragraph.push(text.trim());
    }

    flushParagraph();
    flushCalloutList();
    return blocks.join('\n');
  }

  function flushBlockquote() {
    if (!inBlockquote || bqBuffer.length === 0) return;
    const content = renderCalloutBody(bqBuffer);
    html += `\n<div class="callout">${content}</div>\n`;
    bqBuffer = [];
    inBlockquote = false;
  }

  function closeSection() {
    flushCode();
    flushTable();
    flushList();
    flushBlockquote();
    if (sectionOpen) {
      html += '\n</section>\n';
      sectionOpen = false;
    }
  }

  function escapeHtml(str) {
    return str.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
  }

  function inline(str) {
    // Escape HTML first
    let s = escapeHtml(str);
    // Bold
    s = s.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
    // Italic (not inside code tags)
    s = s.replace(/(^|[^*])\*(?!\*)(.+?)\*([^*]|$)/g, '$1<em>$2</em>$3');
    // Code inline
    s = s.replace(/`([^`]+)`/g, '<code>$1</code>');
    // Links
    s = s.replace(/\[([^\]]+)\]\(([^)]+)\)/g, '<a href="$2">$1</a>');
    return s;
  }

  const headings = [];
  let h2Counter = 0;
  let h3Counter = 0;
  let h4Counter = 0;
  let skippingToc = false;

  while (i < lines.length) {
    const raw = lines[i];
    const line = raw; // keep original for code blocks

    // Strip embedded markdown Table of Contents from the content pane
    // (the sidebar already provides a generated TOC)
    if (skippingToc) {
      if (/^#{1,2}\s/.test(line)) {
        skippingToc = false;
      } else {
        i++;
        continue;
      }
    }

    // Code block
    if (line.startsWith('```')) {
      if (!inCode) {
        flushList();
        flushBlockquote();
        inCode = true;
        const rest = line.slice(3).trim();
        codeLang = rest;
        codeCaption = '';
      } else {
        flushCode();
      }
      i++;
      continue;
    }
    if (inCode) {
      codeBuffer.push(raw);
      i++;
      continue;
    }

    // Horizontal rule: close section only if the next non-empty line is a top-level heading
    if (/^---+\s*$/.test(line)) {
      let j = i + 1;
      while (j < lines.length && lines[j].trim() === '') j++;
      const nextIsH1 = j < lines.length && /^#\s+/.test(lines[j]);
      if (nextIsH1) closeSection();
      else flushList();
      html += '\n<hr>\n';
      i++;
      continue;
    }

    // Blockquote
    if (line.startsWith('>')) {
      if (!inBlockquote) flushList();
      inBlockquote = true;
      bqBuffer.push(line.replace(/^>\s?/, ''));
      i++;
      continue;
    } else if (inBlockquote && line.trim() === '') {
      flushBlockquote();
      i++;
      continue;
    }

    // Table
    if (line.trim().startsWith('|')) {
      if (!inTable) {
        flushList();
        inTable = true;
      }
      tableBuffer.push(line.trim());
      i++;
      continue;
    } else if (inTable) {
      flushTable();
    }

    // FAQ dropdown: preserve raw <details>/<summary> blocks, but render the
    // answer Markdown inside so backticks and bold work like the rest of the page.
    if (/^<details\b/i.test(line.trim())) {
      flushList();
      flushBlockquote();
      const block = [];
      let k = i;
      while (k < lines.length) {
        block.push(lines[k]);
        if (/<\/details>/i.test(lines[k])) break;
        k++;
      }

      let summary = '';
      const content = [];
      let paragraph = [];
      const flushParagraph = () => {
        if (!paragraph.length) return;
        content.push(`<p>${inline(paragraph.join(' '))}</p>`);
        paragraph = [];
      };

      for (const entry of block) {
        const trimmed = entry.trim();
        const summaryMatch = trimmed.match(/^<summary>(.*)<\/summary>$/i);
        if (summaryMatch) {
          summary = summaryMatch[1];
          continue;
        }
        if (/^<\/?details\b/i.test(trimmed)) continue;
        if (trimmed === '') {
          flushParagraph();
          continue;
        }
        paragraph.push(trimmed);
      }
      flushParagraph();

      html += `\n<details class="faq">\n<summary>${summary}</summary>\n${content.join('\n')}\n</details>\n`;
      i = k + 1;
      continue;
    }

    // Headings
    const h1Match = line.match(/^#\s+(.+)$/);
    const h2Match = line.match(/^##\s+(.+)$/);
    const h3Match = line.match(/^###\s+(.+)$/);
    const h4Match = line.match(/^####\s+(.+)$/);

    if (h1Match) {
      closeSection();
      h2Counter++;
      h3Counter = 0;
      h4Counter = 0;
      const text = inline(h1Match[1]);
      const id = 's' + String(h2Counter).padStart(2, '0');
      headings.push({ level: 2, text: h1Match[1], id });
      html += `\n<section id="${id}">\n<h2><span class="num">${String(h2Counter).padStart(2, '0')}</span><span>${text}</span></h2>\n`;
      sectionOpen = true;
      i++;
      continue;
    }
    if (h2Match) {
      const headingText = h2Match[1].trim();
      if (/^table of contents$/i.test(headingText)) {
        closeSection();
        skippingToc = true;
        i++;
        continue;
      }
      flushList();
      flushBlockquote();
      h3Counter++;
      h4Counter = 0;
      const text = inline(headingText);
      const id = 's' + String(h2Counter).padStart(2, '0') + '-' + String(h3Counter).padStart(2, '0');
      headings.push({ level: 3, text: headingText, id });
      html += `\n<h3 id="${id}">${text}</h3>\n`;
      i++;
      continue;
    }
    if (h3Match) {
      flushList();
      h4Counter++;
      const text = inline(h3Match[1]);
      const id = 's' + String(h2Counter).padStart(2, '0') + '-' + String(h3Counter).padStart(2, '0') + '-' + String(h4Counter).padStart(2, '0');
      headings.push({ level: 4, text: h3Match[1], id });
      html += `\n<h4 id="${id}">${text}</h4>\n`;
      i++;
      continue;
    }
    if (h4Match) {
      flushList();
      html += `\n<h5>${inline(h4Match[1])}</h5>\n`;
      i++;
      continue;
    }

    // Lists
    const ulMatch = line.match(/^(\s*)[-*]\s+(.+)$/);
    const olMatch = line.match(/^(\s*)\d+\.\s+(.+)$/);
    if (ulMatch || olMatch) {
      const isUl = !!ulMatch;
      const content = ulMatch ? ulMatch[2] : olMatch[2];
      const newType = isUl ? 'ul' : 'ol';
      if (inList && listType !== newType) {
        flushList();
      }
      inList = true;
      listType = newType;
      listBuffer.push(content);
      i++;
      continue;
    } else if (inList && (line.trim() === '' || (!ulMatch && !olMatch && !line.startsWith(' ')))) {
      flushList();
    }

    // Empty line
    if (line.trim() === '') {
      flushBlockquote();
      i++;
      continue;
    }

    // Paragraph
    flushList();
    flushBlockquote();
    html += `\n<p>${inline(line)}</p>\n`;
    i++;
  }

  closeSection();
  return { html, headings };
}

function buildPage({ title, eyebrow, h1, lede, meta, tocTitle, sideSub, sideFoot, sideKicker, colophon, contentHtml, headings }) {
  const numPad = (n) => String(n).padStart(2, '0');

  let secNum = 0;
  const toc = headings.map((h) => {
    let numText = '';
    let levelClass = '';
    if (h.level === 2) {
      secNum++;
      numText = numPad(secNum);
      levelClass = 'l2';
    } else if (h.level === 3) {
      levelClass = 'l3';
    } else if (h.level === 4) {
      levelClass = 'l4';
    }
    const tocText = h.text.replace(/`/g, '');
    return `      <a href="#${h.id}" class="${levelClass}"><span class="n">${numText}</span><span>${escapeXml(tocText)}</span></a>`;
  }).join('\n');

  const metaTags = (meta || []).map(m => `          <span>${escapeXml(m)}</span>`).join('\n');

  return `<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>${escapeXml(title)}</title>
<style>
html{font-size:var(--root-size,24px)}

:root{
  --paper:#f0eee6; --surface:#fbfaf7; --ivory:#fffdfa; --ink:#1f1e1d;
  --prose:#33302c; --muted:#55524c; --stone:#8c877c;
  --line:#e0dbcf; --line-soft:#e9e4d8; --tint:#f6ede6;
  --terra:#d97757; --terra-dark:#c9633f; --amber:#b9862f;
  --code-bg:#23211e; --code-bar:#2b2823; --code-line:#3a3732;
  --code-ink:#f2ece1; --code-dim:#a9a294; --code-accent:#f0b49a;
  --sidebar:19.25rem; --measure:46rem;
  --sans:-apple-system,'Segoe UI',Inter,Helvetica,Arial,sans-serif;
  --serif:'Iowan Old Style',Palatino,'Palatino Linotype','Book Antiqua',Georgia,serif;
  --mono:'JetBrains Mono','Fira Code',ui-monospace,SFMono-Regular,Consolas,monospace;
}
html[data-theme="dark"]{
  --paper:#14171b; --surface:#1b1f24; --ivory:#232830; --ink:#eef2f6;
  --prose:#c7d0d8; --muted:#9aa7b4; --stone:#7f8c99;
  --line:#303944; --line-soft:#263039; --tint:#252f3b;
  --terra:#e08a6a; --terra-dark:#eda07e; --amber:#d3a44a;
  --code-bg:#111418; --code-bar:#181d22; --code-line:#2b343e;
  --code-ink:#eef2f6; --code-dim:#8f9ba7; --code-accent:#f0b49a;
}
*{box-sizing:border-box}
html{scroll-behavior:smooth}
body{
  margin:0; background:var(--paper); color:var(--prose);
  font:1.03125rem/var(--lh-body,1.66) var(--sans);
  -webkit-font-smoothing:antialiased;
}
::selection{background:#f0d3c6; color:#2a2622}
html[data-theme="dark"] ::selection{background:#4a2f28; color:#f2ece1}

/* ---------- shell ---------- */
.shell{display:grid; grid-template-columns:var(--sidebar) minmax(0,1fr); align-items:start}
.sidebar{
  position:sticky; top:0; height:100vh; overflow-y:auto; overscroll-behavior:contain;
  scrollbar-width:thin; scrollbar-color:#cec6b5 transparent;
  padding:1.625rem 1.125rem 2.125rem 1.375rem;
  border-right:0.0625rem solid var(--line);
  background:linear-gradient(180deg,#f4f1e9,#efece3 60%,#ece8de);
}
html[data-theme="dark"] .sidebar{
  scrollbar-color:#3a4652 transparent;
  background:linear-gradient(180deg,#1d2228,#191e23 60%,#171b20);
}
.side-kicker{
  display:block; margin:0 0 0.625rem; color:var(--terra-dark);
  font:600 0.65625rem/1.3 var(--sans); letter-spacing:.14em; text-transform:uppercase; text-decoration:none;
}
.side-title{
  margin:0; color:var(--ink); font:500 1.3125rem/1.2 var(--serif); letter-spacing:-.01em;
}
.side-sub{margin:0.375rem 0 0; color:var(--stone); font-size:0.7875rem; line-height:1.45}
.side-rule{height:0.0625rem; margin:1.125rem 0 0.875rem; background:var(--line)}
.side-label{
  margin:0 0 0.375rem; color:var(--stone);
  font:600 0.65625rem/1.3 var(--sans); letter-spacing:.13em; text-transform:uppercase;
}
.toc{display:flex; flex-direction:column; gap:0.0625rem}
.toc a{
  display:flex; gap:0.5625rem; align-items:baseline;
  padding:0.375rem 0.5625rem 0.375rem 0.625rem; border-left:0.125rem solid transparent; border-radius:0 0.4375rem 0.4375rem 0;
  color:var(--muted); font-size:0.8375rem; line-height:1.4; text-decoration:none;
  transition:background .14s,color .14s,border-color .14s;
}
.toc a .n{color:#a9a294; font:0.6875rem/1 var(--mono); flex:0 0 1.125rem}
.toc a:hover{background:#e8e3d6; color:var(--ink)}
html[data-theme="dark"] .toc a .n{color:#7f8c99}
html[data-theme="dark"] .toc a:hover{background:#252f3b}
.toc a.active{background:var(--tint); border-left-color:var(--terra); color:var(--ink); font-weight:600}
.toc a.active .n{color:var(--terra-dark)}
.toc a.l3{padding-left:1.25rem; font-size:0.78rem}
.toc a.l4{padding-left:1.85rem; font-size:0.73rem}
.toc a.l3 .n,
.toc a.l4 .n{display:none}
html[data-theme="dark"] .toc a.l3:hover,
html[data-theme="dark"] .toc a.l4:hover{background:#222930}
.side-foot{
  margin-top:1.25rem; padding-top:0.875rem; border-top:0.0625rem solid var(--line);
  color:var(--stone); font-size:0.7375rem; line-height:1.6;
}
.side-foot code{font-size:0.6875rem}

.progress{position:fixed; top:0; left:var(--sidebar); right:0; height:0.125rem; z-index:40; background:transparent}
.progress span{display:block; height:100%; width:0; background:var(--terra); transition:width .1s linear}

.sidebar::-webkit-scrollbar{width:0.4375rem}
.sidebar::-webkit-scrollbar-thumb{background:#d5ccbb; border-radius:0.5rem}
html[data-theme="dark"] .sidebar::-webkit-scrollbar-thumb{background:#3a4652}
.sidebar::-webkit-scrollbar-track{background:transparent}

/* ---------- content pane ---------- */
.pane{padding:3.25rem 3.5rem 8.75rem; min-width:0}
.inner{max-width:var(--measure); margin:0 auto}

.page-heading{margin:0 0 2.125rem; padding-bottom:1.75rem; border-bottom:0.0625rem solid var(--line)}
.page-heading .eyebrow{
  margin:0 0 0.75rem; color:var(--terra-dark);
  font:600 0.6875rem/1.3 var(--sans); letter-spacing:.15em; text-transform:uppercase;
}
h1{
  margin:0; color:var(--ink); font:500 clamp(2.125rem,4vw,2.875rem)/1.1 var(--serif); letter-spacing:-.02em;
}
.page-heading .lede{margin:0.875rem 0 0; color:var(--muted); font-size:1.09375rem; max-width:38rem}
.meta{
  margin:1.25rem 0 0; display:flex; flex-wrap:wrap; gap:0.25rem 0.6875rem;
  color:var(--stone); font:0.7rem/1.6 var(--mono);
}
.meta span::before{content:"\\00b7"; margin-right:0.6875rem; color:#c3bcae}
html[data-theme="dark"] .meta span::before{color:#4a5560}
.meta span:first-child::before{content:none; margin:0}

section{padding-top:0.375rem; margin:0 0 2.75rem}
section:first-of-type h2{margin-top:0}
h2{
  display:flex; gap:0.8125rem; align-items:baseline;
  margin:2.375rem 0 0.875rem; color:var(--ink);
  font:500 1.65625rem/1.22 var(--serif); letter-spacing:-.015em;
  scroll-margin-top:1.625rem;
}
h2 .num{
  flex:0 0 auto; color:var(--terra); padding-top:0.125rem;
  font:600 0.71875rem/1 var(--mono); letter-spacing:.06em;
}
h3{
  margin:1.875rem 0 0.625rem; color:var(--ink);
  font:600 0.96875rem/1.4 var(--sans); letter-spacing:.005em;
}
h4{
  margin:1.5rem 0 0.5rem; color:var(--ink);
  font:600 0.85rem/1.35 var(--sans); letter-spacing:.005em;
}
h5{
  margin:1.25rem 0 0.4rem; color:var(--ink);
  font:600 0.8rem/1.3 var(--sans); letter-spacing:.005em;
}
p{margin:0 0 0.875rem}
p + p{margin-top:-0.125rem}
strong{color:var(--ink); font-weight:600}
em{font-style:italic; color:var(--ink)}
a{color:var(--terra-dark); text-decoration-thickness:0.0625rem; text-underline-offset:0.125rem}

ul{margin:0 0 1rem; padding-left:0; list-style:none}
ol{margin:0 0 1rem; padding-left:0; list-style:none; counter-reset:item}
ol li{position:relative; margin:0 0 0.625rem; padding-left:1.5rem}
ol li::before{
  content:counter(item) "."; counter-increment:item; position:absolute; left:0.1875rem; top:0;
  color:var(--terra); font:600 0.7rem/1 var(--mono);
}
ul li{position:relative; margin:0 0 0.625rem; padding-left:1.25rem}
ul li::before{
  content:""; position:absolute; left:0.1875rem; top:.66em;
  width:0.375rem; height:0.375rem; border-radius:50%; background:#d8b6a6;
}
html[data-theme="dark"] ul li::before{background:#8a5a48}
li strong{color:var(--ink)}

code{
  padding:.12em .38em; border-radius:0.3125rem; background:#e9e4d7; color:#7c3f2b;
  font:.855em/1.5 var(--mono); word-break:break-word;
}
html[data-theme="dark"] code{background:#2b2521; color:#f0b49a}

/* ---------- callouts ---------- */
.callout{
  margin:1.25rem 0 1.375rem; padding:0.8125rem 1.0625rem 0.875rem;
  border-left:0.1875rem solid var(--terra); border-radius:0 0.5625rem 0.5625rem 0;
  background:var(--tint); color:#4b4741; font-size:0.925rem; line-height:1.62;
}
.callout strong{color:var(--ink)}
.callout p{margin:0.55em 0 0}
.callout p:first-child{margin-top:0}
.callout ul,.callout ol{margin:0.55em 0 0.2em 1.15em}
.callout li{margin:0 0 0.35em}
.callout li:last-child{margin-bottom:0}
.callout.warn{border-left-color:var(--amber); background:#f7f0da; color:#4e4734}
html[data-theme="dark"] .callout{color:var(--prose)}
html[data-theme="dark"] .callout.warn{background:#2e2a1e; color:#d8cfb8}

/* ---------- FAQ dropdowns ---------- */
details.faq{
  margin:0.75rem 0 1rem; border:0.0625rem solid var(--line);
  border-radius:0.5625rem; background:var(--surface); overflow:hidden;
}
details.faq summary{
  cursor:pointer; padding:0.6875rem 0.875rem; color:var(--ink);
  font-weight:600; line-height:1.45; list-style:none;
}
details.faq summary::-webkit-details-marker{display:none}
details.faq summary::before{
  content:'▸'; display:inline-block; width:1.15em; color:var(--terra-dark);
  transition:transform .15s;
}
details.faq[open] summary::before{content:'▾'}
details.faq[open] summary{border-bottom:0.0625rem solid var(--line-soft)}
details.faq > p{
  margin:0; padding:0.75rem 0.875rem 0.875rem 1.9rem;
  color:var(--prose); font-size:0.925rem; line-height:1.62;
}
html[data-theme="dark"] details.faq summary{color:var(--ink)}
html[data-theme="dark"] details.faq > p{color:var(--prose)}

/* ---------- code ---------- */
figure.code, figure.ascii{margin:1.125rem 0 1.375rem; border-radius:0.6875rem; overflow:hidden}
figure.code{margin-left:-1.375rem; margin-right:-1.375rem}
figure.code{background:var(--code-bg); border:0.0625rem solid #34312b; box-shadow:0 0.125rem 0.625rem rgba(31,30,29,.07)}
html[data-theme="dark"] figure.code{border-color:#2b343e; box-shadow:0 0.125rem 0.625rem rgba(0,0,0,.28)}
figure.code figcaption{
  display:flex; justify-content:space-between; gap:0.75rem; align-items:center;
  padding:0.5rem 0.875rem; background:var(--code-bar); border-bottom:0.0625rem solid var(--code-line);
  color:var(--code-accent); font:0.7125rem/1.4 var(--mono); letter-spacing:.02em;
}
figure.code figcaption .lang{color:#7d776b; font-size:0.6625rem; letter-spacing:.1em; text-transform:uppercase}
html[data-theme="dark"] figure.code figcaption .lang{color:#8f9ba7}
figure.code pre{
  margin:0; padding:0.9375rem 1.125rem 1.0625rem; overflow-x:auto;
  color:var(--code-ink); font:var(--fs-code,0.775rem)/1.66 var(--mono); tab-size:2;
  white-space:pre-wrap; overflow-wrap:break-word;
}
figure.ascii{
  border:0.0625rem dashed #d3ccbb; background:#f7f4ec;
}
html[data-theme="dark"] figure.ascii{border-color:#3a4652; background:#1b2026}
figure.ascii figcaption{
  padding:0.4375rem 0.875rem 0; color:var(--stone);
  font:600 0.65rem/1.4 var(--sans); letter-spacing:.12em; text-transform:uppercase;
}
figure.ascii pre{
  margin:0; padding:0.6875rem 0.875rem 0.9375rem; overflow-x:auto;
  color:#4c483f; font:0.76875rem/1.55 var(--mono); white-space:pre;
}
html[data-theme="dark"] figure.ascii pre{color:#c7d0d8}

/* ---------- tables ---------- */
.table-wrap{margin:1rem 0 1.375rem; overflow-x:auto; scrollbar-width:thin; scrollbar-color:#cec6b5 transparent}
.table-wrap::-webkit-scrollbar{height:0.4375rem}
.table-wrap::-webkit-scrollbar-thumb{background:#d5ccbb; border-radius:0.5rem}
html[data-theme="dark"] .table-wrap{scrollbar-color:#3a4652 transparent}
html[data-theme="dark"] .table-wrap::-webkit-scrollbar-thumb{background:#3a4652}
table{width:100%; border-collapse:collapse; font-size:0.875rem; line-height:1.5}
thead th{
  padding:0 0.75rem 0.5rem 0; border-bottom:0.0625rem solid var(--line); text-align:left;
  color:var(--stone); font:600 0.6625rem/1.3 var(--sans); letter-spacing:.09em; text-transform:uppercase;
}
tbody td{padding:0.625rem 0.75rem 0.625rem 0; border-bottom:0.0625rem solid var(--line-soft); vertical-align:top; color:var(--muted)}
tbody tr:last-child td{border-bottom:none}
tbody td:first-child{color:var(--ink)}
tbody td code{font-size:0.75rem}
tbody td:first-child{white-space:nowrap}
.tag{
  display:inline-block; margin-left:0.375rem; padding:0.0625rem 0.375rem; border-radius:1.25rem;
  background:#f0dcd2; color:#9a4d31; font:600 0.6rem/1.5 var(--sans); letter-spacing:.08em; text-transform:uppercase;
}
html[data-theme="dark"] .tag{background:#3a2a24; color:#f0b49a}

.table-wrap.dense table{font-size:0.8125rem}
.table-wrap.dense tbody td, .table-wrap.dense td code{white-space:normal; overflow-wrap:anywhere}
.table-wrap.dense tbody td{padding-right:0.625rem}
.table-wrap.dense tbody td:first-child{min-width:8.5rem}

/* ---------- footer ---------- */
.colophon{
  margin-top:3.5rem; padding-top:1.125rem; border-top:0.0625rem solid var(--line);
  color:var(--stone); font-size:0.775rem; line-height:1.7;
}
.colophon code{font-size:0.7rem}

/* ---------- narrow ---------- */
@media (max-width: 940px){
  .shell{grid-template-columns:1fr}
  .sidebar{position:static; height:auto; border-right:none; border-bottom:0.0625rem solid var(--line); padding:1.375rem 1.25rem 1.125rem}
  .toc{flex-direction:row; flex-wrap:wrap; gap:0.25rem 0.375rem}
  .toc a{padding:0.3125rem 0.5625rem; border-left:none; border-radius:0.4375rem; background:#eae5d8; font-size:0.775rem}
  html[data-theme="dark"] .toc a{background:#252f3b}
  .toc a .n{flex:0 0 auto}
  .toc a.active{border-left:none}
  .toc a.l3{font-size:0.74rem}
  .toc a.l4{font-size:0.70rem}
  .side-foot{display:none}
  .progress{left:0}
  .pane{padding:1.875rem 1.25rem 5.625rem}
  h2{font-size:1.4375rem}
  .table-wrap{margin-left:0; margin-right:0}
  figure.code{margin-left:0; margin-right:0}
  thead th{white-space:nowrap}
  tbody td, tbody td code{white-space:normal; overflow-wrap:anywhere}
}

/* ---------- print ---------- */
@media print{
  :root,html[data-theme="dark"]{ --paper:#fff !important; --surface:#fff !important; --ivory:#fff !important; --ink:#1f1e1d !important; --prose:#33302c !important; --muted:#44423d !important; --stone:#6b675f !important; --line:#d8d3c8 !important; --line-soft:#e8e4da !important; --tint:#f8f2ec !important; --terra:#c9633f !important; --terra-dark:#a14e2f !important; --amber:#8a6420 !important; --code-bg:#f6f4ef !important; --code-bar:#efece3 !important; --code-line:#ddd8cc !important; --code-ink:#26241f !important; --code-dim:#6b675f !important; --code-accent:#8f3f27}

  .sidebar,.progress{display:none}
  .shell{display:block}
  .pane{padding:0}
  body{background:#fff; font-size:10.5pt}
  h2{break-after:avoid} figure,table,.callout,details.faq{break-inside:avoid}
  figure.code{margin-left:0; margin-right:0}
  a{color:inherit; text-decoration:none}
}
/* ---------- appearance panel (the rounded "Aa" button, top right) ---------- */

#stylebtn{
  position:fixed; z-index:60; right:18px; top:18px; bottom:auto;
  display:grid; place-items:center; width:46px; height:46px; padding:0;
  border:1px solid var(--line); border-radius:50%;
  background:var(--surface); color:var(--ink);
  box-shadow:0 6px 22px rgba(31,30,29,.16);
  font:500 15px/1 var(--serif); cursor:pointer;
  transition:border-color .14s, color .14s, transform .14s;
}
#stylebtn:hover{border-color:var(--terra); color:var(--terra-dark); transform:translateY(-1px)}
#stylebtn:focus-visible{outline:2px solid var(--terra); outline-offset:2px}
#stylebtn[aria-expanded="true"]{border-color:var(--terra); color:var(--terra-dark)}

#stylepanel{
  position:fixed; z-index:61; right:18px; top:76px; bottom:auto;
  display:flex; flex-direction:column; width:372px;
  max-height:calc(100vh - 94px);
  border:1px solid var(--line); border-radius:14px;
  background:var(--surface); color:var(--ink);
  box-shadow:0 18px 50px rgba(31,30,29,.24);
  font:12.5px/1.45 var(--sans);
}
#stylepanel[hidden]{display:none}

.sp-head{
  display:flex; align-items:center; gap:8px;
  padding:11px 13px; border-bottom:1px solid var(--line-soft);
}
.sp-head h2{margin:0; padding:0; border:0; display:block; font:600 13px/1.2 var(--sans); color:var(--ink)}
.sp-head h2::before{content:none}

.sp-head select,.sp-foot button{
  padding:5px 9px; border:1px solid var(--line); border-radius:7px;
  background:var(--ivory); color:var(--ink);
  font:12.5px/1.3 var(--sans); cursor:pointer;
}
.sp-head select:focus-visible,.sp-foot button:focus-visible{outline:2px solid var(--terra); outline-offset:1px}

#sp-close{
  width:26px; height:26px; padding:0; border:1px solid transparent; border-radius:50%;
  background:none; color:var(--stone); font:14px/1 var(--sans); cursor:pointer;
}
#sp-close:hover{border-color:var(--line); color:var(--ink)}

.sp-body{padding:2px 13px 12px; overflow-x:hidden; overflow-y:auto; scrollbar-width:thin}

.sp-group{padding:11px 0; border-bottom:1px solid var(--line-soft)}
.sp-group:last-child{border-bottom:0}
.sp-group h3{
  margin:0 0 8px; color:var(--stone);
  font:700 9.5px/1.2 var(--sans); letter-spacing:.12em; text-transform:uppercase;
}
.sp-group h3 .tag{margin-left:6px; color:var(--terra-dark); letter-spacing:.04em; text-transform:none}

.sp-row{display:grid; grid-template-columns:1fr auto; gap:2px 10px; align-items:baseline; margin:9px 0}
.sp-row label{color:var(--muted)}
.sp-row > *{min-width:0}
.sp-row output{color:var(--ink); font-variant-numeric:tabular-nums; font-size:11.5px}
.sp-row input[type="range"]{grid-column:1/-1; width:100%; margin:3px 0 0; accent-color:var(--terra)}
.sp-row select{
  grid-column:1/-1; width:100%; margin-top:4px; padding:5px 8px;
  border:1px solid var(--line); border-radius:7px;
  background:var(--ivory); color:var(--ink); font:12px/1.4 var(--sans); cursor:pointer;
}
.sp-row select:focus-visible{outline:2px solid var(--terra); outline-offset:1px}

.sp-colors label{
  display:grid; grid-template-columns:26px 1fr auto; gap:8px; align-items:center; padding:2px 0;
}
.sp-colors .swatch-label{overflow:hidden; color:var(--muted); text-overflow:ellipsis; white-space:nowrap}
.sp-colors input[type="color"]{
  width:26px; height:22px; padding:0; border:1px solid var(--line); border-radius:6px;
  background:none; cursor:pointer;
}
.sp-colors .hex{color:var(--stone); font:11px/1 var(--mono)}

.sp-foot{
  display:flex; align-items:center; gap:8px;
  padding:10px 13px; border-top:1px solid var(--line-soft);
}
.sp-foot .spacer{flex:1}

@media (max-width:520px){
  #stylepanel{right:8px; left:8px; width:auto; top:72px; bottom:auto}
}

@media print{
  #stylebtn,#stylepanel{display:none !important}
}

</style>
<script>
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
    <a class="side-kicker" href="#top">${escapeXml(sideKicker || eyebrow)}</a>
    <p class="side-title">${escapeXml(tocTitle)}</p>
    <p class="side-sub">${escapeXml(sideSub)}</p>
    <div class="side-rule"></div>
    <p class="side-label">Contents</p>
    <nav class="toc" id="toc">
${toc}
    </nav>
    <div class="side-foot">
      ${sideFoot || ''}
    </div>
  </aside>

  <main class="pane" id="top">
    <div class="inner">
      <header class="page-heading">
        <p class="eyebrow">${escapeXml(eyebrow)}</p>
        <h1>${escapeXml(h1)}</h1>
        <p class="lede">${escapeXml(lede)}</p>
        <p class="meta">
${metaTags}
        </p>
      </header>

${contentHtml}

      <div class="colophon">
        ${colophon || `Built from <code>${path.basename(mdPath)}</code> &middot; ${headings.length} sections`}
      </div>
    </div>
  </main>
</div>

<script>
(function(){
  var toc = document.getElementById('toc');
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
<button id="stylebtn" type="button" aria-expanded="false" aria-controls="stylepanel"
        aria-label="Site customiser" title="Site customiser">Aa</button>

<aside id="stylepanel" hidden aria-label="Site customiser">
  <div class="sp-head">
    <h2>Site customiser</h2>
    <select id="sp-mode" aria-label="Colour mode">
      <option value="auto">System</option>
      <option value="light">Light</option>
      <option value="dark">Dark</option>
    </select>
    <button id="sp-close" type="button" aria-label="Close site customiser">&#10005;</button>
  </div>
  <div class="sp-body" id="sp-body"></div>
  <div class="sp-foot">
    <button id="sp-reset" type="button">Reset</button>
    <span class="spacer"></span>
    <button id="sp-copy" type="button">Copy CSS</button>
  </div>
</aside>

<script>
(function () {
  'use strict';

  /* ============================================================
     Site customiser - Light / Dark / System only.
     The page's CSS custom properties are the settings schema, so
     the panel can never drift from the stylesheet. Colours are kept
     per mode, and every control writes to both the TOC sidebar and
     the content pane because they share the same tokens.
     ============================================================ */

  var FONT_OPTIONS = {
    serif: [
      { label: 'Iowan / Palatino', value: "'Iowan Old Style',Palatino,'Palatino Linotype','Book Antiqua',Georgia,serif" },
      { label: 'Georgia', value: "Georgia,'Times New Roman',serif" },
      { label: 'Charter / Cambria', value: "Charter,'Bitstream Charter',Cambria,Georgia,serif" },
      { label: 'System serif', value: "ui-serif,'New York',Times,serif" }
    ],
    sans: [
      { label: 'System sans', value: "-apple-system,'Segoe UI',Inter,Helvetica,Arial,sans-serif" },
      { label: 'Inter / Helvetica', value: "Inter,'Helvetica Neue',Helvetica,Arial,sans-serif" },
      { label: 'Arial', value: "Arial,'Helvetica Neue',Helvetica,sans-serif" },
      { label: 'Verdana', value: "Verdana,Geneva,Tahoma,sans-serif" }
    ],
    mono: [
      { label: 'JetBrains Mono', value: "'JetBrains Mono','Fira Code',ui-monospace,SFMono-Regular,Consolas,monospace" },
      { label: 'SF Mono / Consolas', value: "ui-monospace,SFMono-Regular,'SF Mono',Menlo,Consolas,monospace" },
      { label: 'Consolas', value: "Consolas,'Courier New',monospace" },
      { label: 'Courier', value: "'Courier New',Courier,monospace" }
    ]
  };

  var SPEC = [
    { table: 'type', title: 'Type', items: [
      { key: 'root_size', cssVar: '--root-size', kind: 'number', unit: 'px', min: 16, max: 40, step: 0.5, def: 24, label: 'Text size' },
      { key: 'lh_body', cssVar: '--lh-body', kind: 'number', unit: '', min: 1.2, max: 2.2, step: 0.01, def: 1.66, label: 'Line height' },
      { key: 'fs_code', cssVar: '--fs-code', kind: 'number', unit: 'rem', min: 0.6, max: 1.2, step: 0.005, def: 0.775, label: 'Code size' }
    ] },
    { table: 'layout', title: 'Layout', items: [
      { key: 'sidebar', cssVar: '--sidebar', kind: 'number', unit: 'rem', min: 12, max: 30, step: 0.25, def: 19.25, label: 'Sidebar width' },
      { key: 'measure', cssVar: '--measure', kind: 'number', unit: 'rem', min: 30, max: 72, step: 1, def: 46, label: 'Reading column' }
    ] },
    { table: 'fonts', title: 'Fonts', items: [
      { key: 'serif', cssVar: '--serif', kind: 'font', options: FONT_OPTIONS.serif, def: FONT_OPTIONS.serif[0].value, label: 'Headings (serif)' },
      { key: 'sans', cssVar: '--sans', kind: 'font', options: FONT_OPTIONS.sans, def: FONT_OPTIONS.sans[0].value, label: 'Body (sans)' },
      { key: 'mono', cssVar: '--mono', kind: 'font', options: FONT_OPTIONS.mono, def: FONT_OPTIONS.mono[0].value, label: 'Code (mono)' }
    ] },
    { table: 'colors', title: 'Colours', colors: true, items: [
      { key: 'paper', cssVar: '--paper', kind: 'color', label: 'Page background' },
      { key: 'surface', cssVar: '--surface', kind: 'color', label: 'Sidebar / panel' },
      { key: 'ivory', cssVar: '--ivory', kind: 'color', label: 'Cards and inputs' },
      { key: 'ink', cssVar: '--ink', kind: 'color', label: 'Headings' },
      { key: 'prose', cssVar: '--prose', kind: 'color', label: 'Body text' },
      { key: 'muted', cssVar: '--muted', kind: 'color', label: 'Secondary text' },
      { key: 'stone', cssVar: '--stone', kind: 'color', label: 'Faint labels' },
      { key: 'line', cssVar: '--line', kind: 'color', label: 'Borders' },
      { key: 'line_soft', cssVar: '--line-soft', kind: 'color', label: 'Hairlines' },
      { key: 'tint', cssVar: '--tint', kind: 'color', label: 'Active nav' },
      { key: 'terra', cssVar: '--terra', kind: 'color', label: 'Accent' },
      { key: 'terra_dark', cssVar: '--terra-dark', kind: 'color', label: 'Links / eyebrow' },
      { key: 'amber', cssVar: '--amber', kind: 'color', label: 'Warnings' },
      { key: 'code_bg', cssVar: '--code-bg', kind: 'color', label: 'Code background' },
      { key: 'code_bar', cssVar: '--code-bar', kind: 'color', label: 'Code caption bar' },
      { key: 'code_line', cssVar: '--code-line', kind: 'color', label: 'Code border' },
      { key: 'code_ink', cssVar: '--code-ink', kind: 'color', label: 'Code text' },
      { key: 'code_dim', cssVar: '--code-dim', kind: 'color', label: 'Code comments' },
      { key: 'code_accent', cssVar: '--code-accent', kind: 'color', label: 'Code caption text' }
    ] }
  ];

  var DEFAULTS = {
    base: {
      root_size: 24, lh_body: 1.66, fs_code: 0.775, sidebar: 19.25, measure: 46,
      serif: FONT_OPTIONS.serif[0].value,
      sans: FONT_OPTIONS.sans[0].value,
      mono: FONT_OPTIONS.mono[0].value
    },
    colors: {
      light: {
        paper: '#f0eee6', surface: '#fbfaf7', ivory: '#fffdfa', ink: '#1f1e1d',
        prose: '#33302c', muted: '#55524c', stone: '#8c877c',
        line: '#e0dbcf', line_soft: '#e9e4d8', tint: '#f6ede6',
        terra: '#d97757', terra_dark: '#c9633f', amber: '#b9862f',
        code_bg: '#23211e', code_bar: '#2b2823', code_line: '#3a3732',
        code_ink: '#f2ece1', code_dim: '#a9a294', code_accent: '#f0b49a'
      },
      dark: {
        paper: '#14171b', surface: '#1b1f24', ivory: '#232830', ink: '#eef2f6',
        prose: '#c7d0d8', muted: '#9aa7b4', stone: '#7f8c99',
        line: '#303944', line_soft: '#263039', tint: '#252f3b',
        terra: '#e08a6a', terra_dark: '#eda07e', amber: '#d3a44a',
        code_bg: '#111418', code_bar: '#181d22', code_line: '#2b343e',
        code_ink: '#eef2f6', code_dim: '#8f9ba7', code_accent: '#f0b49a'
      }
    }
  };

  var INIT_MODE = 'auto';
  var STORE = 'mca-site-customiser:v2';

  var root = document.documentElement;
  var darkQuery = window.matchMedia ? window.matchMedia('(prefers-color-scheme: dark)') : null;
  var clone = function (o) { return JSON.parse(JSON.stringify(o)); };
  var copy = function (target, source) {
    Object.keys(target).forEach(function (k) { delete target[k]; });
    Object.keys(clone(source)).forEach(function (k) { target[k] = clone(source)[k]; });
  };

  var saved = {};
  try { saved = JSON.parse(localStorage.getItem(STORE)) || {}; } catch (e) { saved = {}; }

  var state = {
    mode: saved.mode === 'light' || saved.mode === 'dark' || saved.mode === 'auto' ? saved.mode : INIT_MODE,
    base: Object.assign(clone(DEFAULTS.base), saved.base || {}),
    colors: {
      light: Object.assign(clone(DEFAULTS.colors.light), (saved.colors || {}).light || {}),
      dark: Object.assign(clone(DEFAULTS.colors.dark), (saved.colors || {}).dark || {})
    }
  };

  var resolved = function () {
    return state.mode === 'auto' ? (darkQuery && darkQuery.matches ? 'dark' : 'light') : state.mode;
  };
  var currentColors = function () { return state.colors[resolved()]; };

  var cssVal = function (item, value) {
    return item.unit ? value + item.unit : String(value);
  };

  var apply = function () {
    root.setAttribute('data-theme', resolved());

    SPEC.forEach(function (group) {
      group.items.forEach(function (item) {
        var value = item.kind === 'color' ? currentColors()[item.key] : state.base[item.key];
        if (value === undefined || value === null || value === '') root.style.removeProperty(item.cssVar);
        else root.style.setProperty(item.cssVar, cssVal(item, value));
      });
    });
  };

  var persist = function () {
    try { localStorage.setItem(STORE, JSON.stringify(state)); } catch (e) { /* private mode */ }
  };

  /* ---- build the panel ---- */
  var panel = document.getElementById('stylepanel');
  var button = document.getElementById('stylebtn');
  var panelBody = document.getElementById('sp-body');
  var modeSelect = document.getElementById('sp-mode');
  var refs = {};

  var hex6 = function (value) {
    var v = String(value || '').trim().replace('#', '');
    if (v.length === 3) v = v.split('').map(function (c) { return c + c; }).join('');
    return '#' + v.slice(0, 6).padStart(6, '0');
  };

  var ensureFontOption = function (select, value) {
    if (!value) return;
    var found = Array.prototype.some.call(select.options, function (opt) { return opt.value === value; });
    if (!found) {
      var option = document.createElement('option');
      option.value = value;
      option.textContent = 'Custom';
      select.appendChild(option);
    }
  };

  var addGroup = function (group) {
    var wrap = document.createElement('div');
    wrap.className = 'sp-group';

    var title = document.createElement('h3');
    title.textContent = group.title;
    if (group.colors) {
      var tag = document.createElement('span');
      tag.className = 'tag';
      tag.id = 'sp-modetag';
      title.appendChild(tag);
    }
    wrap.appendChild(title);

    if (group.colors) {
      var grid = document.createElement('div');
      grid.className = 'sp-colors';
      group.items.forEach(function (item) {
        var label = document.createElement('label');
        var swatch = document.createElement('input');
        swatch.type = 'color';
        swatch.title = item.label + '  (' + item.cssVar + ')';
        swatch.setAttribute('aria-label', item.label);
        var name = document.createElement('span');
        name.className = 'swatch-label';
        name.textContent = item.label;
        var hex = document.createElement('span');
        hex.className = 'hex';
        label.append(swatch, name, hex);
        grid.appendChild(label);

        swatch.addEventListener('input', function () {
          currentColors()[item.key] = swatch.value;
          hex.textContent = swatch.value;
          apply();
          persist();
        });
        refs[item.key] = { swatch: swatch, hex: hex };
      });
      wrap.appendChild(grid);
      panelBody.appendChild(wrap);
      return;
    }

    group.items.forEach(function (item) {
      var row = document.createElement('div');
      row.className = 'sp-row';
      var label = document.createElement('label');
      label.textContent = item.label;
      row.appendChild(label);

      if (item.kind === 'font') {
        var select = document.createElement('select');
        select.setAttribute('aria-label', item.label);
        (item.options || []).forEach(function (option) {
          var opt = document.createElement('option');
          opt.value = option.value;
          opt.textContent = option.label;
          select.appendChild(opt);
        });
        ensureFontOption(select, state.base[item.key]);
        select.value = state.base[item.key] || (item.options && item.options[0] ? item.options[0].value : '');
        label.appendChild(select);
        select.addEventListener('change', function () {
          state.base[item.key] = select.value;
          apply();
          persist();
        });
        refs[item.key] = { select: select };
      } else {
        var out = document.createElement('output');
        row.appendChild(out);
        var input = document.createElement('input');
        input.type = 'range';
        input.min = item.min;
        input.max = item.max;
        input.step = item.step;
        input.setAttribute('aria-label', item.label);
        row.appendChild(input);
        input.addEventListener('input', function () {
          state.base[item.key] = Number(input.value);
          out.textContent = input.value + (item.unit || '');
          apply();
          persist();
        });
        refs[item.key] = { input: input, out: out };
      }
      wrap.appendChild(row);
    });

    panelBody.appendChild(wrap);
  };

  SPEC.forEach(addGroup);

  var refresh = function () {
    if (modeSelect.value !== state.mode) modeSelect.value = state.mode;
    var mode = resolved();
    var modeTag = document.getElementById('sp-modetag');
    if (modeTag) modeTag.textContent = mode;
    if (button) button.title = 'Site customiser - ' + mode + ' mode';

    SPEC.forEach(function (group) {
      group.items.forEach(function (item) {
        var ref = refs[item.key];
        if (!ref) return;
        if (item.kind === 'color') {
          var value = currentColors()[item.key] || '#000000';
          ref.swatch.value = hex6(value);
          ref.hex.textContent = String(value);
        } else if (item.kind === 'font') {
          var font = state.base[item.key] || '';
          ensureFontOption(ref.select, font);
          ref.select.value = font;
        } else {
          var n = state.base[item.key];
          ref.input.value = n;
          ref.out.textContent = n + (item.unit || '');
        }
      });
    });
  };

  var reopen = function () { apply(); refresh(); };

  modeSelect.addEventListener('change', function () {
    state.mode = modeSelect.value;
    reopen();
    persist();
  });

  var onSystemChange = function () { if (state.mode === 'auto') reopen(); };
  if (darkQuery) {
    if (darkQuery.addEventListener) darkQuery.addEventListener('change', onSystemChange);
    else if (darkQuery.addListener) darkQuery.addListener(onSystemChange);
  }
  window.addEventListener('focus', onSystemChange);

  document.getElementById('sp-reset').addEventListener('click', function () {
    copy(state.base, DEFAULTS.base);
    copy(state.colors.light, DEFAULTS.colors.light);
    copy(state.colors.dark, DEFAULTS.colors.dark);
    state.mode = INIT_MODE;
    try { localStorage.removeItem(STORE); } catch (e) { /* ignore */ }
    reopen();
  });

  var toCss = function () {
    var lines = [
      '/* generated by the site customiser - ' + resolved() + ' mode */',
      '/* paste into the page <style>; rebuild after editing the palette */',
      ':root{'
    ];
    SPEC.forEach(function (group) {
      if (group.colors) return;
      group.items.forEach(function (item) {
        lines.push('  ' + item.cssVar + ':' + cssVal(item, state.base[item.key]) + ';');
      });
    });
    var colorItems = SPEC[SPEC.length - 1].items;
    colorItems.forEach(function (item) {
      lines.push('  ' + item.cssVar + ':' + state.colors.light[item.key] + ';');
    });
    lines.push('}', '', 'html[data-theme="dark"]{');
    colorItems.forEach(function (item) {
      lines.push('  ' + item.cssVar + ':' + state.colors.dark[item.key] + ';');
    });
    lines.push('}');
    return lines.join('\\n');
  };

  var copyText = function (text) {
    if (navigator.clipboard && navigator.clipboard.writeText) {
      return navigator.clipboard.writeText(text).then(function () { return true; }, function () { return false; });
    }
    var area = document.createElement('textarea');
    area.value = text;
    area.style.position = 'fixed';
    area.style.opacity = '0';
    document.body.appendChild(area);
    area.select();
    var ok = false;
    try { ok = document.execCommand('copy'); } catch (e) { ok = false; }
    area.remove();
    return Promise.resolve(ok);
  };

  var copyBtn = document.getElementById('sp-copy');
  copyBtn.addEventListener('click', function () {
    copyText(toCss()).then(function (ok) {
      copyBtn.textContent = ok ? 'Copied' : 'Copy failed';
      setTimeout(function () { copyBtn.textContent = 'Copy CSS'; }, 1600);
    });
  });

  var toggle = function (open) {
    panel.hidden = !open;
    button.setAttribute('aria-expanded', String(open));
    if (open) { refresh(); }
  };

  button.addEventListener('click', function () { toggle(panel.hidden); });
  document.getElementById('sp-close').addEventListener('click', function () { toggle(false); });
  document.addEventListener('keydown', function (e) {
    if (e.key === 'Escape' && !panel.hidden) toggle(false);
  });

  apply();
  refresh();
})();
</script>
</body>
</html>`;
}

function escapeXml(str) {
  return String(str).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}

// ── Main ───────────────────────────────────────────────────────────────────
const args = process.argv.slice(2);
const mdPath = args[0]
  ? path.resolve(args[0])
  : path.resolve(__dirname, '..', 'reverse-engineering.md');
const outPath = args[1]
  ? path.resolve(args[1])
  : path.join(path.dirname(mdPath), path.basename(mdPath, '.md') + '.html');

const md = fs.readFileSync(mdPath, 'utf8');
const { html, headings } = mdToHtml(md);

const baseName = path.basename(mdPath, '.md');
const isReverse = baseName === 'reverse-engineering';

const titleFallback = isReverse
  ? 'mini-coding-js \u00b7 Reverse-engineering build prompt'
  : `mini-coding-js \u00b7 ${baseName.replace(/-/g, ' ').replace(/\b\w/g, c => c.toUpperCase())}`;

const env = process.env;
const generatedTitle = env.DOC_TITLE || titleFallback;
const generatedH1 = env.DOC_H1 || (isReverse
  ? 'Reverse-engineering mini-coding-js'
  : baseName.replace(/-/g, ' ').replace(/\b\w/g, c => c.toUpperCase()));
const generatedLede = env.DOC_LEDE || (isReverse
  ? 'A from-scratch specification of the minimal coding-agent harness: one ReAct loop, eight tools, a write sandbox, nine lifecycle hooks, persistent memory, and an offline demo that proves the guards hold.'
  : 'Converted from Markdown.');
const generatedEyebrow = env.DOC_EYEBROW || (isReverse ? 'Build prompt \u00b7 complete specification' : 'Reading guide');
const generatedTocTitle = env.DOC_TOC_TITLE || (isReverse ? 'Reverse-engineering' : baseName.replace(/-/g, ' ').replace(/\b\w/g, c => c.toUpperCase()));
const generatedSideSub = env.DOC_SIDE_SUB || (isReverse
  ? 'The complete build specification: every file, every function, every contract, every test.'
  : 'Converted from Markdown to styled HTML.');
const generatedMeta = env.DOC_META
  ? env.DOC_META.split('|').map((item) => item.trim()).filter(Boolean)
  : (isReverse ? ['15 sections', '~1400 lines', '15 source files', '1 dependency'] : [`${headings.length} sections`, 'generated page']);

const page = buildPage({
  title: generatedTitle,
  eyebrow: generatedEyebrow,
  h1: generatedH1,
  lede: generatedLede,
  meta: generatedMeta,
  tocTitle: generatedTocTitle,
  sideSub: generatedSideSub,
  sideFoot: env.DOC_SIDE_FOOT || (isReverse
    ? 'Companion to the animated explainers<br>Every file in <code>src/</code> is specified here'
    : `Built from <code>${path.basename(mdPath)}</code><br>${headings.length} sections`),
  sideKicker: env.DOC_SIDE_KICKER || generatedEyebrow,
  colophon: env.DOC_COLOPHON || `Built from <code>${path.basename(mdPath)}</code> &middot; ${headings.length} sections`,
  contentHtml: html,
  headings,
});

fs.writeFileSync(outPath, page, 'utf8');
console.log('Wrote ' + outPath + ' (' + headings.length + ' sections)');
