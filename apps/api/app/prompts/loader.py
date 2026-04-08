"""Prompt asset loader with `config/prompts` override support."""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any, Mapping, Literal

from app.core.client_config import resolve_config_path

TemplateName = Literal["system", "user"]

_PROMPTS_ROOT = Path(__file__).resolve().parent
_CONFIG_PROMPTS_ROOT = resolve_config_path("prompts")
_PROMPT_TEMPLATE_ROOTS = (_CONFIG_PROMPTS_ROOT, _PROMPTS_ROOT)


@dataclass(frozen=True, slots=True)
class PromptPair:
    """Raw system and user prompt templates for one prompt group."""

    system: str
    user: str


@lru_cache(maxsize=256)
def _load_prompt_text(prompt_name: str, template_name: TemplateName) -> str:
    for root in _PROMPT_TEMPLATE_ROOTS:
        path = root / prompt_name / f"{template_name}.md"
        if not path.exists():
            continue

        content = path.read_text(encoding="utf-8").strip()
        if not content:
            raise RuntimeError(f"Prompt template is empty: {prompt_name}/{template_name}")
        return content

    raise RuntimeError(f"Prompt template not found: {prompt_name}/{template_name}")


def load_system_prompt(prompt_name: str) -> str:
    """Load a system prompt markdown asset by name."""

    return _load_prompt_text(prompt_name, "system")


def load_user_prompt(prompt_name: str) -> str:
    """Load a user prompt markdown template by name."""

    return _load_prompt_text(prompt_name, "user")


def load_prompt_pair(prompt_name: str) -> PromptPair:
    """Load raw system+user templates for a prompt group."""

    return PromptPair(system=load_system_prompt(prompt_name), user=load_user_prompt(prompt_name))


def render_user_prompt(prompt_name: str, context: Mapping[str, Any] | None = None) -> str:
    """Render user prompt template with `str.format` context variables."""

    template = load_user_prompt(prompt_name)
    values = {key: value for key, value in dict(context or {}).items()}
    try:
        return template.format(**values)
    except KeyError as exc:
        missing_key = str(exc).strip("'\"")
        raise RuntimeError(f"Missing prompt context key '{missing_key}' for prompt '{prompt_name}/user'.") from exc


def render_prompt_template(prompt_name: str, template_name: TemplateName, **context: Any) -> str:
    """Backwards-compatible prompt renderer used by graph nodes and tests."""

    if template_name == "system":
        return load_system_prompt(prompt_name)
    if template_name == "user":
        return render_user_prompt(prompt_name, context)
    raise RuntimeError(f"Unsupported prompt template type: {template_name}")


__all__ = [
    "PromptPair",
    "load_prompt_pair",
    "load_system_prompt",
    "load_user_prompt",
    "render_prompt_template",
    "render_user_prompt",
]
