# Project Shape (FastAPI + Next.js Monorepo)

This template assumes a monorepo with at least:

- `apps/api`: FastAPI backend and Python services
- `apps/web`: Next.js App Router frontend
- `packages/` (optional): shared libraries, config, or types
- `infra/` (optional): infrastructure/deployment files

Repos may customize paths. If they do, update `.agents/COMMANDS.md` and `.agents/MEMORY.md` to match the real layout.

## Backend expectations

- Python managed with `uv`
- Tests with `pytest`
- FastAPI API surface
- LLM calls should go through LangChain abstractions, not provider SDKs directly in route handlers
- Provider-agnostic LLM support (OpenAI / Anthropic / Google) via config-driven adapter selection
- Structured output contracts should use Pydantic schemas
- Model selection should use explicit task tiers (`small` for routing/classification/extraction, `large` for complex synthesis/reasoning)
- PostgreSQL plus `pgvector` for embeddings/search

## Backend module boundaries

For maintainability, prefer separating concerns into focused modules:

- `core/`: domain logic, business rules, and pure orchestration logic
- `ai/`: model/provider wiring and shared LLM client setup
- `prompts/`: prompt templates and prompt-building utilities
- `nodes/`: discrete LLM or tool steps with one responsibility per node file

## Frontend expectations

- Next.js App Router
- `bun` for web dependency and script execution
- Vitest + React Testing Library for web unit tests (components/hooks)

## Infra expectations

- Docker flow for local development and production images
- Two Vercel projects (typically one for production, one for preview/staging)
- GitHub Actions that build Docker images

## Docker

- Project may use Docker Compose for local orchestration
- Services typically include API, web, and database

## Fill in repo-specific details here

Document concrete paths, environment files, deployment names, and ownership for your real repo. Keep this section current as structure evolves.
