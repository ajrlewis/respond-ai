# RespondAI

RespondAI is a reusable AI system for drafting, reviewing, and approving **RFP/DDQ responses**, designed to be configured across different organisations.

This MVP focuses on a sustainable asset manager scenario: an AI workflow that drafts high-quality, compliant answers grounded in internal materials and requires human approval before finalization.

## Why This Use Case

RFP/DDQ response work is high-value, repetitive, and document-heavy. It benefits from:

- retrieval over existing institutional knowledge
- structured generation with citations
- a controlled human-in-the-loop (HITL) review gate

RespondAI is intentionally a **governed workflow product**, not a generic chatbot.

## Monorepo Structure

```text
respondai/
  docker-compose.yml
  .env.example
  README.md
  AGENTS.md
  data/
    docs/
      *.md
  apps/
    api/
      app/
      scripts/
      tests/
      Dockerfile
      pyproject.toml
    web/
      app/
      src/
      Dockerfile
      package.json
```

## Architecture Overview

### Backend (`apps/api`)

- FastAPI for API endpoints
- LangGraph for orchestrated workflow state transitions
- PostgreSQL for business and source data
- pgvector for semantic retrieval
- LangGraph PostgresSaver for graph checkpoints and pause/resume
- Provider-agnostic AI layer (`app/ai`) with configurable providers/models:
  - OpenAI
  - Anthropic
  - Google
- Purpose-based model routing from env (classification, cross-reference, drafting, revision, evaluation, embeddings)
- Structured outputs (Pydantic) for:
  - question classification
  - evidence synthesis/cross-reference
  - draft metadata extraction
  - revision intent extraction
  - optional LLM-judge evals

### Frontend (`apps/web`)

- Next.js App Router + TypeScript
- three-panel workflow UI (question intake, draft/review, evidence)
- typed API client and explicit workflow actions (approve/revise)
- citation click-to-focus linking between answer body and evidence cards
- revision history snapshots with inline diffing between draft versions
- reviewer source exclusion controls for revision re-drafts

### Database Layout

Three separate persistence concerns are implemented:

1. Source knowledge (RAG):

- `documents`
- `document_chunks`

2. Runtime execution (LangGraph):

- LangGraph checkpoints via PostgresSaver tables

3. Business workflow:

- `rfp_sessions`
- `rfp_reviews`

This separation keeps runtime mechanics independent from product state.

## LangGraph Agent Flow

```text
ask
→ classify_question
→ retrieve_evidence
→ cross_reference_evidence
→ draft_response
→ polish_response
→ human_review
├─ approve → finalize_response
└─ revise  → revise_response → polish_response → human_review
```

### Node behavior summary

1. `ask`: creates session and initializes state
2. `classify_question`: structured classification (`question_type`, confidence, retrieval strategy)
3. `retrieve_evidence`: hybrid semantic + keyword retrieval
4. `cross_reference_evidence`: structured evidence synthesis (selected/rejected ids, contradictions, gaps)
5. `draft_response`: plain-text investor-grade draft + structured draft metadata
6. `polish_response`: constrained tone/parser pass for formal investor style
7. `human_review`: HITL interrupt/pause point
8. `revise_response`: plain-text revision + structured revision intent/metadata
9. `finalize_response`: persists approved final answer

## Seed Data Summary

`data/docs/*.md` contains internal-style knowledge documents for the sustainable asset manager demo (firm overview, strategy, ESG, portfolio examples, process, risk, team, prior answers).

These markdown files are assumed to originate from PDF-to-markdown conversion (Docling or similar). The ingestion pipeline in `apps/api/scripts/seed_data.py`:

1. reads markdown files
2. parses heading structure
3. performs recursive chunking
4. generates embeddings via configured embedding provider/model
5. stores documents/chunks in PostgreSQL + pgvector

This is the RAG foundation used by the workflow.

## AI Configuration

