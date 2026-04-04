"""Evidence retrieval, scoring, and evaluation services."""

from __future__ import annotations

import logging
import re
from typing import Literal

from sqlalchemy.ext.asyncio import AsyncSession

from app.ai import AIConfigurationError, AIProviderError, get_embedding_model, get_structured_model
from app.ai.schemas import EvidenceEvaluationResult, EvidenceSynthesisResult, RetrievalPlanResult
from app.core.config import settings
from app.graph.tools import expand_chunk_context, keyword_search, semantic_search
from app.prompts import render_prompt_template
from app.services.confidence import format_evidence_blob
from app.services.embeddings import EmbeddingService
from app.services.retrieval import RetrievalService

logger = logging.getLogger(__name__)


def _chunk_search_blob(chunk: dict) -> str:
    parts = [
        str(chunk.get("document_title", "")),
        str(chunk.get("document_filename", "")),
        str(chunk.get("text", "")),
    ]
    metadata = chunk.get("metadata", {})
    if isinstance(metadata, dict):
        for key in ("source_type", "category", "tags", "title"):
            value = metadata.get(key)
            if isinstance(value, str):
                parts.append(value)
            elif isinstance(value, list):
                parts.extend(str(item) for item in value if isinstance(item, str))
    return " ".join(parts).lower()


def _chunk_has_numeric_signal(chunk: dict) -> bool:
    text = _chunk_search_blob(chunk)
    if re.search(r"\b\d+(\.\d+)?\s?(%|mw|gw|kwh|kpi|x)\b", text):
        return True
    return any(token in text for token in ("capacity", "metric", "performance", "irr", "moic", "yield"))


def _chunk_has_example_signal(chunk: dict) -> bool:
    text = _chunk_search_blob(chunk)
    return any(token in text for token in ("example", "case study", "portfolio", "investment", "asset", "value creation"))


def _chunk_matches_priority(chunk: dict, priorities: list[str]) -> bool:
    blob = _chunk_search_blob(chunk)
    return any(priority and priority in blob for priority in priorities)


def evidence_item_key(item: dict) -> str:
    """Build a deterministic key for evidence filtering and UI selection."""

    chunk_id = str(item.get("chunk_id", "")).strip()
    if chunk_id:
        return chunk_id
    return f"{item.get('document_filename', 'unknown')}::{item.get('chunk_index', 'n/a')}"


def mark_excluded_evidence(evidence: list[dict], excluded_keys: list[str]) -> list[dict]:
    """Annotate evidence with reviewer exclusion flags."""

    excluded_lookup = {key.strip() for key in excluded_keys if key.strip()}
    marked = []
    for item in evidence:
        row = {**item}
        row["excluded_by_reviewer"] = evidence_item_key(row) in excluded_lookup
        marked.append(row)
    return marked


def active_evidence(evidence: list[dict]) -> list[dict]:
    """Return evidence remaining after reviewer exclusions."""

    return [item for item in evidence if not bool(item.get("excluded_by_reviewer", False))]


def optional_embedding_service() -> EmbeddingService | None:
    """Build embedding service when provider/model configuration is available."""

    try:
        model = get_embedding_model()
        logger.debug("Embedding service available provider=%s model=%s", model.provider, model.model)
        return EmbeddingService(model=model)
    except (AIConfigurationError, AIProviderError) as exc:
        logger.warning("Embedding service unavailable; semantic retrieval will be skipped error=%s", exc)
        return None


def build_retrieval_config(*, plan: RetrievalPlanResult, retry_count: int) -> dict[str, int | str | bool]:
    """Compute adaptive retrieval limits and strategy settings."""

    base_top_k = max(4, int(plan.preferred_top_k or settings.retrieval_top_k))
    if plan.needs_examples:
        base_top_k += 2
    if plan.needs_quantitative_support:
        base_top_k += 2
    if retry_count > 0:
        base_top_k += 4

    base_top_k = min(28, base_top_k)
    strategy = str(plan.retrieval_strategy).strip() or "hybrid"
    if strategy not in {"semantic", "keyword", "hybrid"}:
        strategy = "hybrid"

    semantic_top_k = base_top_k if strategy in {"semantic", "hybrid"} else 0
    keyword_top_k = base_top_k if strategy in {"keyword", "hybrid"} else 0
    if strategy == "hybrid":
        semantic_top_k = max(4, int(round(base_top_k * 0.7)))
        keyword_top_k = max(4, int(round(base_top_k * 0.7)))

    return {
        "strategy": strategy,
        "semantic_top_k": semantic_top_k,
        "keyword_top_k": keyword_top_k,
        "final_top_k": min(32, max(settings.final_evidence_k + 2, base_top_k)),
        "expand_context": bool(plan.should_expand_context or retry_count > 0),
        "context_window": 2 if retry_count > 0 else 1,
        "expand_seed_count": 3 if (plan.needs_examples or retry_count > 0) else 2,
    }


