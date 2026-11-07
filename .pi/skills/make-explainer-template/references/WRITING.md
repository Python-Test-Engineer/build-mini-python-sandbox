# Writing guide

## Voice

Write like a patient engineer explaining a real build to a capable beginner.

- Prefer concrete behaviour over abstract claims.
- Explain the trade-off behind each design decision.
- Say what is deliberately missing.
- Use short paragraphs and small code blocks.
- Make every chapter runnable and checkable.
- Do not sell the result. It is a teaching model.

Avoid:

- marketing language and "revolutionary" claims,
- pretending the teaching code is secure or complete,
- unexplained jargon,
- giant code dumps with no narrative,
- chapters that cannot be run on their own,
- production advice presented as if it were tested.

## Chapter shape

Use this checklist for every chapter:

- [ ] The title states the one capability added.
- [ ] The educational-use disclaimer is first.
- [ ] The goal is one sentence.
- [ ] The reader knows what to run.
- [ ] The code change is explained decision by decision.
- [ ] There is at least one observable acceptance check.
- [ ] The chapter names what it deliberately does not handle.
- [ ] The chapter links back to the plan and forward to the next stage.
- [ ] The run sheet and the book chapter agree.

## Stage design

A good stage is:

- **small:** one architectural layer or one user-visible capability;
- **runnable:** a clean checkout can execute it;
- **observable:** the reader can see or test the new behaviour;
- **honest:** its limits are stated in the chapter;
- **cumulative:** it does not invalidate the previous checkpoint.

If a stage needs more than one major idea, split it.

## Disclaimers

Every project, book, plan, and chapter begins with a variation of:

> **Educational use only — not a production-ready system.** This material is an educational project to learn and understand. It is a deliberately simplified teaching system, not secure, complete, or ready for real users, and must not be deployed as-is. If you adapt it for real work, add proper validation, isolation, monitoring, testing, and operational controls.

Keep the wording direct. Do not bury it in an appendix or a footer.

## Language-specific notes

### Python

- Use type hints on public functions.
- Prefer the standard library until a dependency is justified.
- Keep modules importable and testable without global state.
- Document the virtual-environment setup.
- Use `unittest` unless the project explicitly standardises on another runner.

### JavaScript

- Use ES modules.
- Prefer named exports.
- Inject dependencies instead of reading globals at call time.
- Keep the runtime dependency count low.
- Use `node --test` for offline checks unless the project explicitly standardises on another runner.

## Common failure modes

| Symptom | Fix |
|---|---|
| Sidebar is empty or broken | Every document must start with `#`; the builder derives section IDs and TOC entries from headings. |
| Code fence renders as a paragraph | Use three backticks on their own line and close them. |
| Table renders as text | Include a separator row such as `|---|---|`. |
| PDF is missing | Install Chrome/Edge or set `CHROME_PATH`; rerun `node scripts/build.mjs`. |
| Disclaimer missing from HTML | Do not edit generated HTML by hand. Fix `book.config.json` or the source Markdown and rebuild. |
| Chapter links point to the wrong folder | Keep `chNN` numbering consistent with the stage map: folder `chNN/` is Stage NN. `ch00/` is Stage 0, `ch01/` is Stage 1. |
| One language leaks into another | Choose Python or JavaScript for the whole book; do not mix run commands. |

## Definition of done

A book is done when:

- every chapter has a runnable checkpoint and an offline check;
- the plan, book, and chapter run sheets agree;
- the HTML and PDF editions build;
- the disclaimer is visible at the top of every document;
- a reader can explain the architecture without reading the source line by line;
- nobody could mistake the result for production-grade software.
