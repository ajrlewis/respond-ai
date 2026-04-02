# Commands

Use these commands instead of guessing. If a command is missing or incorrect, update this file.

## Branching

- Create feature branch: `git checkout -b feat/<short-description>`

## API (`apps/api`)

> Default API path is `apps/api`. If this repo differs, update these commands and record the correct path in `.agents/MEMORY.md`.
>
> FastAPI run command assumes ASGI entrypoint `app.main:app`. Replace with the real module path if different.

- Install deps: `cd apps/api && uv sync --extra dev`
- Run API locally: `cd apps/api && uv run uvicorn app.main:app --reload`
- Run unit tests: `cd apps/api && uv run pytest -q`
- Run full test suite: `cd apps/api && uv run pytest`
- Seed markdown docs: `cd apps/api && uv run python scripts/seed_data.py`
- Run offline evals: `cd apps/api && uv run python scripts/run_evals.py --limit 50`

## Database

> Defaults below assume migrations run from `apps/api`.

- Create migration: `cd apps/api && uv run alembic revision --autogenerate -m "<message>"`
- Apply migrations: `cd apps/api && uv run alembic upgrade head`
- Roll back one migration: `cd apps/api && uv run alembic downgrade -1`
- Show current revision: `cd apps/api && uv run alembic current`

## Web (`apps/web`)

> Default web path is `apps/web`. If this repo differs, update these commands and record the correct path in `.agents/MEMORY.md`.

- Install deps: `cd apps/web && bun install --frozen-lockfile`
- Run app locally: `cd apps/web && bun run dev`
- Run tests: `cd apps/web && bun run test`
- Build: `cd apps/web && bun run build`

## Docker

- Start full stack: `docker compose up --build`
- Start in background: `docker compose up -d`
- Stop stack: `docker compose down`
- View logs: `docker compose logs`

## CI / validation

> Prefer a single command that runs all required checks if available.

- Local CI-equivalent checks: `cd apps/api && uv run pytest -q && cd ../web && bun run build`
