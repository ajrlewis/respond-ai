from app.ai.usage import normalize_usage_payload


def test_normalize_usage_payload_handles_openai_shape() -> None:
    usage = normalize_usage_payload(
        {
            "prompt_tokens": 123,
            "completion_tokens": 45,
            "total_tokens": 168,
        }
    )

    assert usage.input_tokens == 123
    assert usage.output_tokens == 45
    assert usage.total_tokens == 168
    assert usage.normalized_input_tokens == 123
    assert usage.normalized_output_tokens == 45


def test_normalize_usage_payload_handles_google_shape() -> None:
    usage = normalize_usage_payload(
        {
            "prompt_token_count": 101,
            "candidates_token_count": 22,
            "total_token_count": 123,
        }
    )

    assert usage.input_tokens == 101
    assert usage.output_tokens == 22
    assert usage.total_tokens == 123


def test_normalize_usage_payload_uses_fallbacks_when_missing() -> None:
    usage = normalize_usage_payload(
        {},
        input_fallback_tokens=80,
        output_fallback_tokens=20,
    )

    assert usage.input_tokens == 0
    assert usage.output_tokens == 0
    assert usage.total_tokens == 100
    assert usage.normalized_input_tokens == 80
    assert usage.normalized_output_tokens == 20
