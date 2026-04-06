# Checklists

## Before finishing

- [ ] Feature branch created and checked out before first file edit (or deviation explicitly called out)
- [ ] Change set is small and focused (no unrelated refactors)
- [ ] New or changed behavior has tests added or updated
- [ ] Relevant tests for impacted API/web areas (`apps/api`, `apps/web`) have been run
- [ ] Edge cases and failure paths considered for new logic

- [ ] If API or shared interfaces changed, dependent code paths are verified
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
