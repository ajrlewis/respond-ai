import pytest

from app.prompts import loader as prompt_loader
from app.prompts import load_prompt_pair, load_system_prompt, render_prompt_template, render_user_prompt


@pytest.fixture(autouse=True)
def _clear_prompt_cache() -> None:
    prompt_loader._load_prompt_text.cache_clear()
    yield
    prompt_loader._load_prompt_text.cache_clear()


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


def test_load_system_prompt_prefers_client_override(tmp_path, monkeypatch) -> None:
    config_prompts = tmp_path / "config-prompts"
    default_prompts = tmp_path / "default-prompts"
    (config_prompts / "draft_answer").mkdir(parents=True)
    (default_prompts / "draft_answer").mkdir(parents=True)

    (config_prompts / "draft_answer" / "system.md").write_text("override system prompt", encoding="utf-8")
    (default_prompts / "draft_answer" / "system.md").write_text("default system prompt", encoding="utf-8")

    monkeypatch.setattr(prompt_loader, "_PROMPT_TEMPLATE_ROOTS", (config_prompts, default_prompts))

    assert load_system_prompt("draft_answer") == "override system prompt"


def test_load_system_prompt_falls_back_to_default_prompt_tree(tmp_path, monkeypatch) -> None:
    config_prompts = tmp_path / "config-prompts"
    default_prompts = tmp_path / "default-prompts"
    (default_prompts / "classify_question").mkdir(parents=True)

    (default_prompts / "classify_question" / "system.md").write_text("default classify system", encoding="utf-8")
    monkeypatch.setattr(prompt_loader, "_PROMPT_TEMPLATE_ROOTS", (config_prompts, default_prompts))

    assert load_system_prompt("classify_question") == "default classify system"
