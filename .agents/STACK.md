# Stack Summary

## Backend

- Default location: `apps/api`
- Language: Python
- Runtime/package tooling: `uv`
- API framework: FastAPI
- ORM / query layer: SQLAlchemy (async usage)
- Testing: `pytest`
- Agent framework options: LangGraph / LangChain
- Database: PostgreSQL with `pgvector` (vector similarity search)
- Migrations: Alembic

## Frontend

- Default location: `apps/web`
- Framework: Next.js (App Router)
- Tooling/runtime: `bun`

## Infrastructure

- Optional shared location: `packages/`
- Optional infra location: `infra/`
- Containers: Docker for development and production
- Deploy frontends: two Vercel projects
- CI/CD: GitHub Actions building Docker images
