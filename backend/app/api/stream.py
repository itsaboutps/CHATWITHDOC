from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from app.schemas.base import AskRequest
from app.core.config import get_settings
from app.services import retrieval, rag
import asyncio, json, time
from .routes import require_api_key

router_stream = APIRouter()
settings = get_settings()


@router_stream.post("/ask/stream")
async def ask_stream(req: AskRequest, _: None = Depends(require_api_key)):
    start = time.time()
    results = await retrieval.search(req.question, settings.top_k, document_ids=req.document_ids)
    filtered = [r for r in results if r.get("hybrid_score", r.get("score", 0)) >= settings.similarity_threshold]

    async def gen():
        if not filtered:
            yield f"data: {json.dumps({'answer': 'OUT_OF_SCOPE', 'answer_type': 'out_of_scope', 'sources': []})}\n\n"
            yield "event: end\ndata: {}\n\n"
            return
        answer = await rag.generate_answer(req.question, filtered)
        # Propagate embedding mode from first chunk if present
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
        yield f"data: {json.dumps(answer)}\n\n"
        yield "event: end\ndata: {}\n\n"

    return StreamingResponse(gen(), media_type="text/event-stream")