def apply_plan_scoring(
    *,
    chunks: list[dict],
    plan: RetrievalPlanResult,
    retry_count: int,
) -> list[dict]:
    """Apply plan-driven score boosts and dedupe results."""

    deduped: dict[str, dict] = {}
    priorities = [item.strip().lower() for item in plan.priority_sources if isinstance(item, str) and item.strip()]
    if plan.needs_prior_answers and "prior_rfp_answers" not in priorities:
        priorities.append("prior_rfp_answers")
    if plan.question_type and plan.question_type not in priorities:
        priorities.append(str(plan.question_type))

    for chunk in chunks:
        row = {**chunk}
        row_key = evidence_item_key(row)
        boost = 0.0
        if _chunk_matches_priority(row, priorities):
            boost += 0.22
        if plan.needs_examples and _chunk_has_example_signal(row):
            boost += 0.18
        if plan.needs_quantitative_support and _chunk_has_numeric_signal(row):
            boost += 0.18
        if plan.needs_regulatory_context and any(
            token in _chunk_search_blob(row)
            for token in ("regulatory", "regulator", "sfdr", "policy", "compliance")
        ):
            boost += 0.14
        if retry_count > 0 and "context_expand" in str(row.get("retrieval_method", "")):
            boost += 0.08

        base_score = float(row.get("score", 0.0) or 0.0)
        row["score"] = round(base_score + boost, 6)
        row["adaptive_score_boost"] = round(boost, 6)
        current = deduped.get(row_key)
        if current is None or float(row["score"]) > float(current.get("score", 0.0)):
            deduped[row_key] = row

    ranked = sorted(
        deduped.values(),
        key=lambda item: (
            -float(item.get("score", 0.0)),
            evidence_item_key(item),
        ),
    )
    return ranked


