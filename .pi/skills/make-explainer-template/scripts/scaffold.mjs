#!/usr/bin/env node
/**
 * make-explainer-template - scaffold a staged explainer project.
 *
 * Example:
 *   node scripts/scaffold.mjs \
 *     --out ../my-new-book \
 *     --topic "a small coding agent" \
 *     --language python \
 *     --title "Build a Mini Coding Agent in Python" \
 *     --chapters 12
 *
 * The generated project is dependency-free for the build step. PDF output
 * needs a local Chrome or Edge install (see scripts/build.mjs).
 */

import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const SKILL_ROOT = path.resolve(HERE, '..');
const TEMPLATES = path.join(SKILL_ROOT, 'templates');
const ASSETS = path.join(SKILL_ROOT, 'assets');

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

function die(message) {
  console.error(`scaffold: ${message}`);
  console.error('\nUsage:\n  node scripts/scaffold.mjs --out DIR --topic "..." --language python|javascript [options]\n\nOptions:\n  --title TITLE       Book title (default: Build a Mini <topic> in <language>)\n  --slug SLUG         Project slug (default derived from title)\n  --author NAME       Author name (default: Your Name)\n  --chapters N        Number of chapter folders, ch00..chNN-1 (default 12)\n  --stages "A,B,C"    Comma-separated stage titles (overrides --chapters)\n  --force             Write into a non-empty directory\n');
  process.exit(1);
}

if (ARGS.help || ARGS.h) {
  die('help requested');
}

const outArg = ARGS.out || ARGS._[0];
if (!outArg) die('--out is required');

const topic = typeof ARGS.topic === 'string' ? ARGS.topic.trim() : '';
if (!topic) die('--topic is required');

const rawLanguage = String(ARGS.language || 'javascript').toLowerCase();
const language = ['py', 'python'].includes(rawLanguage)
  ? 'python'
  : ['js', 'javascript', 'node', 'nodejs'].includes(rawLanguage)
    ? 'javascript'
    : null;
if (!language) die('--language must be python or javascript');

const languageLabel = language === 'python' ? 'Python' : 'JavaScript';
const isPython = language === 'python';
const extension = isPython ? 'py' : 'js';
const fence = isPython ? 'python' : 'javascript';
const mainFile = isPython ? 'main.py' : 'main.js';
const runtime = isPython ? 'Python 3.11+' : 'Node.js 20+';
const testCommand = isPython
  ? 'python -m unittest discover -s test'
  : 'node --test';
const runCommand = isPython ? 'python -m src.main' : 'node src/main.js';

const defaultStages = [
  'Scaffold the project',
  'Configuration and environment',
  'Model or data client',
  'Minimal working loop',
  'State and history',
  'Instructions and context',
  'Read-only tooling',
  'Write and mutation tooling',
  'Safety boundaries',
  'Memory and persistence',
  'Lifecycle hooks and observability',
  'Extract the core engine',
  'Offline demo or fixtures',
  'Full command-line interface',
  'Offline test suite',
  'Documentation and final review',
];

let stages;
if (typeof ARGS.stages === 'string') {
  stages = ARGS.stages.split(',').map((s) => s.trim()).filter(Boolean);
  if (!stages.length) die('--stages did not contain any titles');
} else {
  const count = Number(ARGS.chapters || 12);
  if (!Number.isInteger(count) || count < 1 || count > 99) {
    die('--chapters must be an integer between 1 and 99');
  }
  stages = [];
  for (let i = 0; i < count; i++) {
    stages.push(defaultStages[i] || `Extension stage ${i}`);
  }
}

if (ARGS.chapters && typeof ARGS.stages === 'string') {
  const requested = Number(ARGS.chapters);
  if (Number.isInteger(requested) && requested !== stages.length) {
    die('--chapters and --stages disagree; use one or make them match');
  }
}

const defaultTitle = /^(a|an|the)\s+/i.test(topic)
  ? `Build ${topic} in ${languageLabel}`
  : `Build a Mini ${topic} in ${languageLabel}`;
const title = String(ARGS.title || defaultTitle).trim();

const slug = String(ARGS.slug || title)
  .toLowerCase()
  .replace(/[^a-z0-9]+/g, '-')
  .replace(/^-+|-+$/g, '')
  .slice(0, 64) || 'explainer-book';

