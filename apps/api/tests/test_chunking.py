from app.services.chunking import chunk_markdown, recursive_chunk_text, split_markdown_sections


def test_split_markdown_sections_preserves_heading_path() -> None:
    markdown = """# Top\nIntro\n## Nested\nNested body"""

    sections = split_markdown_sections(markdown)

    assert len(sections) == 2
    assert sections[0].heading_path == ["Top"]
    assert sections[1].heading_path == ["Top", "Nested"]


def test_recursive_chunk_text_breaks_long_text() -> None:
    text = "Paragraph. " * 500

    chunks = recursive_chunk_text(text, max_chars=200)

    assert len(chunks) > 1
    assert all(len(chunk) <= 200 for chunk in chunks)


def test_chunk_markdown_attaches_metadata() -> None:
    markdown = """# Title\n## Section\nA short paragraph for chunking."""

    chunks = chunk_markdown(markdown, "demo.md")

    assert chunks
    assert chunks[0].metadata["source_filename"] == "demo.md"
    assert "section_path" in chunks[0].metadata