async def adaptive_retrieve(
    *,
    db: AsyncSession,
    query: str,
    plan: RetrievalPlanResult,
    retry_count: int,
    embedding_service: EmbeddingService | None,
) -> tuple[list[dict], dict]:
    """Retrieve evidence adaptively based on retrieval plan."""

    config = build_retrieval_config(plan=plan, retry_count=retry_count)
    semantic_results: list[dict] = []
    keyword_results: list[dict] = []
    context_results: list[dict] = []
    query_variants = [query, *[item for item in plan.sub_questions if isinstance(item, str) and item.strip()][:2]]
    keyword_queries = query_variants if config["strategy"] in {"keyword", "hybrid"} else []
    semantic_query = " ".join(query_variants) if config["strategy"] in {"semantic", "hybrid"} else ""

    retrieval = RetrievalService(db=db, embedding_service=embedding_service)

    if semantic_query:
        semantic_results = await semantic_search(retrieval, semantic_query, int(config["semantic_top_k"]))

    if keyword_queries:
        per_query_k = max(2, int(config["keyword_top_k"]) // max(1, len(keyword_queries)))
        for variant in keyword_queries:
            keyword_results.extend(await keyword_search(retrieval, variant, per_query_k))

    if not semantic_results and str(config["strategy"]) == "semantic":
        keyword_results.extend(
            await keyword_search(
                retrieval,
                query,
                max(4, int(config["semantic_top_k"])),
            )
        )
    if not keyword_results and str(config["strategy"]) == "keyword":
        semantic_results.extend(
            await semantic_search(
                retrieval,
                query,
                max(4, int(config["keyword_top_k"])),
            )
        )

    merged = apply_plan_scoring(
        chunks=[*semantic_results, *keyword_results],
        plan=plan,
        retry_count=retry_count,
    )

    if bool(config["expand_context"]) and merged:
        for chunk in merged[: int(config["expand_seed_count"])]:
            chunk_id = str(chunk.get("chunk_id", "")).strip()
            if chunk_id:
                context_results.extend(
                    await expand_chunk_context(
                        retrieval,
                        chunk_id=chunk_id,
                        window=int(config["context_window"]),
                    )
                )
        merged = apply_plan_scoring(
            chunks=[*merged, *context_results],
            plan=plan,
            retry_count=retry_count,
        )

    final_top_k = int(config["final_top_k"])
    retrieved = merged[:final_top_k]
    retrieval_debug = {
        "strategy": config["strategy"],
        "semantic_top_k": int(config["semantic_top_k"]),
        "keyword_top_k": int(config["keyword_top_k"]),
        "final_top_k": final_top_k,
        "expand_context": bool(config["expand_context"]),
        "context_window": int(config["context_window"]),
        "query_variants": query_variants,
        "priority_sources": list(plan.priority_sources),
        "semantic_results": len(semantic_results),
        "keyword_results": len(keyword_results),
        "context_results": len(context_results),
        "retrieved_chunk_ids": [str(item.get("chunk_id", "")) for item in retrieved],
        "retrieved_scores": [float(item.get("score", 0.0)) for item in retrieved],
        "retry_count": retry_count,
    }
    return retrieved, retrieval_debug


async def evaluate_evidence_with_model(
    *,
    question: str,
    plan: RetrievalPlanResult,
    evidence: list[dict],
) -> EvidenceEvaluationResult:
    """Evaluate evidence sufficiency with structured model fallback."""

    if not evidence:
        return EvidenceEvaluationResult(
            coverage="weak",
            confidence=0.1,
            selected_chunk_ids=[],
            rejected_chunk_ids=[],
            missing_information=["No relevant internal evidence was retrieved."],
            contradictions_found=[],
            evidence_summary="No supporting evidence available for drafting.",
            recommended_action="retrieve_more",
            notes_for_drafting=["Do not assert unsupported facts without retrieval coverage."],
            coverage_by_sub_question={item: "weak" for item in plan.sub_questions[:6]},
            num_supporting_chunks=0,
            num_example_chunks=0,
        )

    sub_questions = "\n".join(f"- {item}" for item in plan.sub_questions[:8]) or "- (none)"
    priority_sources = ", ".join(plan.priority_sources[:8]) or "unspecified"
    try:
        evaluator = get_structured_model(
            schema=EvidenceEvaluationResult,
            purpose="evidence_evaluation",
        )
        return await evaluator.ainvoke(
            system_prompt=render_prompt_template("evaluate_evidence", "system"),
            user_prompt=render_prompt_template(
                "evaluate_evidence",
                "user",
                question_type=plan.question_type,
                question=question,
                reasoning_summary=plan.reasoning_summary,
                sub_questions=sub_questions,
                priority_sources=priority_sources,
                needs_examples="yes" if plan.needs_examples else "no",
                needs_quantitative_support="yes" if plan.needs_quantitative_support else "no",
                needs_regulatory_context="yes" if plan.needs_regulatory_context else "no",
                evidence=format_evidence_blob(evidence),
            ),
            temperature=0,
        )
    except (AIConfigurationError, AIProviderError, RuntimeError, TimeoutError) as exc:
        logger.warning("Evidence evaluation fallback applied error=%s", exc)

    selected = evidence[: max(settings.final_evidence_k, 4)]
    selected_ids = [evidence_item_key(item) for item in selected]
    example_chunks = [item for item in selected if _chunk_has_example_signal(item)]
    quantitative_chunks = [item for item in selected if _chunk_has_numeric_signal(item)]
    missing: list[str] = []
    if plan.needs_examples and not example_chunks:
        missing.append("Concrete examples/case studies are limited in retrieved evidence.")
    if plan.needs_quantitative_support and not quantitative_chunks:
        missing.append("Quantitative support (metrics/KPIs/capacity) is limited in retrieved evidence.")
    if plan.needs_regulatory_context:
        has_regulatory = any(
            token in _chunk_search_blob(item)
            for item in selected
            for token in ("regulatory", "policy", "sfdr", "compliance")
        )
        if not has_regulatory:
            missing.append("Regulatory/policy context is limited in retrieved evidence.")

    if not missing and len(selected) >= settings.final_evidence_k:
        coverage: Literal["strong", "partial", "weak"] = "strong"
        confidence = 0.82
    elif missing and len(selected) <= 2:
        coverage = "weak"
        confidence = 0.36
    else:
        coverage = "partial"
        confidence = 0.6

    recommended_action: Literal["proceed", "proceed_with_caveats", "retrieve_more"]
    if coverage == "weak":
        recommended_action = "retrieve_more"
    elif coverage == "partial":
        recommended_action = "proceed_with_caveats"
    else:
        recommended_action = "proceed"

    return EvidenceEvaluationResult(
        coverage=coverage,
        confidence=confidence,
        selected_chunk_ids=selected_ids,
        rejected_chunk_ids=[evidence_item_key(item) for item in evidence[len(selected):]],
        missing_information=missing,
        contradictions_found=[],
        evidence_summary=(
            f"Fallback evidence evaluation retained {len(selected)} chunk(s) for drafting with {coverage} coverage."
        ),
        recommended_action=recommended_action,
        notes_for_drafting=(
            [
                "Use cautious language and acknowledge evidence limits where needed.",
                *[f"Gap to acknowledge: {item}" for item in missing],
            ]
            if missing
            else ["Evidence appears sufficient for a grounded draft."]
        ),
        coverage_by_sub_question={item: coverage for item in plan.sub_questions[:6]},
        num_supporting_chunks=len(selected),
        num_example_chunks=len(example_chunks),
    )


def normalize_evaluation_result(
    *,
    evaluation: EvidenceEvaluationResult,
    evidence: list[dict],
    plan: RetrievalPlanResult,
) -> EvidenceEvaluationResult:
    """Normalize evaluator-selected evidence ids against known candidates."""

    valid_ids = {evidence_item_key(item) for item in evidence}
    selected_ids = [item.strip() for item in evaluation.selected_chunk_ids if item.strip() in valid_ids]
    rejected_ids = [item.strip() for item in evaluation.rejected_chunk_ids if item.strip() in valid_ids]

    if not selected_ids and evidence:
        selected_ids = [evidence_item_key(item) for item in evidence[: max(settings.final_evidence_k, 4)]]
    rejected_ids = [item for item in rejected_ids if item not in selected_ids]

    num_example = 0
    num_supporting = 0
    for item in evidence:
        key = evidence_item_key(item)
        if key not in selected_ids:
            continue
        num_supporting += 1
        if _chunk_has_example_signal(item):
            num_example += 1

    coverage_by_sub_question = dict(evaluation.coverage_by_sub_question or {})
    if not coverage_by_sub_question and plan.sub_questions:
        coverage_by_sub_question = {item: evaluation.coverage for item in plan.sub_questions[:6]}

    return evaluation.model_copy(
        update={
            "selected_chunk_ids": selected_ids,
            "rejected_chunk_ids": rejected_ids,
            "num_supporting_chunks": num_supporting,
            "num_example_chunks": num_example,
            "coverage_by_sub_question": coverage_by_sub_question,
        }
    )


def partition_evidence(
    *,
    evidence: list[dict],
    selected_ids: list[str],
    rejected_ids: list[str],
) -> tuple[list[dict], list[dict], list[dict]]:
    """Split evidence into selected and rejected sets with annotations."""

    selected_lookup = {item.strip() for item in selected_ids if item.strip()}
    rejected_lookup = {item.strip() for item in rejected_ids if item.strip()}
    selected: list[dict] = []
    rejected: list[dict] = []
    annotated: list[dict] = []

    for item in evidence:
        row = {**item}
        key = evidence_item_key(row)
        is_selected = key in selected_lookup
        is_rejected = key in rejected_lookup and not is_selected
        row["selected_for_drafting"] = is_selected
        row["rejected_by_evaluator"] = is_rejected
        if is_selected:
            selected.append(row)
        elif is_rejected:
            rejected.append(row)
        annotated.append(row)

    if not selected and evidence:
        default_selected = {evidence_item_key(item) for item in evidence[: max(settings.final_evidence_k, 4)]}
        selected = []
        rejected = []
        annotated = []
        for item in evidence:
            row = {**item}
            key = evidence_item_key(row)
            is_selected = key in default_selected
            row["selected_for_drafting"] = is_selected
            row["rejected_by_evaluator"] = not is_selected
            if is_selected:
                selected.append(row)
            else:
                rejected.append(row)
            annotated.append(row)

    return selected, rejected, annotated


def augment_plan_for_retry(
    *,
    plan: RetrievalPlanResult,
    evaluation: EvidenceEvaluationResult,
) -> RetrievalPlanResult:
    """Expand retrieval plan after weak evidence evaluation."""

    priority_sources = [
        item.strip()
        for item in plan.priority_sources
        if isinstance(item, str) and item.strip()
    ]
    additions: list[str] = []
    if plan.needs_examples:
        additions.append("portfolio_examples")
    if plan.needs_quantitative_support:
        additions.append("performance_metrics")
    if plan.needs_regulatory_context:
        additions.append("regulatory_policy")
    if plan.needs_prior_answers:
        additions.append("prior_rfp_answers")
    if any("contradiction" in item.lower() for item in evaluation.notes_for_drafting):
        additions.append("governance_policy")
    for item in additions:
        if item not in priority_sources:
            priority_sources.append(item)

    updated_reasoning = (
        f"{plan.reasoning_summary.strip()} "
        f"Retry retrieval targeted missing info: {'; '.join(evaluation.missing_information[:3])}."
    ).strip()
    return plan.model_copy(
        update={
            "priority_sources": priority_sources,
            "should_expand_context": True,
            "preferred_top_k": min(24, max(plan.preferred_top_k + 4, settings.retrieval_top_k + 2)),
            "reasoning_summary": updated_reasoning,
            "confidence": max(0.0, min(1.0, float(plan.confidence) * 0.9)),
        }
    )


async def cross_reference_with_model(
    *,
    question: str,
    question_type: str,
    evidence: list[dict],
) -> EvidenceSynthesisResult | None:
    """Cross-reference evidence chunks for legacy synthesis node."""

    if not evidence:
        return None

    try:
        synthesizer = get_structured_model(
            schema=EvidenceSynthesisResult,
            purpose="cross_reference",
        )
        return await synthesizer.ainvoke(
            system_prompt=render_prompt_template("analyze_evidence", "system"),
            user_prompt=render_prompt_template(
                "analyze_evidence",
                "user",
                question=question,
                question_type=question_type,
                evidence=format_evidence_blob(evidence),
            ),
            temperature=0,
        )
    except (AIConfigurationError, AIProviderError, RuntimeError, TimeoutError) as exc:
        logger.warning("Evidence synthesis fallback applied error=%s", exc)
        return None


def curate_evidence(candidates: list[dict], final_k: int) -> list[dict]:
    """Deduplicate and rerank evidence by score and method diversity."""

    logger.debug("Curating evidence candidates=%d final_k=%d", len(candidates), final_k)
    deduped: dict[str, dict] = {}
    for item in candidates:
        chunk_id = item["chunk_id"]
        current = deduped.get(chunk_id)
        if current is None:
            deduped[chunk_id] = {**item, "methods": {item.get("retrieval_method", "unknown")}}
            continue

        current["score"] = max(float(current.get("score", 0.0)), float(item.get("score", 0.0)))
        current["methods"].add(item.get("retrieval_method", "unknown"))

    reranked = []
    for item in deduped.values():
        method_bonus = 0.15 if len(item["methods"]) > 1 else 0.0
        item["score"] = float(item.get("score", 0.0)) + method_bonus
        item["retrieval_method"] = "+".join(sorted(item["methods"]))
        item.pop("methods", None)
        reranked.append(item)

    reranked.sort(
        key=lambda evidence: (
            -float(evidence.get("score", 0.0)),
            evidence_item_key(evidence),
        )
    )
    results = reranked[:final_k]
    logger.debug("Evidence curation completed deduped=%d selected=%d", len(deduped), len(results))
    return results


def build_confidence_notes(curated_evidence: list[dict]) -> str:
    """Build confidence notes based on evidence quality heuristics."""

    if not curated_evidence:
        logger.debug("Confidence notes requested with no evidence")
        return "No evidence available."

    docs = {item["document_filename"] for item in curated_evidence}
    methods = {item.get("retrieval_method", "") for item in curated_evidence}
    avg_score = sum(float(item.get("score", 0.0)) for item in curated_evidence) / len(curated_evidence)

    notes = [
        f"Retrieved {len(curated_evidence)} supporting chunks from {len(docs)} source documents.",
        f"Average relevance score: {avg_score:.2f}.",
    ]

    if len(docs) < 2:
        notes.append("Coverage is concentrated in a small number of documents; consider additional validation.")
    if not any("semantic" in method for method in methods):
        notes.append("Semantic retrieval unavailable; response relies on keyword matching.")
    if avg_score < 0.2:
        notes.append("Overall evidence quality appears weak; treat response as low confidence.")

    result = " ".join(notes)
    logger.debug(
        "Confidence notes built evidence_count=%d doc_count=%d method_count=%d avg_score=%.2f",
        len(curated_evidence),
        len(docs),
        len(methods),
        avg_score,
    )
    return result
