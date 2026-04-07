# Checklists

## Before finishing

- [ ] Git preflight was completed before first file edit
- [ ] Feature branch created and checked out before first file edit (or deviation explicitly called out)
- [ ] No edits were started on `main` or `master` in non-empty repos
- [ ] For empty/unborn repos, `main` was established before creating `feat/bootstrap-<short-description>`
- [ ] Change set is small and focused (no unrelated refactors)
- [ ] New or changed behavior has tests added or updated
- [ ] Relevant tests for impacted API/web areas (`apps/api`, `apps/web`) have been run
- [ ] Web unit tests use Vitest + React Testing Library for component/hook behavior
- [ ] Web tests focus on behavior-heavy components/hooks rather than forcing tests for every presentational component
- [ ] Edge cases and failure paths considered for new logic

- [ ] If API or shared interfaces changed, dependent code paths are verified
- [ ] Backend LLM calls use LangChain abstraction layer with provider-agnostic adapters (OpenAI/Anthropic/Google) where applicable
- [ ] Structured LLM outputs are validated with Pydantic schemas
- [ ] LLM tasks use explicit `small`/`large` model declarations matching task complexity
- [ ] LLM code is split by concern (`nodes`, `prompts`, `ai`, `core`) instead of large mixed files
- [ ] Touched source files respect file-size policy (soft `300`, hard `500`, never `1000+`)
- [ ] If runtime, dependencies, or build behavior changed, Docker dev/prod config is updated as needed
- [ ] If Docker was introduced, `compose.yaml` runs successfully
- [ ] API and web containers start and are reachable
- [ ] Environment variables are wired correctly

- [ ] If database schema changed, Alembic migration created or updated
- [ ] If migration changed, upgrade/downgrade path reviewed or tested
- [ ] If pgvector usage changed, related queries/indexes verified

- [ ] Commands, workflows, or docs updated if behavior changed
- [ ] Changes are committed on the feature branch with a clear commit message (unless user asked not to commit)
- [ ] PR notes include what changed, how it was tested, and any risks or rollout considerations
