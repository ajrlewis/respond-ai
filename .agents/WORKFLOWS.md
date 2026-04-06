# Workflow Rules

Use these steps for each non-trivial task.

## Monorepo defaults

- API path default: `apps/api`
- Web path default: `apps/web`
- If a repo uses different paths, update `.agents/COMMANDS.md` and `.agents/MEMORY.md` in the same change.

## Feature workflow

1. Start from a clean working tree and an up-to-date default branch.
2. Create and checkout a feature branch **before** making any file edits.
3. If you started editing before creating a branch, immediately create/switch to a feature branch, keep the existing changes, and explicitly note the deviation in your final summary.
4. Keep the change small and scoped to one objective.
5. Implement the change and add or update tests in the same branch.
6. Run relevant tests for touched areas before finishing.
7. If runtime, dependency, build, or deployment behavior changed, update related Docker/dev/prod configuration as needed.
8. Update docs or agent instructions if commands, workflows, or behavior changed.
9. Commit the changes on the feature branch with a clear, descriptive message (for example: `feat(web): add vitest setup`). If the user requests no commit, state that explicitly in the final summary.
10. Prepare a PR summary with what changed, how it was tested, and any rollout or follow-up notes.

## Docker / containerization

- Prefer adding Docker only when local orchestration or deployment is needed.
- If needed, create Dockerfiles for each app and a root `compose.yaml` in the project repo.
- Keep Docker setup minimal and readable; avoid Kubernetes or overengineering by default.
- API container should run FastAPI with `uvicorn`.
- Web container should build and run Next.js.
- Database should use `postgres` with volume persistence.

## Backend / data changes

- If models, schema, or persisted data structures change, update and verify Alembic migrations.
- If migrations change, ensure upgrade/downgrade paths are valid where applicable.
- If vector storage, embeddings, or retrieval behavior changes, verify pgvector-related queries and indexes.

## Branch naming

Use readable names such as:

- `feat/<short-description>`
- `fix/<short-description>`
- `chore/<short-description>`

## Quality bar

- Add or update tests for new or changed behavior.
- Run relevant regression checks before opening or finalizing a PR.
- Avoid unrelated refactors in the same PR.
- Prefer incremental changes over broad rewrites.
