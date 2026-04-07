# Agent Instructions

Read these files before making changes:

1. `.agents/PROJECT.md`
2. `.agents/STACK.md`
3. `.agents/WORKFLOWS.md`
4. `.agents/COMMANDS.md`
5. `.agents/CHECKLISTS.md`
6. `.agents/MEMORY.md`
7. `.agents/CODE_STYLE.md`
8. `.agents/EVALS.md`

## Default Monorepo Layout

Use this template default unless the repo documents a different structure:

```text
apps/
  api/        # FastAPI backend
  web/        # Next.js frontend
packages/     # optional shared libraries/config/types
infra/        # optional infrastructure/deployment files
```

## Operating rules

- Treat this file as the entrypoint and `.agents/*` as the source of truth.
- Follow the workflows in `.agents/WORKFLOWS.md` for all changes.
- Run Git preflight from `.agents/WORKFLOWS.md` before the first file edit in every task.
- Do not start edits on `main`/`master`; switch to a feature branch first.
- For empty/unborn repos, establish `main` first, then create a bootstrap feature branch before scaffolding.

- Keep changes small and scoped to the task.
- Add or update tests for any new or changed behavior.
- Run relevant tests before finishing.
- Prefer incremental changes over large rewrites.

- Use commands from `.agents/COMMANDS.md` instead of guessing.
- Avoid unrelated refactors or broad changes.

- If API (`apps/api`) or web (`apps/web`) behavior changes, verify impacted areas.
- If runtime or dependencies change, check Docker and deployment implications.

- Follow code style guidelines in `.agents/CODE_STYLE.md`.

- When you discover stable repo facts (paths, commands, conventions), add them to `.agents/MEMORY.md`.
- Do not add temporary notes or speculative information.
