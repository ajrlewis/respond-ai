"""System-wide prompt constants and tone guidance."""

TONE_GUIDELINES: dict[str, str] = {
    "formal": (
        "Use precise institutional language, avoid first-person pronouns, and prioritize "
        "compliance-safe phrasing over persuasive claims."
    ),
    "detailed": (
        "Provide full factual context with explicit caveats, include concise definitions for "
        "technical terms, and preserve an analytical tone."
    ),
    "concise": "Keep the response under 150 words while preserving all material facts and citations.",
    "marketing": (
        "Emphasize competitive strengths with active verbs, but avoid unsupported superlatives "
        "or any promise of outcomes."
    ),
}


def get_tone_guidelines(tone: str) -> str:
    """Return tone guidance with a safe default."""

    return TONE_GUIDELINES.get(tone, TONE_GUIDELINES["formal"])
