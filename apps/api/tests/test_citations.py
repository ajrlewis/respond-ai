from app.services.citations import extract_answer_citations, normalize_answer_citations
from app.services.confidence import format_evidence_blob


def _sample_evidence() -> list[dict]:
    return [
        {
            "chunk_id": "32deb755-b17c-45d7-a47a-3b922869e6d8",
            "document_filename": "prior_rfp_answers.md",
            "chunk_index": 2,
            "text": "Sample 1",
        },
        {
            "chunk_id": "171f4074-5835-48b8-9a4d-3392cc8f0b14",
            "document_filename": "energy_transition_strategy.md",
            "chunk_index": 1,
            "text": "Sample 2",
        },
        {
            "chunk_id": "52c83301-a5ae-4d95-8927-86a15ba647de",
            "document_filename": "energy_transition_strategy.md",
            "chunk_index": 0,
            "text": "Sample 3",
        },
        {
            "chunk_id": "65fcff7b-e66b-4469-8228-5592f4af0b7c",
            "document_filename": "portfolio_examples.md",
            "chunk_index": 2,
            "text": "Sample 4",
        },
    ]


def test_normalize_answer_citations_maps_doc_refs_and_uuid_fragments() -> None:
    evidence = _sample_evidence()
    answer = (
        "The strategy supports low-carbon assets [3c83301-a5ae-4d95-8927-86a15ba647de] "
        "and includes grid projects [portfolio_examples.md#chunk-2]."
    )

    normalized = normalize_answer_citations(answer, evidence)

    assert "[3]" in normalized
    assert "[4]" in normalized
    assert "3c83301-a5ae-4d95-8927-86a15ba647de" not in normalized
    assert "portfolio_examples.md#chunk-2" not in normalized


def test_normalize_answer_citations_leaves_non_citation_brackets_untouched() -> None:
    evidence = _sample_evidence()
    answer = "Use internal controls [internal] and keep this marker [Note A]."

    normalized = normalize_answer_citations(answer, evidence)

    assert normalized == answer


def test_extract_answer_citations_supports_numeric_and_doc_chunk_tokens() -> None:
    citations = extract_answer_citations(
        "Response with numeric [2], path [policy.md#chunk-4], and text [internal]."
    )

    assert citations == ["[2]", "[policy.md#chunk-4]"]


def test_format_evidence_blob_omits_chunk_id_values() -> None:
    blob = format_evidence_blob(_sample_evidence())

    assert "chunk_id=" not in blob
    assert "[1] source=prior_rfp_answers.md#chunk-2" in blob
