# Code Style

- Prefer clear, typed, and maintainable code over clever or overly abstract solutions.
- Use type annotations where standard for the codebase (e.g. Python typing, TypeScript types).

- Refactor obvious duplication when it improves clarity and stays within the scope of the task.
- Avoid introducing unnecessary abstractions or premature generalization.

- Add docstrings for public APIs, modules, and non-obvious logic.
- Keep docstrings concise and focused on behavior and intent.

- Use comments to explain intent, tradeoffs, and non-obvious decisions.
- Avoid comments that simply restate what the code is doing.

- Follow existing project conventions and patterns before introducing new ones.
- Prefer consistency with the surrounding code over personal preference.
- In React/Next.js code, prefer focused components and custom hooks over large mixed-responsibility files when it improves clarity and testability.
- In backend LLM code, keep concerns separated (`nodes`, `prompts`, `ai`, `core`) instead of mixing prompts, provider calls, and domain logic in one file.
- Prefer explicit `small`/`large` model selection constants per task over ad-hoc model choices scattered across files.

## File size guardrails

- Soft limit: `300` lines per file. Consider splitting once a file crosses this size.
- Hard limit: `500` lines per file. Split unless there is a strong documented reason.
- Prohibited: `1000+` line files. Refactor into smaller modules before merging.
