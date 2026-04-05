import pytest

from app.prompts import load_prompt_pair, load_system_prompt, render_prompt_template, render_user_prompt


def test_load_prompt_pair_reads_markdown_assets() -> None:
    pair = load_prompt_pair("classify_question")

    assert "Choose exactly one category" in pair.system
    assert "Target question:" in pair.user


def test_render_user_prompt_fills_template_context() -> None:
    rendered = render_user_prompt(
        "classify_question",
        {"question_text": "How do you monitor valuation risk?"},
    )

    assert "How do you monitor valuation risk?" in rendered


def test_render_user_prompt_raises_for_missing_context() -> None:
    with pytest.raises(RuntimeError):
        render_user_prompt("classify_question", {})


def test_render_prompt_template_supports_system_alias() -> None:
    rendered = render_prompt_template("draft_answer", "system")

    assert rendered == load_system_prompt("draft_answer")
