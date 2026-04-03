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

## Example update

- API path changed from `apps/api` to `services/api`
- Updated commands now use `cd services/api && uv run pytest -q`

## Confirmed repo facts

- API app lives in `apps/api` with FastAPI entrypoint `app.main:app`.
- Web app lives in `apps/web` using Next.js App Router and bun scripts.
- Docker orchestration file is `docker-compose.yml` with `postgres`, `api`, and `web` services.
- Postgres service in `docker-compose.yml` sets `security_opt: [seccomp=unconfined]` to allow `initdb` on hosts with restrictive seccomp defaults.
- API service in `docker-compose.yml` sets `security_opt: [seccomp=unconfined]`, mounts `./data` to `/app/data` read-only, and pins BLAS thread env vars to 1 for restrictive Docker hosts.
- Seed ingestion command is `cd apps/api && uv run python scripts/seed_data.py`.
- API settings load `.env` from `apps/api/.env` first, then repo-root `.env` as fallback.
- Database connectivity is configured with a single `DATABASE_URL` for API, SQLAlchemy sessions, scripts, and LangGraph checkpointer.
- Docker-first seed command is `docker compose exec -T api uv run python scripts/seed_data.py`.
- API request handlers use async DB sessions from `app.core.database.get_db` (`AsyncSessionLocal`), while sync `SessionLocal` remains for scripts/seed flows.
- LangGraph runtime executes asynchronously with `AsyncPostgresSaver` and `graph.ainvoke(...)` in `app/graph/runtime.py`.
- Prompt assets are centralized in `apps/api/app/prompts/<task>/{system,user}.md` and loaded via `app.prompts.loader`.
- AI model/provider access is centralized in `apps/api/app/ai` through a thin LangChain-backed factory (`get_chat_model`, `get_structured_model`, `get_embedding_model`) without a custom provider-class hierarchy.
- Provider/model routing is environment-driven (`AI_PROVIDER`, `LARGE_LLM_PROVIDER`, `SMALL_LLM_PROVIDER`, `EMBEDDING_PROVIDER`) with optional eval judge routing (`EVAL_LLM_PROVIDER`, `EVAL_LLM_MODEL`).
- Schema boundary convention: `apps/api/app/ai/schemas` is for structured LLM outputs; `apps/api/app/schemas` is for API/application/persistence contracts.
- LangGraph flow inserts `polish_response` after both `draft_response` and `revise_response` to enforce final investor-tone cleanup before `human_review`.
- API logging level is configured via `LOGGING_LEVEL` (default `INFO`) in `apps/api/app/core/config.py` and applied by `app/core/logging.py`.
- API emits lifecycle/debug logs across routes, graph runtime/nodes, and service/database layers using module loggers (`logging.getLogger(__name__)`).
- API startup import smoke coverage lives in `apps/api/tests/test_app_startup.py` to catch startup-time import/runtime wiring regressions.
- Session payloads now include `current_node`, and `GET /api/questions/thread/{thread_id}` supports thread-based progress polling while `POST /api/questions/ask` is running.
- Session API payload includes structured `confidence` metadata and `answer_versions` snapshots for revision history/diff UX.
- `POST /api/questions/{session_id}/review` accepts `excluded_evidence_keys` and `reviewed_evidence_gaps`; approve is rejected when evidence gaps exist and are not acknowledged.
- Session payload now includes `evidence_gap_count`, `requires_gap_acknowledgement`, `evidence_gaps_acknowledged`, and `evidence_gaps_acknowledged_at` to support approval gating in review UI.
- Session-level evidence-gap acknowledgement is reset when a new draft/revision is generated, and approval is server-enforced unless evidence gaps are acknowledged.
- LangGraph main flow now runs `ask -> classify_and_plan -> adaptive_retrieve -> evaluate_evidence -> draft_response -> polish_response -> human_review`, with bounded one-time retry routing from `evaluate_evidence` back to `adaptive_retrieve` when evidence is insufficient.
- `rfp_sessions` persists structured planning/evaluation artifacts in `retrieval_plan_payload`, `retrieval_strategy_used`, `retrieval_metadata_payload`, `evidence_evaluation_payload`, `selected_evidence_payload`, `rejected_evidence_payload`, and `retry_count`.
- Drafting now consumes planner + evidence-evaluation context and selected evidence, while confidence payloads include retrieval strategy, evaluator coverage, recommended action, and selected/rejected chunk ids.
- Draft history APIs are available at `GET /api/questions/{session_id}/drafts`, `GET /api/questions/{session_id}/drafts/{draft_id}`, and `GET /api/questions/{session_id}/drafts/compare?left=<id>&right=<id>`.
- Approval finalization writes immutable governance metadata on `rfp_sessions` (`final_version_number`, `approved_at`, `reviewer_action`, `reviewer_id`) plus `final_audit_payload`, and approved sessions are locked from further `POST /api/questions/{session_id}/review` actions.
- Final audit snapshot retrieval is exposed at `GET /api/questions/{session_id}/audit` and returns only approved-session immutable audit data.
- Observability tables include `graph_runs`, `node_runs`, `tool_runs`, `llm_calls`, and `session_metrics` for workflow/model/token telemetry persisted in Postgres.
- Offline eval runner command is `cd apps/api && uv run python scripts/run_evals.py --limit 50`.
- Eval API endpoints are `POST /api/evals/run`, `GET /api/evals/runs`, and `GET /api/evals/runs/{run_id}`.
- Graph node implementations are split under `apps/api/app/graph/nodes/` as thin orchestration adapters; planning, evidence analysis, drafting/revision/polish, and finalization business logic live in `apps/api/app/services/{planning,evidence_analysis,drafting,finalization}.py`.
- Web workflow UI is organized under `apps/web/src/components/workflow/` with orchestration hooks in `apps/web/src/hooks/use-workflow.ts` and `apps/web/src/hooks/use-draft-history.ts`; `apps/web/src/components/workflow-shell.tsx` is a thin re-export to the workflow container.
