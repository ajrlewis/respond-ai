"""Prompt templates for evidence synthesis, drafting, revision, and polish."""

ANALYZE_EVIDENCE_SYSTEM = """You are an evidence analyst for institutional RFP/DDQ drafting.

Your job is to evaluate and synthesize retrieved evidence chunks.
Use only the provided evidence chunks and do not add outside knowledge.
If information is missing, record it as missing information.
If two chunks conflict, record the contradiction explicitly."""


ANALYZE_EVIDENCE_USER = """Question type: {question_type}
Question: {question}

Evidence chunks:
{evidence}

Tasks:
1. Select chunk ids that should be used in drafting.
2. Reject chunk ids that are weak, redundant, or not directly relevant.
3. Identify contradictions and missing information.
4. Summarize what the evidence supports."""


DRAFT_ANSWER_SYSTEM = """You draft institutional-quality RFP/DDQ responses for a sustainable asset manager.

Requirements:
1. Use only grounded facts provided in the prompt.
2. Maintain a compliance-safe, non-promissory tone.
3. Include citations in the answer using [document#chunk-index].
4. Do not claim guaranteed performance, certainty, or outcomes."""


DRAFT_ANSWER_USER = """Tone: {tone}
Tone guidelines: {tone_guidelines}
Question type: {question_type}
Question: {question}

Evidence chunks:
{evidence}

Draft the formal response in plain text using only the evidence chunks."""


DRAFT_METADATA_SYSTEM = """You extract reviewer metadata from an RFP/DDQ draft answer.

Return structured metadata based only on the answer and evidence context."""


DRAFT_METADATA_USER = """Question: {question}
Question type: {question_type}

Draft answer:
{draft_answer}

Evidence chunks:
{evidence}

Extract:
1. citations used
2. coverage notes
3. confidence notes
4. missing information notes
5. compliance flags"""


REVISION_INTENT_SYSTEM = """You normalize reviewer feedback into structured revision intent."""


REVISION_INTENT_USER = """Question: {question}
Reviewer feedback:
{reviewer_feedback}

Return:
1. reviewer request summary
2. concrete requested changes
3. expected improvements."""


REVISE_ANSWER_SYSTEM = """You revise institutional RFP/DDQ responses while preserving factual grounding.

Revision constraints:
1. Update the prior draft based on reviewer feedback.
2. Do not remove existing citations unless they conflict with provided evidence.
3. If reviewer feedback conflicts with evidence, keep the answer evidence-grounded.
4. Keep language compliance-safe and avoid guaranteed-return wording."""


REVISE_ANSWER_USER = """Tone: {tone}
Tone guidelines: {tone_guidelines}
Question: {question}
Reviewer feedback: {reviewer_feedback}
Structured reviewer intent: {reviewer_intent}

Prior draft:
{prior_draft}

Evidence chunks:
{evidence}

Revise the prior draft with minimal necessary changes while preserving valid citations."""


POLISH_ANSWER_SYSTEM = """You polish institutional RFP/DDQ answers for investor audiences.

Rules:
1. Preserve all factual claims and citation references from the draft answer.
2. Keep edits minimal and focused on clarity, precision, and formal tone.
3. Do not introduce new facts, numbers, or citations that are not in the provided evidence.
4. Keep compliance-safe language and avoid promissory statements."""


POLISH_ANSWER_USER = """Tone: {tone}
Tone guidelines: {tone_guidelines}
Question type: {question_type}
Question: {question}

Current draft:
{draft_answer}

Evidence chunks:
{evidence}

Return a polished answer that improves readability while preserving citations."""


def analyze_evidence_system_prompt() -> str:
    return ANALYZE_EVIDENCE_SYSTEM


def analyze_evidence_user_prompt(*, question: str, question_type: str, evidence: str) -> str:
    return ANALYZE_EVIDENCE_USER.format(question=question, question_type=question_type, evidence=evidence)


def draft_answer_system_prompt() -> str:
    return DRAFT_ANSWER_SYSTEM


def draft_answer_user_prompt(
    *,
    tone: str,
    tone_guidelines: str,
    question_type: str,
    question: str,
    evidence: str,
) -> str:
    return DRAFT_ANSWER_USER.format(
        tone=tone,
        tone_guidelines=tone_guidelines,
        question_type=question_type,
        question=question,
        evidence=evidence,
    )


def draft_metadata_system_prompt() -> str:
    return DRAFT_METADATA_SYSTEM


def draft_metadata_user_prompt(*, question: str, question_type: str, draft_answer: str, evidence: str) -> str:
    return DRAFT_METADATA_USER.format(
        question=question,
        question_type=question_type,
        draft_answer=draft_answer,
        evidence=evidence,
    )


def revision_intent_system_prompt() -> str:
    return REVISION_INTENT_SYSTEM


def revision_intent_user_prompt(*, question: str, reviewer_feedback: str) -> str:
    return REVISION_INTENT_USER.format(question=question, reviewer_feedback=reviewer_feedback)


def revise_answer_system_prompt() -> str:
    return REVISE_ANSWER_SYSTEM


def revise_answer_user_prompt(
    *,
    tone: str,
    tone_guidelines: str,
    question: str,
    reviewer_feedback: str,
    reviewer_intent: str,
    prior_draft: str,
    evidence: str,
) -> str:
    return REVISE_ANSWER_USER.format(
        tone=tone,
        tone_guidelines=tone_guidelines,
        question=question,
        reviewer_feedback=reviewer_feedback,
        reviewer_intent=reviewer_intent,
        prior_draft=prior_draft,
        evidence=evidence,
    )


def polish_answer_system_prompt() -> str:
    return POLISH_ANSWER_SYSTEM


def polish_answer_user_prompt(
    *,
    tone: str,
    tone_guidelines: str,
    question_type: str,
    question: str,
    draft_answer: str,
    evidence: str,
) -> str:
    return POLISH_ANSWER_USER.format(
        tone=tone,
        tone_guidelines=tone_guidelines,
        question_type=question_type,
        question=question,
        draft_answer=draft_answer,
        evidence=evidence,
    )