const author = String(ARGS.author || 'Your Name').trim();
const last = String(stages.length - 1).padStart(2, '0');
const outDir = path.resolve(process.cwd(), outArg);

const disclaimer =
  'Educational use only — not a production-ready system. This material is an educational project to learn and understand. ' +
  'It is a deliberately simplified teaching system, not secure, complete, or ready for real users, and must not be deployed as-is. ' +
  'If you adapt it for real work, add proper validation, isolation, monitoring, testing, and operational controls.';

const pad = (n) => String(n).padStart(2, '0');

/* ------------------------------------------------------------------ */
/* helpers                                                             */
/* ------------------------------------------------------------------ */

function readTemplate(name) {
  return fs.readFileSync(path.join(TEMPLATES, name), 'utf8');
}

function render(template, data) {
  let text = template;
  for (const [key, value] of Object.entries(data)) {
    text = text.split(`__${key}__`).join(String(value ?? ''));
  }
  return text;
}

const WRITTEN = [];
const SKIPPED = [];

function write(rel, content) {
  const target = path.join(outDir, rel);
  if (fs.existsSync(target) && !ARGS.force) {
    SKIPPED.push(rel);
    return;
  }
  fs.mkdirSync(path.dirname(target), { recursive: true });
  fs.writeFileSync(target, content, 'utf8');
  WRITTEN.push(rel);
}

function writeBinary(rel, source) {
  const target = path.join(outDir, rel);
  if (fs.existsSync(target) && !ARGS.force) {
    SKIPPED.push(rel);
    return;
  }
  fs.mkdirSync(path.dirname(target), { recursive: true });
  fs.copyFileSync(source, target);
  WRITTEN.push(rel);
}

function quickstart() {
  if (isPython) {
    return [
      'cd ch00',
      'python -m venv .venv',
      '# Windows PowerShell:  .venv\\Scripts\\Activate.ps1',
      '# macOS / Linux:       source .venv/bin/activate',
      'pip install -r requirements.txt',
      'python -m unittest discover -s test',
      'python -m src.main',
    ].join('\n');
  }
  return [
    'cd ch00',
    'npm install',
    'npm test',
    'node src/main.js',
  ].join('\n');
}

function architecture() {
  return [
    `Entry point (src/${mainFile})`,
    '  ├─ configuration',
    '  ├─ core stage logic',
    '  ├─ model / data / input boundary',
    '  ├─ safety policy and limits',
    '  └─ outputs, checks, and tests',
  ].join('\n');
}

function stageTable() {
  const rows = [
    '| Stage | Folder | Focus | Accepted |',
    '|---|---|---|---|',
  ];
  stages.forEach((stage, index) => {
    rows.push(`| ${index} | \`ch${pad(index)}/\` | ${stage} | ☐ |`);
  });
  return rows.join('\n');
}

function planStages() {
  return stages.map((stage, index) => {
    return [
      `### Stage ${index} — ${stage}`,
      '',
      '**What you will learn:** Replace this with one clear, concrete learning objective.',
      '',
      '**Files to create or modify:**',
      '- `src/...`',
      '- `test/...`',
      '',
      '**Acceptance criteria:**',
      '- [ ] The stage runs from a clean checkout.',
      `- [ ] The stage demonstrates one new capability: ${stage.toLowerCase()}.`,
      '- [ ] The offline checks pass.',
      '- [ ] The previous stage still runs.',
      '- [ ] The educational-use limitation is still stated.',
      '',
    ].join('\n');
  }).join('\n');
}

function finalChecklist() {
  const rows = stages.map((stage, index) =>
    `- [ ] Stage ${index}: ${stage}`
  );
  return [
    ...rows,
    '- [ ] Every chapter explains the educational-use limitation.',
    '- [ ] The book builds to HTML and PDF.',
    '- [ ] The final checkpoint runs from a clean checkout.',
    '- [ ] No chapter claims the result is production-grade.',
  ].join('\n');
}

