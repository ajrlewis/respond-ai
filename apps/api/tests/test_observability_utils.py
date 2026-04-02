from app.services.observability import determine_graph_status, estimate_cost_usd, summarize_workflow_state


def test_determine_graph_status_recognizes_pause_and_completion() -> None:
    assert determine_graph_status({"status": "awaiting_review"}, default_status="completed") == "paused_for_review"
    assert determine_graph_status({"status": "approved", "final_answer": "Done"}, default_status="paused_for_review") == "completed"


def test_estimate_cost_uses_default_model_pricing() -> None:
    cost = estimate_cost_usd(model_name="gpt-4o-mini", input_tokens=1000, output_tokens=500)

    assert cost is not None
    assert cost > 0


def test_summarize_workflow_state_includes_key_counts() -> None:
    summary = summarize_workflow_state(
        {
            "session_id": "abc",
            "question_text": "How do you govern valuation policy?",
            "retrieved_evidence": [{"chunk_id": "1"}, {"chunk_id": "2"}],
            "curated_evidence": [{"chunk_id": "1"}],
            "excluded_evidence_keys": ["2"],
            "draft_answer": "Draft",
            "final_answer": "Final",
            "confidence_payload": {"score": 0.8, "evidence_gaps": ["Missing external assurance"]},
        }
    )

    assert summary["retrieved_evidence_count"] == 2
    assert summary["curated_evidence_count"] == 1
    assert summary["excluded_evidence_count"] == 1
    assert summary["draft_chars"] == 5
    assert summary["final_chars"] == 5
    assert summary["evidence_gap_count"] == 1
    assert summary["question_hash"] is not None
