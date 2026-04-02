from app.evals.evaluators import SessionEvalInput, evaluate_session


def test_evaluate_session_scores_and_passes_for_strong_record() -> None:
    result = evaluate_session(
        SessionEvalInput(
            session_id="s1",
            approved=True,
            has_final_answer=True,
            num_retrieved_chunks=6,
            num_cited_chunks=3,
            num_revision_rounds=1,
            review_event_count=2,
            time_to_first_draft_ms=20_000,
            time_to_approval_ms=10 * 60_000,
            total_tokens=2500,
            estimated_cost_usd=0.01,
            has_retrieval_plan=True,
            planner_sub_question_count=3,
            retrieval_strategy_used="hybrid",
            evidence_coverage="strong",
            recommended_action="proceed",
            missing_information_count=0,
            retrieval_retry_count=0,
        )
    )

    assert result.passed is True
    assert result.overall_score >= 0.7
    assert len(result.metrics) == 7


def test_evaluate_session_flags_weak_grounding() -> None:
    result = evaluate_session(
        SessionEvalInput(
            session_id="s2",
            approved=False,
            has_final_answer=False,
            num_retrieved_chunks=8,
            num_cited_chunks=0,
            num_revision_rounds=0,
            review_event_count=0,
            time_to_first_draft_ms=None,
            time_to_approval_ms=None,
            total_tokens=10_000,
            estimated_cost_usd=0.3,
            has_retrieval_plan=False,
            planner_sub_question_count=0,
            retrieval_strategy_used=None,
            evidence_coverage="weak",
            recommended_action="retrieve_more",
            missing_information_count=3,
            retrieval_retry_count=0,
        )
    )

    grounding = next(metric for metric in result.metrics if metric.name == "grounding")
    review_process = next(metric for metric in result.metrics if metric.name == "review_process")
    planning = next(metric for metric in result.metrics if metric.name == "planning_quality")
    evidence = next(metric for metric in result.metrics if metric.name == "evidence_readiness")

    assert grounding.passed is False
    assert review_process.passed is False
    assert planning.passed is False
    assert evidence.passed is False
    assert result.passed is False