function bookBody() {
  return stages.map((stage, index) => {
    const prev = index > 0 ? `ch${pad(index - 1)}` : null;
    const next = index < stages.length - 1 ? `ch${pad(index + 1)}` : null;
    return [
      `# Chapter ${index} — Stage ${index}: ${stage}`,
      '',
      '> [!WARNING]',
      `> **Educational use only — not a production-ready system.** Chapter ${index} is Stage ${index} in an educational project to learn and understand. It simplifies the design so the idea stays visible. Do not deploy it as-is.`,
      '',
      '## What this chapter builds',
      '',
      `This chapter builds the **${stage}** layer of ${topic} in ${languageLabel}.`,
      '',
      '- Replace this paragraph with the concrete problem the stage solves.',
      '- State what the reader can run, see, or verify by the end.',
      '- Name the one architectural idea the reader should remember.',
      '',
      '## Why it matters',
      '',
      'Explain the trade-off behind the stage. What gets easier? What gets deferred? Which production concern is deliberately out of scope?',
      '',
      '## Build it',
      '',
      'Walk through the change one decision at a time. Prefer short code blocks and observable checkpoints over long explanations.',
      '',
      '```' + fence,
      `# Chapter ${index} - Stage ${index}: ${stage.toLowerCase()}`,
      runCommand,
      '```',
      '',
      '## Acceptance criteria',
      '',
      '- [ ] The chapter checkpoint runs on its own.',
      '- [ ] The new capability is observable.',
      '- [ ] The offline checks pass.',
      '- [ ] The limits of the teaching implementation are stated.',
      '',
      '## What to notice',
      '',
      'Point out the boundary, contract, or invariant the reader should be able to explain after the chapter.',
      '',
      '## Limits and production notes',
      '',
      'This is an educational implementation. Say what it does not handle, what a production version would need, and why the simplification is acceptable for learning.',
      '',
      '## Read next',
      '',
      prev ? `- Previous checkpoint: [\`${prev}/\`](../${prev}/CHAPTER.md)` : '- This is the first checkpoint.',
      next ? `- Next chapter: Chapter ${index + 1} — Stage ${index + 1}: ${stages[index + 1]} (\`${next}/\`)` : '- This is the final checkpoint.',
      '',
    ].join('\n');
  }).join('\n---\n\n');
}

function chapterTemplate(index) {
  const previous = index > 0 ? `ch${pad(index - 1)}` : null;
  const next = index < stages.length - 1 ? `ch${pad(index + 1)}` : null;
  return render(readTemplate('CHAPTER.md.tmpl'), {
    N: index,
    NN: pad(index),
    STAGE_TITLE: stages[index],
    GOAL: `Add the "${stages[index]}" checkpoint to ${topic} without breaking the previous stage.`,
    BULLET_ONE: 'The one new capability this stage introduces.',
    BULLET_TWO: 'The check or test that proves the capability works.',
    BULLET_THREE: 'The production concern this stage deliberately leaves out.',
    MAIN_FILE: mainFile,
    RUN_COMMAND: runCommand,
    FENCE: fence,
    PREV_LINK: previous
      ? `- Previous checkpoint: \`../${previous}/\``
      : '- Previous checkpoint: none; this is the starting point.',
    NEXT_LINK: next
      ? `- Next checkpoint: \`../${next}/\``
      : '- Next checkpoint: none; this is the final stage.',
  });
}

/* ------------------------------------------------------------------ */
/* scaffold                                                            */
/* ------------------------------------------------------------------ */

if (fs.existsSync(outDir)) {
  const entries = fs.readdirSync(outDir).filter((name) => name !== '.git');
  if (entries.length && !ARGS.force) {
    die(`${outDir} already exists and is not empty. Use --force to write into it.`);
  }
}

fs.mkdirSync(outDir, { recursive: true });

const readme = render(readTemplate('README.md.tmpl'), {
  TITLE: title,
  TOPIC: topic,
  LANGUAGE_LABEL: languageLabel,
  SLUG: slug,
  AUTHOR: author,
  LAST: last,
  FENCE: 'bash',
  QUICKSTART: quickstart(),
});

const plan = render(readTemplate('plan.md.tmpl'), {
  TITLE: title,
  TOPIC: topic,
  LANGUAGE_LABEL: languageLabel,
  SLUG: slug,
  AUTHOR: author,
  ARCHITECTURE: architecture(),
  STAGE_TABLE: stageTable(),
  PLAN_STAGES: planStages(),
  FINAL_CHECKLIST: finalChecklist(),
});

