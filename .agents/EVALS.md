# Evals

Use this file before finishing any non-trivial task.

The goal is to verify that the change is complete, follows repo instructions, and is honestly reported.

## Workflow eval

- Did the work follow `.agents/WORKFLOWS.md`?
- Was Git preflight completed before any file edit?
- Was a feature branch created before the first code edit? If not, is the deviation explicitly acknowledged?
- For non-empty repos, were edits avoided on `main`/`master`?
- For empty/unborn repos, was `main` established before creating a bootstrap feature branch?
- Was the change kept small and scoped to the task?
- Were unrelated refactors avoided?
- Were docs or agent instructions updated if behavior, commands, or workflows changed?

## Command eval

- Were commands taken from `.agents/COMMANDS.md` instead of guessed?
- If a command was missing or incorrect, was `.agents/COMMANDS.md` updated?
- If actual app paths differ from template defaults, were commands and memory updated accordingly?

## Code quality eval

- Does the code follow `.agents/CODE_STYLE.md`?
- Is the implementation clear, typed, and maintainable?
- Were comments and docstrings added where they help explain intent or non-obvious behavior?
- Was unnecessary abstraction avoided?
- For backend LLM work, are `nodes`, `prompts`, `ai`, and `core` concerns kept separated?
- Do touched files stay within file-size guardrails (soft `300`, hard `500`, no `1000+` files)?

## Test eval

- Were tests added or updated for new or changed behavior?
- Were relevant tests run for impacted areas?
- For web unit tests, does the setup use Vitest + React Testing Library?
- Do web tests prioritize behavior-heavy components/hooks instead of requiring tests for every presentational component?
- If tests were not run, is that stated explicitly in the final summary?
- Were edge cases and failure paths considered?

## Integration eval

- If backend, frontend, or API behavior changed, were dependent code paths verified?
- If shared interfaces changed, were affected consumers checked?
- If runtime, dependency, build, or deployment behavior changed, were Docker/dev/prod implications reviewed?
- For backend LLM integrations, are provider calls routed via LangChain with provider-agnostic adapters (OpenAI/Anthropic/Google)?
- For structured outputs, are Pydantic schemas used and validated before dependent logic executes?
- Is model selection explicit (`small` vs `large`) and aligned to task complexity?

## Database eval

- If schema or persisted data structures changed, was an Alembic migration created or updated?
- If migrations changed, was the upgrade/downgrade path reviewed or tested?
- If pgvector usage changed, were related queries and indexes verified?

## Memory eval

- Were any stable repo facts discovered, confirmed, or changed?
- If yes, were they added to `.agents/MEMORY.md`?
- Does `.agents/MEMORY.md` contain only durable facts, not task notes or reasoning?

## Completion eval

Before finishing, confirm that the final response clearly states:

- what changed
- what tests were run
- what was not verified
- the final branch name and commit message (or explicitly that no commit was made by request)
- any remaining risks, assumptions, or follow-up work

If any checklist item was not completed, say so explicitly instead of implying full completion.