The AI layer is provider-agnostic and supports configurable model selection across OpenAI, Anthropic, and Google. Structured outputs are used for classification, evidence selection, and evaluation tasks to improve reliability and reduce brittle prompt parsing.

At minimum, configure:

```env
AI_PROVIDER=openai
LARGE_LLM_PROVIDER=openai
LARGE_LLM_MODEL=gpt-4o
SMALL_LLM_PROVIDER=openai
SMALL_LLM_MODEL=gpt-4o-mini
EMBEDDING_PROVIDER=openai
EMBEDDING_MODEL=text-embedding-3-small

OPENAI_API_KEY=
ANTHROPIC_API_KEY=
GOOGLE_API_KEY=
```

Optional controls:

```env
AI_TEMPERATURE=0
AI_MAX_RETRIES=2
AI_TIMEOUT_SECONDS=60
ENABLE_LLM_JUDGE_EVALS=false
EVAL_LLM_PROVIDER=
EVAL_LLM_MODEL=
```

Mixed-provider deployments are supported. Example:
- `LARGE_LLM_PROVIDER=anthropic`
- `SMALL_LLM_PROVIDER=openai`
- `EMBEDDING_PROVIDER=openai`

Note: `EMBEDDING_PROVIDER=anthropic` is not supported in this stack; use `openai` or `google`.

## API Endpoints

- `GET /health`
- `POST /api/questions/ask`
- `POST /api/questions/{session_id}/review`
- `GET /api/questions/{session_id}`
- `GET /api/questions/{session_id}/drafts`
- `GET /api/questions/{session_id}/drafts/{draft_id}`
- `GET /api/questions/{session_id}/drafts/compare?left=<id>&right=<id>`
- `GET /api/questions/{session_id}/history`
- `GET /api/documents`

## Design Decisions

- **Postgres for app + vector storage**: simple operational model and strong relational + retrieval support.
- **LangGraph PostgresSaver**: durable checkpoints and clean pause/resume for HITL review.
- **Separate business tables from checkpoint state**: product state remains clear and queryable without coupling to internal graph mechanics.
- **Scoped single-workflow MVP**: one high-value workflow done well over an overbuilt multi-agent system.

## Future Extensions

- organization-level configuration profiles (tone, templates, taxonomies)
- additional workflows (DDQs, IC memos, portfolio analytics)
- integrations with CRM/data warehouse/document systems
- MCP exposure for external tool orchestration
- optional constrained web research where policy allows
- stronger auth, audit, and compliance controls

## How To Run

1. Copy environment variables:

```bash
cp .env.example .env
```

2. Set provider keys in `.env` for any providers you configure.
   Default config requires `OPENAI_API_KEY`.
   `DATABASE_URL` and `CHECKPOINT_DATABASE_URL` are for local runs (`localhost`);
   Docker uses `DOCKER_DATABASE_URL` and `DOCKER_CHECKPOINT_DATABASE_URL`.

3. Start the stack:

```bash
docker compose up --build
```

4. Seed markdown docs into Postgres + pgvector:

```bash
docker compose exec api uv run python scripts/seed_data.py
```

5. Open:

- Web UI: `http://localhost:3000`
- API docs: `http://localhost:8000/docs`

## Non-Docker Local Run (Copy/Paste)

```bash
# from repo root
cp .env.example .env

# set provider keys in .env (default: OPENAI_API_KEY)

# terminal 1: API
cd apps/api
uv sync --extra dev
uv run uvicorn app.main:app --reload
```

```bash
# terminal 2: seed embeddings (run once API + Postgres are available)
cd apps/api
uv run python scripts/seed_data.py
```

```bash
# terminal 3: web
cd apps/web
bun install
bun run dev
```

## Docker commands

```bash
# Build and start everything
docker compose up -d --build --remove-orphans

# Seed the database
docker compose exec -T api uv run python scripts/seed_data.py
# Inspect the database
docker compose exec postgres psql -U respondai -d respondai
```

web: http://localhost:3000/
api: http://localhost:8000/docs
