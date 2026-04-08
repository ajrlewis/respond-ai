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
- Document-centric drafting API is available at `/api/response-documents` (create, generate, save versions, compare versions, AI revise) and is used by the `review-v2` workspace.
- Docker Compose `api` service now runs `uv run alembic upgrade head` before `uvicorn` startup so schema head stays aligned at boot.
- Web app proxies `/api/*` and `/auth/*` via Next.js rewrites; configure `API_BASE_URL` for the upstream API target (Docker Compose defaults to `http://api:8000` for web build/runtime).
- Response-document workflow updates stream over SSE at `/api/response-documents/{document_id}/events`; `review-v2` generation/revision stages now consume these server events (run-id scoped) instead of UI-only stage timers.
- Web SSE clients can use `NEXT_PUBLIC_API_SSE_BASE_URL` (fallback: `NEXT_PUBLIC_API_BASE_URL`; localhost browser fallback: `http://localhost:8000`) so EventSource traffic bypasses Next.js rewrite buffering.
- Response-document generate/revise now run through the existing LangGraph runtime per question and forward node-start progress into document SSE stage updates.
- Response-document generation/revision must read post-run `RFPSession` snapshots using a fresh `AsyncSessionLocal` to avoid stale request-scoped identity-map state when LangGraph updates sessions concurrently.
- Generation SSE `stage_update` events now include `question_completed`, `question_id`, `content_markdown`, and `evidence_refs` metadata so the review-v2 generating view can populate each answer field and supporting sources immediately after each question completes.
- Web workspace UI now lives under `src/components/workspace`, `/` is the primary response workspace route, and `/review-v2` redirects to `/` for backward compatibility.
- Client deployment overrides now use repo-root `config/` (client/branding/workspace/retrieval JSON, `documents/sample-questions.md`, and optional prompt overrides under `config/prompts/*`) with a seeded Gresham House configuration.
- API prompt loading now resolves `config/prompts/<prompt>/<system|user>.md` first and falls back to `apps/api/app/prompts/<prompt>/<system|user>.md`; JSON client config loaders live in `app/core/client_config.py`.
- Frontend workspace branding now loads from API endpoint `/api/client-config/workspace` (client/branding/workspace payload) with env/default fallback in the web app.
- Frontend review-v2 workspace now applies `workspace.json` `ui_flags` and wording from `/api/client-config/workspace` (example-question visibility, source filename visibility, revision scope availability, revision submit/validation copy, and approval button/helper copy).
- Seed corpus markdown files now live under `config/documents/data`; `apps/api/scripts/seed_data.py` ingests from that directory (not `data/docs`).
- Docker Compose now mounts repo `./config` into API/worker containers at `/app/config` so client branding/workspace/prompt/document overrides load correctly in containerized runs.

## Example update

- API path changed from `apps/api` to `services/api`
- Updated commands now use `cd services/api && uv run pytest -q`
- Web unit test baseline uses Vitest + React Testing Library via `cd apps/web && bun run test`
- Backend LLM baseline uses LangChain with provider adapters (OpenAI/Anthropic/Google), Pydantic structured outputs, and explicit `small`/`large` model tiers.
- Branch safety baseline: run Git preflight before first edit; if repo is empty, establish `main` then branch to `feat/bootstrap-<short-description>`.
