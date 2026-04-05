"""Markdown parsing and recursive chunking utilities."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class ChunkCandidate:
    """Chunk payload before persistence."""

    chunk_index: int
    text: str
    metadata: dict


@dataclass(slots=True)
class Section:
    """Heading-scoped markdown section."""

    heading_path: list[str]
    body: str


def split_markdown_sections(markdown_text: str) -> list[Section]:
    """Split markdown into heading-aware sections."""

    lines = markdown_text.splitlines()
    heading_stack: list[tuple[int, str]] = []
    section_lines: list[str] = []
    sections: list[Section] = []

    def flush_section() -> None:
        if not section_lines:
            return
        content = "\n".join(section_lines).strip()
        if content:
            sections.append(Section(heading_path=[h[1] for h in heading_stack], body=content))
        section_lines.clear()

    for line in lines:
        if line.startswith("#"):
            flush_section()
            level = len(line) - len(line.lstrip("#"))
            title = line[level:].strip()
            while heading_stack and heading_stack[-1][0] >= level:
                heading_stack.pop()
            heading_stack.append((level, title))
            continue
        section_lines.append(line)

    flush_section()
    if not sections:
        return [Section(heading_path=["Document"], body=markdown_text.strip())]
    return sections


def recursive_chunk_text(text: str, max_chars: int = 900, overlap_chars: int = 120) -> list[str]:
    """Recursively split text into semantically coherent chunks."""

    clean = text.strip()
    if not clean:
        return []
    if len(clean) <= max_chars:
        return [clean]

    delimiters = ["\n\n", "\n", ". ", " "]
    chunks: list[str] = [clean]

    for delimiter in delimiters:
        next_chunks: list[str] = []
        split_any = False
        for chunk in chunks:
            if len(chunk) <= max_chars:
                next_chunks.append(chunk)
                continue

            parts = chunk.split(delimiter)
            if len(parts) == 1:
                next_chunks.append(chunk)
                continue

            split_any = True
            buffer = ""
            for part in parts:
                candidate = f"{buffer}{delimiter if buffer else ''}{part}".strip()
                if len(candidate) <= max_chars:
                    buffer = candidate
                    continue

                if buffer:
                    next_chunks.append(buffer)
                buffer = part.strip()

            if buffer:
                next_chunks.append(buffer)

        chunks = next_chunks
        if split_any and all(len(chunk) <= max_chars for chunk in chunks):
            break

    final_chunks: list[str] = []
    for chunk in chunks:
        if len(chunk) <= max_chars:
            final_chunks.append(chunk.strip())
            continue

        start = 0
        while start < len(chunk):
            end = min(start + max_chars, len(chunk))
            final_chunks.append(chunk[start:end].strip())
            if end == len(chunk):
                break
            start = max(0, end - overlap_chars)

    return [chunk for chunk in final_chunks if chunk]


def chunk_markdown(markdown_text: str, source_filename: str) -> list[ChunkCandidate]:
    """Create heading-aware chunks with metadata."""

    sections = split_markdown_sections(markdown_text)
    candidates: list[ChunkCandidate] = []
    chunk_index = 0

    for section in sections:
        section_path = " > ".join(section.heading_path) if section.heading_path else "Document"
        chunk_texts = recursive_chunk_text(section.body)
        for section_chunk_idx, chunk in enumerate(chunk_texts):
            metadata = {
                "source_filename": source_filename,
                "section_path": section_path,
                "section_chunk_index": section_chunk_idx,
            }
            candidates.append(ChunkCandidate(chunk_index=chunk_index, text=chunk, metadata=metadata))
            chunk_index += 1

    return candidates
