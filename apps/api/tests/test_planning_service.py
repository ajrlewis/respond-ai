import asyncio

from app.ai.errors import AIProviderError
from app.ai.schemas import RetrievalPlanResult
from app.services import planning


def test_plan_retrieval_returns_structured_plan(monkeypatch) -> None:
    expected_plan = RetrievalPlanResult(
        question_type="strategy",
        confidence=0.81,
        sub_questions=["What is the fund strategy?"],
        retrieval_strategy="hybrid",
        priority_sources=["strategy"],
    )
    captured: dict[str, object] = {}

    class FakePlanner:
        async def ainvoke(self, *, system_prompt: str, user_prompt: str, temperature: float):
            captured["system_prompt"] = system_prompt
            captured["user_prompt"] = user_prompt
            captured["temperature"] = temperature
            return expected_plan

    def _fake_get_structured_model(*, schema, purpose):
        captured["schema"] = schema
        captured["purpose"] = purpose
        return FakePlanner()

    monkeypatch.setattr(planning, "get_structured_model", _fake_get_structured_model)

    result = asyncio.run(planning.plan_retrieval("Describe your strategy."))

    assert result == expected_plan
    assert captured["schema"] is RetrievalPlanResult
    assert captured["purpose"] == "planning"
    assert captured["temperature"] == 0


def test_plan_retrieval_raises_when_planner_unavailable(monkeypatch) -> None:
    def _raise_unavailable(*, schema, purpose):
        raise AIProviderError("planner unavailable")

    monkeypatch.setattr(planning, "get_structured_model", _raise_unavailable)

    try:
        asyncio.run(planning.plan_retrieval("Describe your strategy."))
        raise AssertionError("Expected AIProviderError when planner model is unavailable")
    except AIProviderError as exc:
        assert "planner unavailable" in str(exc)
