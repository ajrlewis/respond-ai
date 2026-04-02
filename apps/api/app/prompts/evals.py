"""Prompt templates for optional LLM-judge evaluations."""

EVAL_JUDGE_SYSTEM = """You are an institutional QA evaluator for RFP/DDQ responses.

Score the answer for factual grounding, completeness, and compliance-safe language.
Use only provided session metrics and final answer content."""


EVAL_JUDGE_USER = """Session id: {session_id}
Approved: {approved}
Question type: {question_type}
Final answer:
{final_answer}

Metrics:
- Retrieved chunks: {num_retrieved_chunks}
- Cited chunks: {num_cited_chunks}
- Revision rounds: {num_revision_rounds}
- Total tokens: {total_tokens}
- Estimated cost USD: {estimated_cost_usd}

Return a normalized quality judgment."""


def eval_judge_system_prompt() -> str:
    return EVAL_JUDGE_SYSTEM


def eval_judge_user_prompt(
    *,
    session_id: str,
    approved: bool,
    question_type: str,
    final_answer: str,
    num_retrieved_chunks: int,
    num_cited_chunks: int,
    num_revision_rounds: int,
    total_tokens: int,
    estimated_cost_usd: float | None,
) -> str:
    return EVAL_JUDGE_USER.format(
        session_id=session_id,
        approved=approved,
        question_type=question_type,
        final_answer=final_answer,
        num_retrieved_chunks=num_retrieved_chunks,
        num_cited_chunks=num_cited_chunks,
        num_revision_rounds=num_revision_rounds,
        total_tokens=total_tokens,
        estimated_cost_usd=estimated_cost_usd,
    )
