# Workflow Rules

Use these steps for each non-trivial task.

## Monorepo defaults

- API path default: `apps/api`
- Web path default: `apps/web`
- If a repo uses different paths, update `.agents/COMMANDS.md` and `.agents/MEMORY.md` in the same change.

## Git preflight (required before first edit)

Run this preflight before creating, editing, or deleting files:

1. Confirm you are inside a git repository.
2. Check whether the repository has at least one commit.
3. Determine the current branch.
4. If the repo has no commits (unborn history):
   - ensure branch name is `main` first
   - create and switch to `feat/bootstrap-<short-description>` before scaffolding files
5. If the repo has commits and current branch is `main` or `master`, create and switch to a feature branch before any edits.
6. If the repo has commits and uses a different default branch name, do not rename it; create/switch to a feature branch from that baseline.

Edits made before passing this preflight must be treated as workflow deviations and called out in the final summary.

## Feature workflow

1. Complete the Git preflight section above before the first file edit.
2. For non-empty repositories, start from a clean working tree and an up-to-date baseline branch.
3. Keep the change small and scoped to one objective.
4. Implement the change and add or update tests in the same feature branch.
5. Run relevant tests for touched areas before finishing.
6. If runtime, dependency, build, or deployment behavior changed, update related Docker/dev/prod configuration as needed.
7. Update docs or agent instructions if commands, workflows, or behavior changed.
8. Commit the changes on the feature branch with a clear, descriptive message (for example: `feat(web): add vitest setup`). If the user requests no commit, state that explicitly in the final summary.
9. Prepare a PR summary with what changed, how it was tested, and any rollout or follow-up notes.

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

## Backend LLM workflow

- Route backend LLM calls through LangChain abstractions instead of calling provider SDKs directly inside API handlers.
- Keep provider usage provider-agnostic with adapters/config for OpenAI, Anthropic, and Google.
- Use Pydantic schemas for structured outputs and validate parsed model responses before downstream usage.
- Declare model tiers explicitly for each task:
  - `small` for routing, classification, extraction, and short transforms
  - `large` for complex reasoning, synthesis, and long-form generation
- Keep LLM code modular by splitting `nodes`, `prompts`, `ai`, and `core` responsibilities into separate files.

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

## Frontend testing strategy (Next.js)

- Use Vitest + React Testing Library for web unit tests.
- Do not require a unit test for every component; prioritize components and hooks with meaningful logic or state transitions.
- For purely presentational components, prefer lightweight smoke coverage or indirect coverage via parent/component integration tests.
- Prefer extracting logic into focused hooks/components instead of growing large mixed files when behavior becomes hard to test.

## File size policy

- Treat `300` lines as a soft limit and start planning a split.
- Treat `500` lines as a hard limit and split before merging, unless there is a clearly documented exception.
- Do not merge `1000+` line source files.
