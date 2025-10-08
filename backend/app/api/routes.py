from fastapi import APIRouter, UploadFile, File, Depends, HTTPException, Header
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.db.session import get_db, engine, Base
from app.db import models
from app.services import memdb
from app.schemas.base import UploadResponse, DocumentOut, AskRequest, Answer, HealthResponse
from app.core.config import get_settings
from app.services.storage import store_file, delete_file
from app.services import retrieval, rag
from app.services import debug_buffer
import httpx
from app.services.retrieval import delete_document_vectors
from app.core import runtime_state as rt_state
from app.services import embeddings as emb_mod
from app.services import rag as rag_mod
import time, io
from app.utils.logging import setup_logging

logger = setup_logging()

router = APIRouter()
settings = get_settings()


def require_api_key(x_api_key: Optional[str] = Header(None)):
    if settings.api_key and x_api_key != settings.api_key:
        raise HTTPException(status_code=401, detail="Invalid or missing API key")


@router.on_event("startup")
async def startup():
    if not settings.use_in_memory:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
    retrieval.ensure_collection()


@router.get("/health", response_model=HealthResponse)
async def health():
    components: dict = {}
    if settings.use_in_memory:
        components["db"] = "in_memory"
    else:
        try:
            async with engine.begin() as conn:
                await conn.execute(select(1))
            components["db"] = "ok"
        except Exception as e:  # pragma: no cover
            components["db"] = f"error: {e}"
    if getattr(settings, 'use_qdrant_embedded', False):
        try:
            retrieval.ensure_collection()
            components["qdrant_embedded"] = "ok"
        except Exception as e:
            components["qdrant_embedded"] = f"error: {e}"
    overall = "ok" if all(v in ("ok", "in_memory") for v in components.values()) else "degraded"
    return {"status": overall, "components": components}


@router.post("/gemini/key")
async def set_gemini_key(payload: dict):  # payload expects {"key": "..."}
    key = payload.get("key", "").strip()
    if not key:
        raise HTTPException(status_code=400, detail="Key required")
    rt_state.set_gemini_key(key)
    return {"status": "ok", "message": "Gemini key set (ephemeral)", "active": True}


@router.delete("/gemini/key")
async def clear_gemini_key():
    rt_state.clear_gemini_key()
    return {"status": "ok", "message": "Gemini key cleared", "active": False}


@router.get("/gemini/key")
async def gemini_key_status():
    return {"active": rt_state.has_gemini_key()}


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


