"""Seed markdown documents into Postgres + pgvector."""

from __future__ import annotations

from pathlib import Path
import sys

# Ensure `app.*` imports work whether the script is run from repo-local or container paths.
API_ROOT = Path(__file__).resolve().parents[1]
if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))

from app.core.database import SessionLocal
from app.db.migration_check import assert_schema_current_sync
from app.services.ingestion import IngestionService


def _resolve_docs_dir() -> Path:
    """Resolve the seed docs directory in local and container layouts."""

    script_path = Path(__file__).resolve()
    candidates = [script_path.parent]
    candidates.extend(list(script_path.parents))

    for base_path in candidates:
        docs_dir = base_path / "data" / "docs"
        if docs_dir.exists():
            return docs_dir

    raise FileNotFoundError(
        "Seed docs directory not found. Expected a `data/docs` directory in a parent path."
    )


def main() -> None:
    """Run seed ingestion from /data/docs."""

    docs_dir = _resolve_docs_dir()

    assert_schema_current_sync()

    with SessionLocal() as db:
        service = IngestionService(db)
        summary = service.ingest_markdown_directory(docs_dir)

    print(
        f"Ingestion complete: {summary.documents_processed} documents, "
        f"{summary.chunks_processed} chunks."
    )


if __name__ == "__main__":
    main()
