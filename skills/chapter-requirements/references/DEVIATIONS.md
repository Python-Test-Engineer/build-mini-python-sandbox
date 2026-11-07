# Deviations and decisions

This file records intentional differences between the generated chapter snapshots, the book and the contracts in `plan.md`. The chapter snapshots live at the repository root (`ch00/` … `ch16/`); the former `BOOK/` wrapper is obsolete.

## 1. `delete_file` is included

- **Plan:** Stage 8 lists `create_file`, `write_file`, `edit_file` and `delete_file`, and the end state is nine tools.
- **Decision:** follow the plan. `ch08`–`ch16` expose nine tools: `list_files`, `read_file`, `create_file`, `write_file`, `edit_file`, `delete_file`, `run_command`, `remember`, `recall`.
- **Consequence:** the book, README and stage text say "nine tools". A future reconciliation can remove `delete_file` from every chapter, but it must not silently keep both counts.

## 2. One shared `.env` at the repository root

- Chapters do **not** carry their own `.env` or `.env.example`.
- `config.js` walks up from each chapter root, so the nearest `.env` is the shared file at the repository root (next to `ch00/` … `ch16/`).
- The shared `.env` is git-ignored; the distributed copy contains only a placeholder, never a real key.

## 3. `package-lock.json` is included

- Each chapter carries a `package-lock.json` for reproducible installs.
- It was generated, not hand-written, from the single `chalk` dependency.

## 4. Chapters do not carry `node_modules/`

- Readers run `npm install` per chapter, as the requirements require.

## 5. `CHAPTER.md` only, except the final chapter

- `ch00`–`ch15` have `CHAPTER.md`; `ch16` has both `CHAPTER.md` and the project `README.md`.
- `ch16`'s `CHAPTER.md` is not overwritten by the README.

## 6. Shell scanning is best-effort

- The `run_command` write-target scan and hard deny-list are heuristics, exactly as documented in `plan.md` and the book.
- The sandbox is not a container. This is stated in the book's safety section and is a deliberate teaching choice, not an omission.

## 7. Tests are offline

- No test makes a network call or needs an API key.
- Live-mode checks in `CHAPTER.md` files are manual.

## 8. Chapter numbering and location

- `chNN` maps one-to-one to Stage `NN` (`ch00` = Stage 0 … `ch16` = Stage 16), as resolved in the requirements document.
- All chapters now live at the repository root. The obsolete `BOOK/` wrapper has been removed.
