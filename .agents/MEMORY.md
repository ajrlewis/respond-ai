# Stable Memory

Use this file for stable repo facts that should persist across tasks.
This is not a task log.

## When to write

Write to this file when you discover, confirm, or change durable facts, including:

- actual API path (default template path is `apps/api`)
- actual web path (default template path is `apps/web`)
- canonical commands used for install, run, and test
- deployment target names and environment names
- required CI/CD job names
- durable repo conventions used consistently

## Good examples

- API lives in `apps/api`
- Web app lives in `apps/web`
- CI command is `make ci`
- Production deploy uses Vercel project `portfolio-web`
- API tests run with `cd apps/api && uv run pytest -q`
- Web dev server runs with `cd apps/web && bun run dev`

## Do not store

- temporary task notes
- one-off assumptions
- debugging logs
- chain-of-thought or step-by-step reasoning

## Style

- Use concise bullet points
- Prefer concrete, verifiable facts
- Avoid speculation
- Update or replace stale entries when facts change

## RespondAI facts

- The `api` Docker image installs with `uv sync --no-dev`, so `pytest` is not available inside `docker compose exec api ...`; run API tests from `apps/api` on host instead.

## Example update

- API path changed from `apps/api` to `services/api`
- Updated commands now use `cd services/api && uv run pytest -q`
- Web unit test baseline uses Vitest + React Testing Library via `cd apps/web && bun run test`
- Backend LLM baseline uses LangChain with provider adapters (OpenAI/Anthropic/Google), Pydantic structured outputs, and explicit `small`/`large` model tiers.
- Branch safety baseline: run Git preflight before first edit; if repo is empty, establish `main` then branch to `feat/bootstrap-<short-description>`.
