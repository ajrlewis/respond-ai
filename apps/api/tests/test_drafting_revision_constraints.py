from app.services.drafting import apply_revision_format_constraints


def test_single_paragraph_feedback_collapses_line_breaks() -> None:
    output = apply_revision_format_constraints(
        "First sentence.\n\nSecond sentence with citation [1].\nThird sentence.",
        "Turn this into a single paragraph.",
    )

    assert output == "First sentence. Second sentence with citation [1]. Third sentence."


def test_one_paragraph_variation_is_supported() -> None:
    output = apply_revision_format_constraints(
        "Line one.\nLine two.",
        "Please rewrite as one paragraph.",
    )

    assert output == "Line one. Line two."


def test_non_format_feedback_leaves_text_unchanged() -> None:
    original = "Paragraph one.\n\nParagraph two."
    output = apply_revision_format_constraints(
        original,
        "Tighten language and make it more formal.",
    )

    assert output == original
