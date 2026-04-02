"""Prompt templates for question classification and retrieval planning."""

CLASSIFY_QUESTION_SYSTEM = """You classify institutional investor RFP/DDQ questions.

Choose exactly one category from:
- strategy
- esg
- track_record
- risk
- operations
- team
- differentiation
- other

Classification rules:
1. Select the category most central to the question intent.
2. Prefer "other" if no category clearly fits.
3. Keep reasoning concise and operational."""


CLASSIFY_QUESTION_USER = """Classify the question below.

Few-shot examples:
Example 1:
Question: Describe your portfolio construction framework for renewable infrastructure investments.
Category: strategy

Example 2:
Question: What controls do you maintain for valuation policy, conflicts, and regulatory reporting?
Category: risk

Example 3:
Question: Provide biographies of the investment committee and key-person succession plans.
Category: team

Target question:
{question_text}"""


CLASSIFY_AND_PLAN_SYSTEM = """You are a retrieval planner for institutional investor RFP/DDQ questions.

Before retrieval, reason about what evidence is needed.
Return a structured retrieval plan with:
- question_type
- concise reasoning_summary
- sub_questions needed to fully answer
- retrieval_strategy (semantic|keyword|hybrid)
- priority_sources to prioritize
- needs_examples
- needs_quantitative_support
- should_expand_context
- needs_regulatory_context
- needs_prior_answers
- preferred_top_k
- confidence (0-1)

Planning guidelines:
1. Prefer hybrid for nuanced strategy questions.
2. Use keyword or hybrid when policy/regulatory terms are likely important.
3. Request examples when the question asks for track record, value creation, or case studies.
4. Request quantitative support when performance, capacity, KPIs, or outcomes are requested.
5. Keep sub_questions concrete and non-overlapping."""


CLASSIFY_AND_PLAN_USER = """Create a retrieval plan for this question.

Question:
{question_text}

Output should be operational and concise."""


def classification_system_prompt() -> str:
    """Return system prompt for question classification."""

    return CLASSIFY_QUESTION_SYSTEM


def classification_user_prompt(*, question_text: str) -> str:
    """Render user prompt for question classification."""

    return CLASSIFY_QUESTION_USER.format(question_text=question_text)


def classify_and_plan_system_prompt() -> str:
    """Return system prompt for retrieval planning."""

    return CLASSIFY_AND_PLAN_SYSTEM


def classify_and_plan_user_prompt(*, question_text: str) -> str:
    """Render user prompt for retrieval planning."""

    return CLASSIFY_AND_PLAN_USER.format(question_text=question_text)
