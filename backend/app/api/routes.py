from fastapi import APIRouter, UploadFile, File, Depends, HTTPException, Header
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.db.session import get_db, engine, Base
from app.db import models
from app.schemas.base import UploadResponse, DocumentOut, AskRequest, Answer, HealthResponse
from app.core.config import get_settings
from app.core import runtime_state
from app.services.storage import store_file
from app.services import retrieval, rag
from app.services.retrieval import delete_document_vectors
from app.services.storage import _client as minio_client, settings as storage_settings
from app.core import runtime_state as rt_state
from app.core import runtime_state
from app.services import embeddings as emb_mod
from app.services import rag as rag_mod
import time
import io
from app.utils.logging import setup_logging

logger = setup_logging()

router = APIRouter()
settings = get_settings()


def require_api_key(x_api_key: str | None = Header(None)):
    if settings.api_key and x_api_key != settings.api_key:
        raise HTTPException(status_code=401, detail="Invalid or missing API key")


@router.on_event("startup")
async def startup():
    # Create tables
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    retrieval.ensure_collection()


@router.get("/health", response_model=HealthResponse)
async def health():
    components: dict = {}
    # Postgres
    try:
        async with engine.begin() as conn:
            await conn.execute(select(1))
        components["postgres"] = "ok"
    except Exception as e:  # pragma: no cover
        components["postgres"] = f"error: {e}"  # noqa: E501
    # Qdrant
    try:
        retrieval.ensure_collection()
        components["qdrant"] = "ok"
    except Exception as e:  # pragma: no cover
        components["qdrant"] = f"error: {e}"
    # MinIO
    try:
        from app.services.storage import _client, settings as s
        # list_objects in minio-py doesn't accept max_keys param; fetch one safely
        iterator = _client.list_objects(s.minio_bucket, recursive=False)
        # Advance at most one item to validate access without loading everything
        try:
            next(iterator, None)
        except StopIteration:
            pass
        components["minio"] = "ok"
    except Exception as e:  # pragma: no cover
        components["minio"] = f"error: {e}"
    # Redis removed in simplified mode
    components["redis"] = "removed"
    overall = "ok" if all(v in ("ok", "removed") for v in components.values()) else "degraded"
    return {"status": overall, "components": components}


@router.post("/gemini/key")
async def set_gemini_key(payload: dict):  # payload expects {"key": "..."}
    key = payload.get("key", "").strip()
    if not key:
        raise HTTPException(status_code=400, detail="Key required")
    runtime_state.set_gemini_key(key)
    return {"status": "ok", "message": "Gemini key set (ephemeral)", "active": True}


@router.delete("/gemini/key")
async def clear_gemini_key():
    runtime_state.clear_gemini_key()
    return {"status": "ok", "message": "Gemini key cleared", "active": False}


@router.get("/gemini/key")
async def gemini_key_status():
    return {"active": runtime_state.has_gemini_key()}


@router.get("/gemini/models")
async def gemini_model_diagnostics():
    """Return the configured models and candidate fallbacks we will try for generation."""
    settings_models = {
        "embedding_model_config": settings.embedding_model,
        "generation_model_config": settings.generation_model,
    }
    gen = settings.generation_model
    candidates = [gen]
    if not gen.startswith("models/"):
        candidates.append(f"models/{gen}")
    if not gen.endswith("-latest"):
        candidates.append(gen + "-latest")
    return {"configured": settings_models, "generation_candidates": candidates}


