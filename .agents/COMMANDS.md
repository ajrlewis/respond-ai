# Commands

Use these commands instead of guessing. If a command is missing or incorrect, update this file.

## Branching

- Verify git repo context: `git rev-parse --is-inside-work-tree`
- Check if history exists (fails for empty/unborn repos): `git rev-parse --verify HEAD`
- Show current branch: `git branch --show-current`
- For empty/unborn repos, establish `main` first: `git checkout -B main`
- Create feature branch: `git checkout -b feat/<short-description>`
- Create bootstrap feature branch for initial scaffolding: `git checkout -b feat/bootstrap-<short-description>`
- Commit staged changes: `git commit -m "<type>(<scope>): <summary>"`

## API (`apps/api`)

> Default API path is `apps/api`. If this repo differs, update these commands and record the correct path in `.agents/MEMORY.md`.
>
> FastAPI run command assumes ASGI entrypoint `app.main:app`. Replace with the real module path if different.

- Install deps: `cd apps/api && uv sync --frozen`
- Run API locally: `cd apps/api && uv run uvicorn app.main:app --reload`
- Run unit tests: `cd apps/api && uv run pytest -q`
- Run full test suite: `cd apps/api && uv run pytest`

## Database

> Defaults below assume migrations run from `apps/api`.

- Create migration: `cd apps/api && uv run alembic revision --autogenerate -m "<message>"`
- Apply migrations: `cd apps/api && uv run alembic upgrade head`
- Roll back one migration: `cd apps/api && uv run alembic downgrade -1`
- Show current revision: `cd apps/api && uv run alembic current`

## Web (`apps/web`)

> Default web path is `apps/web`. If this repo differs, update these commands and record the correct path in `.agents/MEMORY.md`.
>
> Unit tests for Next.js should use Vitest with React Testing Library.

- Install deps: `cd apps/web && bun install --frozen-lockfile`
- Run app locally: `cd apps/web && bun run dev`
- Run unit tests (Vitest): `cd apps/web && bun run test`
- Run tests in watch mode: `cd apps/web && bun run test:watch`
- Run tests with coverage: `cd apps/web && bun run test:coverage`
- Build: `cd apps/web && bun run build`

## Docker

- Start full stack: `docker compose up --build`
- Start in background: `docker compose up -d`
- Stop stack: `docker compose down`
- View logs: `docker compose logs`

## CI / validation

> Prefer a single command that runs all required checks if available.

- Local CI-equivalent checks: `<replace-with-your-local-ci-command>`
