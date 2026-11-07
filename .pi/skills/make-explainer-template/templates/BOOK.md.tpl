# __TITLE__

> [!WARNING]
> **This book is an educational project to learn and understand, not a production-ready system.**
> It teaches a simplified, deliberately small implementation. It is **not** production-ready software and should not be used as one. The code favours clarity over robustness, security, scale, and operational correctness. Use it to learn the ideas, then build production software with proper validation, isolation, observability, testing, and review.

## About this book

This is a staged explainer book for **__TOPIC__** in **__LANGUAGE_LABEL__**. Each chapter adds one layer to a small working system and explains the trade-offs behind it. The companion code lives in `ch00/` … `ch__LAST__/`.

## Who it is for

- Learners who prefer to build a working thing before studying the theory.
- Developers who want a compact mental model of the architecture.
- Instructors who need a runnable, chapter-by-chapter teaching arc.

## How to use this book

1. Read the chapter.
2. Open the matching `chNN/CHAPTER.md` run sheet.
3. Run the stage.
4. Check the acceptance criteria.
5. Explain the change back in your own words before moving on.

## The educational contract

This project is intentionally honest about its limits:

- It is a teaching model, not a hardened product.
- It optimises for readability and small steps, not production performance.
- Safety checks, tests, and error handling are illustrative and incomplete.
- Any real deployment needs independent review and production-grade controls.

---

__BOOK_BODY__

---

# Appendix: Study and review

## Rebuild from memory

Close the book and rebuild the final stage from a blank directory. Use the plan and the acceptance criteria, not the code, as your guide. Then compare your result with `ch__LAST__/`.

## Review questions

- Which decision in this project would change first if it had to serve real users?
- Where does the teaching code take a shortcut, and what would production code do instead?
- Which boundary is easiest to break accidentally?
- What would you test first if you inherited this project?
- Which simplification is acceptable for learning but unacceptable in production?

## Glossary

Add the domain terms used by this project here as the book develops.

## Further reading

Add links to the language documentation, relevant specifications, and reference material here.

---

**Educational use only — not a production-ready system.** The book and its code are an educational project to learn and understand, not a deployable system.