@router.post("/gemini/models/config")
async def gemini_model_config_update(payload: dict):
    """Update generation/embedding model names at runtime (no restart required).
    Payload accepts keys: generation_model, embedding_model.
    Returns the new configuration and candidate list.
    """
    gen = payload.get("generation_model")
    emb = payload.get("embedding_model")
    changed = {}
    if gen:
        settings.generation_model = gen.strip()
        changed["generation_model"] = settings.generation_model
    if emb:
        settings.embedding_model = emb.strip()
        changed["embedding_model"] = settings.embedding_model
    # Reuse diagnostics build
    gen_model = settings.generation_model
    candidates = [gen_model]
    if not gen_model.startswith("models/"):
        candidates.append(f"models/{gen_model}")
    if not gen_model.endswith("-latest"):
        candidates.append(gen_model + "-latest")
    return {"updated": changed, "current": {"generation_model": settings.generation_model, "embedding_model": settings.embedding_model}, "generation_candidates": candidates}


@router.get("/gemini/test/embed")
async def gemini_test_embed(sample: str = "Hello world test embedding"):
    try:
        vecs = await emb_mod.embed_texts([sample])
        mode = getattr(vecs, "_embed_mode", "unknown")
        return {"ok": True, "dimensions": len(vecs[0]) if vecs else 0, "mode": mode}
    except Exception as e:
        return {"ok": False, "error": str(e)}


@router.get("/gemini/test/generate")
async def gemini_test_generate(q: str = "What is a test?", ctx: str = "A test checks functionality."):
    try:
        # mimic context chunk structure minimally
        result = await rag_mod.generate_answer(q, [{"page": 0, "text": ctx}])
        return {"ok": True, **result}
    except Exception as e:
        return {"ok": False, "error": str(e)}


@router.get("/diagnostics")
async def diagnostics(db: AsyncSession = Depends(get_db)):
    # Aggregate document ingestion states
    res = await db.execute(select(models.Document.status, models.Document.id))
    rows = res.fetchall()
    total = len(rows)
    by_status: dict[str,int] = {}
    for st, _id in rows:  # type: ignore
        by_status[st] = by_status.get(st, 0) + 1
    gem = runtime_state.gemini_status()
    return {
        "documents_total": total,
        "documents_by_status": by_status,
        "any_processing": any(st not in ("ingested", "error") for st,_ in rows),
        "gemini": gem,
    }



@router.post("/upload", response_model=UploadResponse)
async def upload(file: UploadFile = File(...), db: AsyncSession = Depends(get_db)):
    if not file.content_type:
        raise HTTPException(status_code=400, detail="Unknown content type")
    content = await file.read()
    if len(content) > 50 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="File too large")
    buffer = io.BytesIO(content)
    object_name = store_file(buffer, file.filename)
    doc = models.Document(
        filename=file.filename,
        content_type=file.content_type,
        original_path=object_name,
        status="uploaded",
    )
    db.add(doc)
    await db.commit()
    await db.refresh(doc)
    logger.info(f"Stored file {file.filename} as {object_name} (doc_id={doc.id})")
    # Always inline ingest now (Celery removed)
    try:
        from app.services.tasks import ingest_document
        current_key = runtime_state.get_gemini_key("") or None
        await ingest_document(doc.id, object_name, file.content_type, current_key)
        await db.refresh(doc)
        return UploadResponse(document_id=doc.id, task_id="inline", status=doc.status)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ingestion failed: {e}")


@router.get("/documents", response_model=list[DocumentOut])
async def list_documents(db: AsyncSession = Depends(get_db)):
    res = await db.execute(select(models.Document).order_by(models.Document.created_at.desc()))
    return res.scalars().all()


