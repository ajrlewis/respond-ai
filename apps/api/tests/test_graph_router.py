from app.graph.router import route_evidence_evaluation, route_review


def test_route_review_defaults_to_revise_for_unknown_action() -> None:
    assert route_review({"review_action": "approve"}) == "approve"
    assert route_review({"review_action": "revise"}) == "revise"
    assert route_review({"review_action": "unexpected"}) == "revise"


def test_route_evidence_evaluation_enforces_bounded_retry() -> None:
    assert route_evidence_evaluation({"evidence_evaluation": {"recommended_action": "retrieve_more"}, "retry_count": 0}) == "retrieve_more"
    assert route_evidence_evaluation({"evidence_evaluation": {"recommended_action": "retrieve_more"}, "retry_count": 1}) == "proceed"
    assert route_evidence_evaluation({"evidence_evaluation": {"recommended_action": "proceed_with_caveats"}, "retry_count": 0}) == "proceed"
