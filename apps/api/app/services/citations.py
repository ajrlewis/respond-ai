"""Citation normalization helpers for draft/revision text."""

from __future__ import annotations

import re

_BRACKETED_TOKEN_RE = re.compile(r"\[([^\[\]\n]{1,200})\]")
_HEXISH_TOKEN_RE = re.compile(r"[0-9a-fA-F-]{8,64}")


def _normalize_token(value: str) -> str:
    return value.strip().strip("`").strip().lower()


def _compact_hex(value: str) -> str:
    return re.sub(r"[^0-9a-f]", "", value.lower())


def _build_indexes(evidence: list[dict]) -> tuple[dict[str, int], dict[str, int]]:
    chunk_id_to_index: dict[str, int] = {}
    doc_ref_to_index: dict[str, int] = {}
    for idx, item in enumerate(evidence, start=1):
        chunk_id = _normalize_token(str(item.get("chunk_id", "")))
        if chunk_id:
            chunk_id_to_index[chunk_id] = idx

        filename = _normalize_token(str(item.get("document_filename", "")))
        chunk_index = str(item.get("chunk_index", "")).strip()
        if filename and chunk_index:
            doc_ref_to_index[f"{filename}#chunk-{chunk_index}"] = idx
    return chunk_id_to_index, doc_ref_to_index


def _resolve_citation_index(
    token: str,
    *,
    max_index: int,
    chunk_id_to_index: dict[str, int],
    doc_ref_to_index: dict[str, int],
) -> int | None:
    normalized = _normalize_token(token)
    if not normalized:
        return None

    if normalized.isdigit():
        value = int(normalized)
        return value if 1 <= value <= max_index else None

    normalized = re.sub(r"^(chunk[\s_-]*id)\s*[:=]\s*", "", normalized)

    direct_chunk = chunk_id_to_index.get(normalized)
    if direct_chunk is not None:
        return direct_chunk

    direct_doc = doc_ref_to_index.get(normalized)
    if direct_doc is not None:
        return direct_doc

    for doc_ref, idx in doc_ref_to_index.items():
        if doc_ref in normalized:
            return idx

    compact_token = _compact_hex(normalized)
    if len(compact_token) >= 8:
        matches = [
            idx
            for chunk_id, idx in chunk_id_to_index.items()
            if compact_token in _compact_hex(chunk_id)
        ]
        if len(set(matches)) == 1:
            return matches[0]

    if "-" in normalized:
        suffix = normalized.split("-", 1)[1].strip()
        if suffix:
            matches = [
                idx
                for chunk_id, idx in chunk_id_to_index.items()
                if chunk_id.endswith(suffix)
            ]
            if len(set(matches)) == 1:
                return matches[0]

    match = _HEXISH_TOKEN_RE.search(normalized)
    if match:
        compact_match = _compact_hex(match.group(0))
        if len(compact_match) >= 8:
            matches = [
                idx
                for chunk_id, idx in chunk_id_to_index.items()
                if compact_match in _compact_hex(chunk_id)
            ]
            if len(set(matches)) == 1:
                return matches[0]
    return None


def normalize_answer_citations(answer_text: str, evidence: list[dict]) -> str:
    """Normalize mixed citation formats into stable numeric citations like [1]."""

    if not answer_text or not evidence:
        return answer_text

    chunk_id_to_index, doc_ref_to_index = _build_indexes(evidence)
    max_index = len(evidence)

    def _replace(match: re.Match[str]) -> str:
        token = match.group(1)
        resolved = _resolve_citation_index(
            token,
            max_index=max_index,
            chunk_id_to_index=chunk_id_to_index,
            doc_ref_to_index=doc_ref_to_index,
        )
        if resolved is None:
            return match.group(0)
        return f"[{resolved}]"

    return _BRACKETED_TOKEN_RE.sub(_replace, answer_text)


def extract_answer_citations(answer_text: str) -> list[str]:
    """Extract ordered citation markers from draft text."""

    ordered: list[str] = []
    seen: set[str] = set()
    for token in _BRACKETED_TOKEN_RE.findall(answer_text):
        stripped = token.strip()
        if not stripped:
            continue
        if not (stripped.isdigit() or "#chunk-" in stripped.lower()):
            continue
        marker = f"[{stripped}]"
        if marker not in seen:
            ordered.append(marker)
            seen.add(marker)
    return ordered
