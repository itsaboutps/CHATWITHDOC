"""Simplified ingestion (synchronous inline) removing Celery/Redis.
The upload route now awaits ingest_document_async directly.
"""

from app.core.config import get_settings
from app.core import runtime_state
from app.services import parsing, chunking, retrieval
from app.db.session import SessionLocal
from app.db import models
from app.services.storage import _client, settings as ssettings
from loguru import logger
import traceback

settings = get_settings()


async def _update_status(document_id: int, state: str):
    try:
        async with SessionLocal() as session:  # type: ignore
            doc = await session.get(models.Document, document_id)
            if doc:
                doc.status = state
                await session.commit()
                logger.debug(f"doc {document_id} -> {state}")
    except Exception as e:  # pragma: no cover
        logger.warning(f"status update failed {document_id} {state}: {e}")


async def ingest_document(document_id: int, object_name: str, content_type: str, gemini_key: str | None = None):  # noqa: D401
    if gemini_key:
        runtime_state.set_gemini_key(gemini_key)
    await _update_status(document_id, "downloading")
    try:
        response = _client.get_object(ssettings.minio_bucket, object_name)
        data = response.read()
    except Exception as e:
        await _update_status(document_id, "error")
        logger.exception(f"Download failed doc {document_id}: {e}")
        return {"document_id": document_id, "error": f"download:{e}"}
    await _update_status(document_id, "parsing")
    pages = parsing.parse_file(content_type, data)
    page_dicts = [{"page": p, "text": t} for p, t in pages]
    aggregated_text = "\n".join([p["text"] for p in page_dicts])
    await _update_status(document_id, "chunking")
    chunks = chunking.chunk_pages(page_dicts)
    for ch in chunks:
        ch["document_id"] = document_id
    add_error: str | None = None
    try:
        await _update_status(document_id, "embedding")
        await retrieval.add_documents(chunks)
        await _update_status(document_id, "indexing")
    except Exception as e:
        add_error = f"embedding_or_vector_error: {e}"
        logger.exception(f"Embedding/index error doc {document_id}: {e}")
    # Persist chunks and final status
    try:
        async with SessionLocal() as session:  # type: ignore
            doc = await session.get(models.Document, document_id)
            if not doc:
                return {"document_id": document_id, "error": "missing_doc"}
            if add_error:
                doc.status = "error"
                doc.aggregated_text = (add_error + "\n" + aggregated_text)[:2_000_000]
            else:
                for idx, ch in enumerate(chunks):
                    c = models.Chunk(document_id=document_id, page=ch.get("page", 0), position=idx, text=ch["text"])  # type: ignore
                    session.add(c)
                doc.status = "ingested"
                doc.aggregated_text = aggregated_text[:2_000_000]
            await session.commit()
    except Exception as e:  # pragma: no cover
        logger.exception(f"Persist failed doc {document_id}: {e}")
        add_error = add_error or f"persist:{e}"
        await _update_status(document_id, "error")
    return {"document_id": document_id, "chunks": len(chunks), "error": add_error}