@router.post("/ask", response_model=Answer)
async def ask(req: AskRequest):
    start = time.time()
    try:
        results = await retrieval.search(req.question, settings.top_k, document_ids=req.document_ids)
    except Exception as e:  # broad catch to prevent 500 surface
        logger.error(f"Retrieval failure: {e}")
        return {
            "answer": "Retrieval failed. Please retry shortly.",
            "answer_type": "out_of_scope",
            "sources": [],
            "latency_ms": int((time.time() - start) * 1000),
            "retrieved": 0,
            "generation_mode": "not_started",
            "embed_mode": None,
            "fallback_reason": "retrieval_error",
        }
    filtered = [r for r in results if r.get("hybrid_score", r.get("score", 0)) >= settings.similarity_threshold]
    if not filtered:
        return {
            "answer": "I'm sorry, that appears to be outside the scope of the provided documents or they are still ingesting.",
            "answer_type": "out_of_scope",
            "sources": [],
            "latency_ms": int((time.time() - start) * 1000),
            "retrieved": 0,
            "generation_mode": "none",
            "embed_mode": filtered[0].get("_embed_mode") if filtered else None,
            "fallback_reason": "no_results",
        }
    answer = await rag.generate_answer(req.question, filtered)
    # Determine embedding mode from vector list attribute if present on retrieval internals
    # retrieval.add_documents stores vectors but we can infer from generation context: attach from answer if missing
    answer.setdefault("embed_mode", filtered[0].get("_embed_mode") if filtered and filtered[0].get("_embed_mode") else None)
    answer.setdefault("generation_mode", "unknown")
    answer.setdefault("fallback_reason", None)
    answer["source_snippets"] = [c.get("text", "")[:220] for c in filtered]
    # Include document ids used so UI can highlight
    answer["document_ids_used"] = list({c.get("document_id") for c in filtered if c.get("document_id") is not None})
    answer["latency_ms"] = int((time.time() - start) * 1000)
    answer.setdefault("retrieved", len(filtered))
    return answer


@router.get("/summarize/{document_id}", response_model=Answer)
async def summarize(document_id: int, db: AsyncSession = Depends(get_db)):
    doc = await db.get(models.Document, document_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    if not doc.aggregated_text:
        raise HTTPException(status_code=400, detail="Document not ingested yet")
    result = await rag.summarize(doc.aggregated_text)
    return result


@router.delete("/documents/{document_id}")
async def delete_document(document_id: int, db: AsyncSession = Depends(get_db)):
    doc = await db.get(models.Document, document_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Not found")
    # Delete vectors first
    delete_document_vectors(document_id)
    # Delete object in MinIO
    try:
        if doc.original_path:
            minio_client.remove_object(storage_settings.minio_bucket, doc.original_path)
    except Exception:  # pragma: no cover
        logger.warning("Failed removing object from MinIO")
    await db.delete(doc)
    await db.commit()
    return {"status": "deleted", "document_id": document_id}


@router.get("/tasks/{task_id}")
async def task_status(task_id: str):
    """Legacy endpoint kept for frontend backward compatibility.
    Since ingestion is now inline (no Celery), we just echo that the task is done.
    Frontend should stop polling this and rely on /documents list instead."""
    if task_id == "inline":
        return {"task_id": task_id, "status": "done", "result": None}
    return {"task_id": task_id, "status": "unknown", "result": None}


@router.post("/admin/reset")
async def admin_reset(token: str):
    if settings.admin_reset_token and token != settings.admin_reset_token:
        raise HTTPException(status_code=403, detail="Forbidden")
    # Clear runtime key
    rt_state.clear_gemini_key()
    # Drop DB tables & recreate
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    # Qdrant collection wipe
    try:
        retrieval.client.delete_collection(settings.qdrant_collection)
    except Exception:
        pass
    # MinIO bucket wipe (objects only)
    try:
        for obj in minio_client.list_objects(storage_settings.minio_bucket, recursive=True):
            try:
                minio_client.remove_object(storage_settings.minio_bucket, obj.object_name)
            except Exception:  # noqa: E722
                pass
    except Exception:
        pass
    # Redis purge skipped (redis removed)
    # In-memory retrieval indexes
    try:
        from app.services import retrieval as rmod
        rmod._MEM_INDEX.clear()  # type: ignore
        rmod._LEX_CHUNKS.clear()  # type: ignore
        rmod._LEX_TERM_FREQS.clear()  # type: ignore
        rmod._LEX_DOC_FREQ.clear()  # type: ignore
        rmod._LEX_TOTAL = 0  # type: ignore
    except Exception:
        pass
    return {"status": "reset", "message": "All stores cleared"}
