"""Seed markdown documents into Postgres + pgvector."""

from __future__ import annotations

from pathlib import Path
import sys

# Ensure `app.*` imports work whether the script is run from repo-local or container paths.
API_ROOT = Path(__file__).resolve().parents[1]
if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))

from app.core.database import SessionLocal
from app.core.client_config import resolve_config_path
from app.db.migration_check import assert_schema_current_sync
from app.services.ingestion import IngestionService


def _resolve_docs_dir() -> Path:
    """Resolve markdown seed directory under repo-level `config/documents/data`."""

    docs_dir = resolve_config_path("documents/data")
    if docs_dir.exists() and docs_dir.is_dir():
        return docs_dir
    raise FileNotFoundError(
        "Seed docs directory not found. Expected `config/documents/data`."
    )


def main() -> None:
    """Run seed ingestion from `config/documents/data`."""

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
