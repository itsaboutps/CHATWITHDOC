"""Synchronous ingestion pipeline (no Celery/Redis)."""

from app.core.config import get_settings
from app.core import runtime_state
from app.services import parsing, chunking, retrieval
from app.db.session import SessionLocal
from app.db import models
from app.services.storage import read_file
from app.services import memdb
from typing import Optional
import logging
logger = logging.getLogger(__name__)
import traceback

settings = get_settings()


async def _update_status(document_id: int, state: str):
    if settings.use_in_memory:
        memdb.update_document(document_id, status=state)
        logger.debug(f"doc {document_id} -> {state} (mem)")
        return
    try:
        async with SessionLocal() as session:  # type: ignore
            doc = await session.get(models.Document, document_id)
            if doc:
                doc.status = state
                await session.commit()
                logger.debug(f"doc {document_id} -> {state}")
    except Exception as e:  # pragma: no cover
        logger.warning(f"status update failed {document_id} {state}: {e}")


async def ingest_document(document_id: int, object_name: str, content_type: str, gemini_key: Optional[str] = None):  # noqa: D401
    if gemini_key:
        runtime_state.set_gemini_key(gemini_key)
    if settings.pipeline_debug:
        logger.info(f"[PIPELINE][INGEST][start] doc_id={document_id} file={object_name} content_type={content_type}")
    await _update_status(document_id, "downloading")
    try:
        data = read_file(object_name)
    except Exception as e:
        await _update_status(document_id, "error")
        logger.exception(f"Read failed doc {document_id}: {e}")
        if settings.pipeline_debug:
            logger.error(f"[PIPELINE][INGEST][error] doc_id={document_id} stage=read error={e}")
        return {"document_id": document_id, "error": f"read:{e}"}
    await _update_status(document_id, "parsing")
    pages = parsing.parse_file(content_type, data)
    if settings.pipeline_debug:
        logger.info(f"[PIPELINE][INGEST][parsed] doc_id={document_id} pages={len(pages)}")
    page_dicts = [{"page": p, "text": t} for p, t in pages]
    aggregated_text = "\n".join([p["text"] for p in page_dicts])
    await _update_status(document_id, "chunking")
    chunks = chunking.chunk_pages(page_dicts)
    if settings.pipeline_debug:
        logger.info(f"[PIPELINE][INGEST][chunked] doc_id={document_id} chunks={len(chunks)} chunk_size={settings.chunk_size} overlap={settings.chunk_overlap}")
    for ch in chunks:
        ch["document_id"] = document_id
    add_error: Optional[str] = None
    try:
        await _update_status(document_id, "embedding")
        if settings.pipeline_debug:
            logger.info(f"[PIPELINE][INGEST][embedding] doc_id={document_id} chunks={len(chunks)} model={settings.embedding_model}")
        await retrieval.add_documents(chunks)
        await _update_status(document_id, "indexing")
        if settings.pipeline_debug:
            logger.info(f"[PIPELINE][INGEST][indexed] doc_id={document_id} vector_store=qdrant_embedded={getattr(settings,'use_qdrant_embedded', False)}")
    except Exception as e:
        add_error = f"embedding_or_vector_error: {e}"
        logger.exception(f"Embedding/index error doc {document_id}: {e}")
        if settings.pipeline_debug:
            logger.error(f"[PIPELINE][INGEST][error] doc_id={document_id} stage=embedding_index error={e}")
    # Persist chunks and final status
    if settings.use_in_memory:
        if add_error:
            memdb.update_document(document_id, status="error", aggregated_text=(add_error + "\n" + aggregated_text)[:2_000_000])
            if settings.pipeline_debug:
                logger.info(f"[PIPELINE][INGEST][done] doc_id={document_id} status=error")
        else:
            for ch in chunks:
                # retrieval.add_documents already got them; just record
                pass
            memdb.update_document(document_id, status="ingested", aggregated_text=aggregated_text[:2_000_000])
            if settings.pipeline_debug:
                logger.info(f"[PIPELINE][INGEST][done] doc_id={document_id} status=ingested")
    else:
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
                if settings.pipeline_debug:
                    logger.info(f"[PIPELINE][INGEST][done] doc_id={document_id} status={doc.status}")
        except Exception as e:  # pragma: no cover
            logger.exception(f"Persist failed doc {document_id}: {e}")
            add_error = add_error or f"persist:{e}"
            await _update_status(document_id, "error")
            if settings.pipeline_debug:
                logger.error(f"[PIPELINE][INGEST][error] doc_id={document_id} stage=persist error={e}")
    return {"document_id": document_id, "chunks": len(chunks), "error": add_error}

