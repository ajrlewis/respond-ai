from app.ai.schemas import DraftMetadataResult, EvidenceSynthesisResult
from app.graph.nodes import (
    active_evidence,
    append_answer_version,
    build_confidence_notes,
    build_structured_confidence_payload,
    render_confidence_notes,
    curate_evidence,
    mark_excluded_evidence,
    render_prompt_template,
)


def test_curate_evidence_dedupes_and_boosts_multi_method() -> None:
    candidates = [
        {
            "chunk_id": "1",
            "document_filename": "a.md",
            "score": 0.3,
            "retrieval_method": "semantic",
        },
        {
            "chunk_id": "1",
            "document_filename": "a.md",
            "score": 0.4,
            "retrieval_method": "keyword",
        },
        {
            "chunk_id": "2",
            "document_filename": "b.md",
            "score": 0.2,
            "retrieval_method": "keyword",
        },
    ]

    curated = curate_evidence(candidates, final_k=5)

    assert len(curated) == 2
    assert curated[0]["chunk_id"] == "1"
    assert "keyword" in curated[0]["retrieval_method"]
    assert "semantic" in curated[0]["retrieval_method"]


def test_build_confidence_notes_mentions_counts() -> None:
    curated = [
        {"document_filename": "a.md", "score": 0.5, "retrieval_method": "semantic+keyword"},
        {"document_filename": "b.md", "score": 0.4, "retrieval_method": "keyword"},
    ]

    notes = build_confidence_notes(curated)

    assert "2 supporting chunks" in notes
    assert "2 source documents" in notes


def test_render_prompt_template_classify_question() -> None:
    rendered = render_prompt_template(
        "classify_question",
        "user",
        question_text="What controls govern your valuation process?",
    )

    assert "Few-shot examples" in rendered
    assert "What controls govern your valuation process?" in rendered


def test_build_structured_confidence_notes() -> None:
    metadata = DraftMetadataResult(
        citations_used=["[policy.md#chunk-2]"],
        coverage_notes="Core policy controls are covered.",
        confidence_notes="Reviewer should verify 2025 figures.",
        missing_info_notes=["No external assurance statement located."],
        compliance_flags=["Potential promissory language detected: 'guaranteed'."],
    )
    synthesis = EvidenceSynthesisResult(
        selected_chunk_ids=["chunk-1"],
        rejected_chunk_ids=[],
        contradictions_found=[],
        missing_information=["No external assurance statement located."],
        evidence_summary="Evidence supports governance process, but assurance detail is missing.",
    )

    payload = build_structured_confidence_payload(
        metadata=metadata,
        synthesis=synthesis,
        retrieval_notes="Retrieved 4 supporting chunks.",
    )
    notes = render_confidence_notes(payload)

    assert "Confidence score (heuristic)" in notes
    assert "Compliance status: Needs review." in notes
    assert "No external assurance statement located." in notes
    assert "Retrieved 4 supporting chunks." in notes


def test_mark_excluded_evidence_and_filter_active() -> None:
    evidence = [
        {"chunk_id": "c1", "document_filename": "a.md", "chunk_index": 1, "text": "One"},
        {"chunk_id": "c2", "document_filename": "b.md", "chunk_index": 2, "text": "Two"},
    ]

    marked = mark_excluded_evidence(evidence, excluded_keys=["c2"])
    filtered = active_evidence(marked)

    assert marked[0]["excluded_by_reviewer"] is False
    assert marked[1]["excluded_by_reviewer"] is True
    assert len(filtered) == 1
    assert filtered[0]["chunk_id"] == "c1"


def test_append_answer_version_skips_adjacent_duplicates() -> None:
    versions = append_answer_version([], "Initial draft.", "draft")
    versions = append_answer_version(versions, "Initial draft.", "revision")
    versions = append_answer_version(versions, "Revised draft.", "revision")

    assert len(versions) == 2
    assert versions[0]["label"] == "Draft 1"
    assert versions[1]["label"] == "Draft 2"
