"""Prompt templates for question classification."""

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


def classification_system_prompt() -> str:
    """Return system prompt for question classification."""

    return CLASSIFY_QUESTION_SYSTEM


def classification_user_prompt(*, question_text: str) -> str:
    """Render user prompt for question classification."""

    return CLASSIFY_QUESTION_USER.format(question_text=question_text)