@router.get("/gemini/models/available")
async def gemini_models_available():
    """Fetch the list of models the current API key can see and classify embedding vs generation.
    Provides availability flags for the configured embedding & generation models.
    """
    runtime_key = rt_state.get_gemini_key(settings.gemini_api_key)
    if not runtime_key:
        raise HTTPException(status_code=400, detail="No Gemini API key set (use POST /gemini/key)")
    url = f"https://generativelanguage.googleapis.com/v1beta/models?key={runtime_key}"
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.get(url)
            r.raise_for_status()
            data = r.json()
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Model list fetch failed: {e}")
    models = data.get('models', [])
    names = [m.get('name','') for m in models if m.get('name')]
    # Simple classification heuristics
    embedding = [n for n in names if 'embedding' in n]
    generation = [n for n in names if 'gemini' in n and 'embedding' not in n]
    other = sorted(set(names) - set(embedding) - set(generation))
    # Normalize configured names to both raw & with models/ prefix
    cfg_gen = settings.generation_model
    cfg_emb = settings.embedding_model
    def is_available(cfg: str):
        if cfg in names:
            return True
        pref = cfg if cfg.startswith('models/') else f'models/{cfg}'
        alt = cfg.split('/')[-1]
        variants = {cfg, pref, alt, pref + ('-latest' if not pref.endswith('-latest') else '')}
        return any(v in names for v in variants)
    availability = {
        'generation_model': { 'configured': cfg_gen, 'available': is_available(cfg_gen) },
        'embedding_model': { 'configured': cfg_emb, 'available': is_available(cfg_emb) },
    }
    return {
        'runtime_key_active': True,
        'total_models': len(names),
        'generation_models': generation,
        'embedding_models': embedding,
        'other_models': other,
        'availability': availability,
    }


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
    if settings.use_in_memory:
        docs = memdb.list_documents()
        total = len(docs)
        by_status = {}
        for d in docs:
            st = d.get("status", "unknown")
            by_status[st] = by_status.get(st, 0) + 1
        any_processing = any(st not in ("ingested", "error") for st in by_status.keys())
    else:
        res = await db.execute(select(models.Document.status, models.Document.id))
        rows = res.fetchall()
        total = len(rows)
        by_status = {}
        for st, _id in rows:  # type: ignore
            by_status[st] = by_status.get(st, 0) + 1
        any_processing = any(st not in ("ingested", "error") for st,_ in rows)
    gem = rt_state.gemini_status()
    return {
        "documents_total": total,
        "documents_by_status": by_status,
        "any_processing": any_processing,
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
    if settings.use_in_memory:
        doc_dict = memdb.create_document(file.filename, file.content_type, object_name)
        document_id = doc_dict["id"]
    else:
        doc = models.Document(
            filename=file.filename,
            content_type=file.content_type,
            original_path=object_name,
            status="uploaded",
        )
        db.add(doc)
        await db.commit()
        await db.refresh(doc)
        document_id = doc.id
        logger.info(f"Stored file {file.filename} as {object_name} (doc_id={doc.id})")
    # Inline ingestion
    try:
        from app.services.tasks import ingest_document
        current_key = rt_state.get_gemini_key("") or None
        await ingest_document(document_id, object_name, file.content_type, current_key)
        if settings.use_in_memory:
            status_val = memdb.get_document(document_id)["status"]  # type: ignore
        else:
            await db.refresh(doc)
            status_val = doc.status
        return UploadResponse(document_id=document_id, task_id="inline", status=status_val)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ingestion failed: {e}")


@router.get("/documents", response_model=list[DocumentOut])
async def list_documents(db: AsyncSession = Depends(get_db)):
    if settings.use_in_memory:
        return [DocumentOut(id=d["id"], filename=d["filename"], status=d["status"]) for d in memdb.list_documents()]  # type: ignore
    res = await db.execute(select(models.Document).order_by(models.Document.created_at.desc()))
    return res.scalars().all()


@router.post("/ask", response_model=Answer)
async def ask(req: AskRequest):
    start = time.time()
    if settings.pipeline_debug:
        logger.info(f"[PIPELINE][ASK][start] question='{req.question[:120]}' docs_filter={req.document_ids}")
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
    # If threshold filtered everything but we had candidates, take the top-1 so user gets best-effort answer.
    if not filtered and results:
        filtered = results[:1]
    # Adaptive broad-question enrichment: if user asks a summarization/broad intent question and we have too few chunks, broaden context.
    broad_q = req.question.lower().strip().rstrip('?')
    BROAD_PATTERNS = [
        'what is this document about',
        'what is the document about',
        'summarize this document',
        'give me a summary',
        'overall summary',
        'summary of the document'
    ]
    if len(filtered) < 2 and results and any(p in broad_q for p in BROAD_PATTERNS):
        # Take top up to 3 distinct chunks even if below threshold (context amplification)
        enriched = results[: min(3, len(results))]
        if settings.pipeline_debug:
            logger.info(f"[PIPELINE][ASK][adaptive_enrich] broad_intent=True original_filtered={len(filtered)} enriched_to={len(enriched)}")
        filtered = enriched
    if settings.pipeline_debug:
        logger.info(f"[PIPELINE][ASK][retrieved] total_candidates={len(results)} used={len(filtered)} threshold={settings.similarity_threshold}")
        # Log acceptance / rejection rationale for each candidate (top candidates list only)
        for idx, cand in enumerate(results):
            if idx >= settings.top_k:
                break
            hs = cand.get('hybrid_score', cand.get('score',0))
            accepted = hs >= settings.similarity_threshold or cand in filtered
            reason = 'below_threshold' if hs < settings.similarity_threshold else 'meets_threshold'
            if accepted and cand in results[:1] and len(filtered)==1 and hs < settings.similarity_threshold:
                reason = 'fallback_top1'
            snippet = (cand.get('text') or '').replace('\n',' ')[:160]
            logger.info(f"[PIPELINE][ASK][candidate] rank={idx+1} hybrid={hs:.4f} mode={cand.get('mode')} accepted={accepted} reason={reason} doc={cand.get('document_id')} page={cand.get('page')} text='{snippet}'")
    if not filtered:
        return {
            "answer": "I'm sorry, that appears to be outside the scope of the provided documents or they are still ingesting.",
            "answer_type": "out_of_scope",
            "sources": [],
            "latency_ms": int((time.time() - start) * 1000),
            "retrieved": 0,
            "generation_mode": "none",
            "embed_mode": None,
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
    # Debug buffer capture
    try:
        debug_buffer.record({
            'question': req.question,
            'document_ids_filter': req.document_ids,
            'answer': answer.get('answer'),
            'answer_type': answer.get('answer_type'),
            'retrieved_used': len(filtered),
            'latency_ms': answer.get('latency_ms'),
            'generation_mode': answer.get('generation_mode'),
            'embed_mode': answer.get('embed_mode'),
            'candidates': [
                {
                    'rank': idx+1,
                    'hybrid_score': round(c.get('hybrid_score', c.get('score', 0)),4),
                    'accepted': c in filtered,
                    'doc': c.get('document_id'),
                    'page': c.get('page'),
                    'mode': c.get('mode'),
                    'text': (c.get('text') or '')[:260]
                }
                for idx, c in enumerate(results[:settings.top_k])
            ],
            'threshold': settings.similarity_threshold,
        })
    except Exception:
        pass
    if settings.pipeline_debug:
        logger.info(f"[PIPELINE][ASK][done] retrieved={answer.get('retrieved')} latency_ms={answer.get('latency_ms')} generation_mode={answer.get('generation_mode')} embed_mode={answer.get('embed_mode')}")
    return answer

@router.get("/debug/last")
async def debug_last(limit: int = 5):
    """Return last N ask interactions (for debugging answer quality)."""
    limit = max(1, min(limit, 20))
    return {
        'limit': limit,
        'entries': debug_buffer.last(limit)
    }


@router.get("/summarize/{document_id}", response_model=Answer)
async def summarize(document_id: int, db: AsyncSession = Depends(get_db)):
    if settings.use_in_memory:
        doc = memdb.get_document(document_id)
        if not doc:
            raise HTTPException(status_code=404, detail="Document not found")
        if not doc.get("aggregated_text"):
            raise HTTPException(status_code=400, detail="Document not ingested yet")
        return await rag.summarize(doc["aggregated_text"])  # type: ignore
    doc = await db.get(models.Document, document_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    if not doc.aggregated_text:
        raise HTTPException(status_code=400, detail="Document not ingested yet")
    return await rag.summarize(doc.aggregated_text)


@router.delete("/documents/{document_id}")
async def delete_document(document_id: int, db: AsyncSession = Depends(get_db)):
    if settings.use_in_memory:
        if not memdb.get_document(document_id):
            raise HTTPException(status_code=404, detail="Not found")
        delete_document_vectors(document_id)
        memdb.delete_document(document_id)
        return {"status": "deleted", "document_id": document_id}
    doc = await db.get(models.Document, document_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Not found")
    delete_document_vectors(document_id)
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
    if not settings.use_in_memory:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
            await conn.run_sync(Base.metadata.create_all)
    else:
        try:
            from app.services import memdb as _m
            _m.reset()
        except Exception:
            pass
    # Qdrant collection wipe
    # Qdrant disabled – no collection deletion in pure mode
    # Local upload dir cleanup
    try:
        import shutil, pathlib
        up_dir = pathlib.Path("data/uploads")
        if up_dir.exists():
            shutil.rmtree(up_dir)
            up_dir.mkdir(parents=True, exist_ok=True)
    except Exception:
        pass
    # Redis purge skipped (redis removed)
    # Retrieval reset with verification
    from app.services import retrieval as rmod
    rmod.reset_all()
    st = rmod.stats()
    success = (st.get("vectors") == 0 and st.get("lexical_chunks") == 0 and ("qdrant_points" not in st or st.get("qdrant_points") == 0))
    return {"status": "reset" if success else "partial", "message": "All stores cleared" if success else "Partial cleanup (some resources not cleared)", "retrieval_stats": st, "documents_remaining": (len(memdb.list_documents()) if settings.use_in_memory else None)}
