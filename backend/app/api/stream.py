from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from app.schemas.base import AskRequest
from app.core.config import get_settings
from app.services import retrieval, rag
import asyncio, json, time, logging
from .routes import require_api_key

router_stream = APIRouter()
settings = get_settings()
logger = logging.getLogger(__name__)


@router_stream.post("/ask/stream")
async def ask_stream(req: AskRequest, _: None = Depends(require_api_key)):
    start = time.time()
    if getattr(settings, 'pipeline_debug', False):
        logger.info(f"[PIPELINE][ASK_STREAM][start] question='{req.question[:120]}' docs_filter={req.document_ids}")
    results = await retrieval.search(req.question, settings.top_k, document_ids=req.document_ids)
    filtered = [r for r in results if r.get("hybrid_score", r.get("score", 0)) >= settings.similarity_threshold]
    if not filtered and results:
        # fallback to top-1 like /ask endpoint
        filtered = results[:1]
    if getattr(settings, 'pipeline_debug', False):
        logger.info(f"[PIPELINE][ASK_STREAM][retrieved] total_candidates={len(results)} used={len(filtered)} threshold={settings.similarity_threshold}")

    async def gen():
        if not filtered:
            if getattr(settings, 'pipeline_debug', False):
                logger.info("[PIPELINE][ASK_STREAM][done] retrieved=0 reason=no_results")
            yield f"data: {json.dumps({'answer': 'OUT_OF_SCOPE', 'answer_type': 'out_of_scope', 'sources': [], 'retrieved': 0})}\n\n"
            yield "event: end\ndata: {}\n\n"
            return
        answer = await rag.generate_answer(req.question, filtered)
        if not answer.get("embed_mode"):
            answer["embed_mode"] = filtered[0].get("_embed_mode") if filtered and filtered[0].get("_embed_mode") else None
        answer.setdefault("generation_mode", "unknown")
        answer.setdefault("fallback_reason", None)
        full = answer.get("answer", "")
        sentences = [s.strip() for s in full.replace('\n', ' ').split('.') if s.strip()]
        acc = ""
        for s in sentences:
            acc += s + '. '
            yield f"data: {json.dumps({'partial': acc.strip()})}\n\n"
            await asyncio.sleep(0.05)
        answer["latency_ms"] = int((time.time() - start) * 1000)
        if getattr(settings, 'pipeline_debug', False):
            logger.info(f"[PIPELINE][ASK_STREAM][done] retrieved={answer.get('retrieved', len(filtered))} latency_ms={answer['latency_ms']} generation_mode={answer.get('generation_mode')}")
        yield f"data: {json.dumps(answer)}\n\n"
        yield "event: end\ndata: {}\n\n"

    return StreamingResponse(gen(), media_type="text/event-stream")
