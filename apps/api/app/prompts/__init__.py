"""Centralized prompt rendering helpers."""

from collections.abc import Callable

from app.prompts.classification import (
    classify_and_plan_system_prompt,
    classify_and_plan_user_prompt,
    classification_system_prompt,
    classification_user_prompt,
)
from app.prompts.drafting import (
    analyze_evidence_system_prompt,
    analyze_evidence_user_prompt,
    draft_answer_system_prompt,
    draft_answer_user_prompt,
    evaluate_evidence_system_prompt,
    evaluate_evidence_user_prompt,
    polish_answer_system_prompt,
    polish_answer_user_prompt,
    revise_answer_system_prompt,
    revise_answer_user_prompt,
)


PromptRenderer = Callable[..., str]

_PROMPT_RENDERERS: dict[tuple[str, str], PromptRenderer] = {
    ("classify_question", "system"): classification_system_prompt,
    ("classify_question", "user"): classification_user_prompt,
    ("classify_and_plan", "system"): classify_and_plan_system_prompt,
    ("classify_and_plan", "user"): classify_and_plan_user_prompt,
    ("analyze_evidence", "system"): analyze_evidence_system_prompt,
    ("analyze_evidence", "user"): analyze_evidence_user_prompt,
    ("evaluate_evidence", "system"): evaluate_evidence_system_prompt,
    ("evaluate_evidence", "user"): evaluate_evidence_user_prompt,
    ("draft_answer", "system"): draft_answer_system_prompt,
    ("draft_answer", "user"): draft_answer_user_prompt,
    ("revise_answer", "system"): revise_answer_system_prompt,
    ("revise_answer", "user"): revise_answer_user_prompt,
    ("polish_answer", "system"): polish_answer_system_prompt,
    ("polish_answer", "user"): polish_answer_user_prompt,
}


def render_prompt_template(prompt_name: str, template_name: str, **context: str) -> str:
    """Render known prompts from centralized prompt modules."""

    key = (prompt_name, template_name)
    renderer = _PROMPT_RENDERERS.get(key)
    if not renderer:
        raise RuntimeError(f"Prompt template not found: {prompt_name}/{template_name}")
    return renderer(**context)