const book = render(readTemplate('BOOK.md.tpl'), {
  TITLE: title,
  TOPIC: topic,
  LANGUAGE_LABEL: languageLabel,
  SLUG: slug,
  LAST: last,
  BOOK_BODY: bookBody(),
});

const config = {
  title,
  slug,
  topic,
  language,
  languageLabel,
  runtime,
  author,
  kicker: `${languageLabel} build-along`,
  subtitle: `A staged, educational build-along for ${topic}.`,
  disclaimer,
  chapters: stages.length,
  source: 'book/BOOK.md',
  outputHtml: 'book/BOOK.html',
  outputPdf: 'book/BOOK.pdf',
  buildChapters: true,
};

write('README.md', readme);
write('plan.md', plan);
write('book/BOOK.md', book);
write('book.config.json', JSON.stringify(config, null, 2) + '\n');
write('.env.example', '# Add secrets here. Never commit a real key.\n# API_KEY=replace-me\n');

write('.gitignore', [
  'node_modules/',
  '.venv/',
  '__pycache__/',
  '*.pyc',
  '.env',
  '*.log',
  '.DS_Store',
  'ch*/workspace/*',
  '!ch*/workspace/.gitkeep',
  '',
].join('\n'));

write('assets/book.css', fs.readFileSync(path.join(ASSETS, 'book.css'), 'utf8'));
write('scripts/build.mjs', fs.readFileSync(path.join(HERE, 'build.mjs'), 'utf8'));

for (let index = 0; index < stages.length; index++) {
  const dir = `ch${pad(index)}`;
  write(`${dir}/CHAPTER.md`, chapterTemplate(index));
  write(`${dir}/.gitignore`, [
    'node_modules/',
    '.venv/',
    '__pycache__/',
    '*.pyc',
    'workspace/*',
    '!workspace/.gitkeep',
    '',
  ].join('\n'));
  write(`${dir}/workspace/.gitkeep`, '');
  write(`${dir}/test/.gitkeep`, '');

  if (isPython) {
    write(`${dir}/src/__init__.py`, '');
    write(`${dir}/src/main.py`, [
      '"""Chapter placeholder. Replace this with the stage implementation."""',
      '',
      'def main() -> None:',
      `    print("Chapter ${index} - Stage ${index}: replace src/main.py with this stage implementation.")`,
      '',
      '',
      'if __name__ == "__main__":',
      '    main()',
      '',
    ].join('\n'));
    write(`${dir}/requirements.txt`, '# Add runtime dependencies here.\n');
  } else {
    write(`${dir}/src/main.js`, [
      '// Chapter placeholder. Replace this with the stage implementation.',
      `console.log("Chapter ${index} - Stage ${index}: replace src/main.js with this stage implementation.");`,
      '',
    ].join('\n'));
    write(`${dir}/package.json`, JSON.stringify({
      name: `${slug}-ch${pad(index)}`,
      private: true,
      type: 'module',
      scripts: {
        start: 'node src/main.js',
        test: 'node --test',
      },
      engines: { node: '>=20' },
    }, null, 2) + '\n');
  }
}

console.log(`Created ${createdLabel()} in ${outDir}`);
console.log(`  Chapters : ${stages.length} (ch00..ch${pad(String(stages.length - 1))})`);
console.log(`  Topic    : ${topic}`);
console.log(`  Language : ${languageLabel}`);
console.log('');
console.log('Next:');
console.log(`  cd ${path.relative(process.cwd(), outDir) || '.'}`);
console.log('  node scripts/build.mjs');
console.log('');
console.log('Then replace every "Replace this" placeholder with real chapter content.');
console.log('Keep the educational-use disclaimer at the top of README.md, plan.md, book/BOOK.md, and every CHAPTER.md.');

function createdLabel() {
  const suffix = SKIPPED.length ? ` (${SKIPPED.length} existing file${SKIPPED.length === 1 ? '' : 's'} skipped)` : '';
  return `${WRITTEN.length} files${suffix}`;
}
