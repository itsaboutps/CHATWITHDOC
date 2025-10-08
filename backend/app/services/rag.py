import httpx
import json
import time
from typing import List, Dict
from app.core.config import get_settings
from app.core import runtime_state
from app.services import local_models
from loguru import logger

settings = get_settings()
if settings.generation_model == "gemini-1.5-flash":  # backward compatibility auto-upgrade
    settings.generation_model = "gemini-flash-latest"

GEMINI_GEN_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={key}"

PROMPT_TEMPLATE = """You are a domain-constrained QA assistant. Use ONLY the supplied context to answer. If the answer is not in context, reply with OUT_OF_SCOPE.
Classify the answer type as one of: factual, contextual, analytical, descriptive, summarization, out_of_scope.
Return JSON with keys: answer, answer_type, sources (list).

Question: {question}
Context:
{context}
"""


async def generate_answer(question: str, context_chunks: List[Dict]):
    start = time.time()
    if getattr(settings, 'pipeline_debug', False):
        logger.info(f"[PIPELINE][GENERATE][start] question='{question[:120]}' ctx_chunks={len(context_chunks)}")
    if not context_chunks:
        return {
            "answer": "I'm sorry, that appears to be outside the scope of the provided documents.",
            "answer_type": "out_of_scope",
            "sources": [],
            "latency_ms": int((time.time() - start) * 1000),
            "retrieved": 0,
            "generation_mode": "none",
            "fallback_reason": "no_context",
        }
    context_text = "\n---\n".join([f"[p{c['page']}] {c['text'][:800]}" for c in context_chunks])
    prompt = PROMPT_TEMPLATE.format(question=question, context=context_text)
    runtime_key = runtime_state.get_gemini_key(settings.gemini_api_key)
    model_try = settings.generation_model
    tried_models = []
    data = None
    error_obj = None
    # Try original, then prefixed models/<name>, then -latest variant
    candidates = [model_try]
    if not model_try.startswith("models/"):
        candidates.append(f"models/{model_try}")
    if not model_try.endswith("-latest"):
        candidates.append(model_try + "-latest")
    for cand in candidates:
        url = GEMINI_GEN_URL.format(model=cand, key=runtime_key)
        tried_models.append(cand)
        try:
            async with httpx.AsyncClient(timeout=120) as client:
                payload = {"contents": [{"parts": [{"text": prompt}]}]}
                r = await client.post(url, json=payload)
                if r.status_code == 404:
                    logger.warning(f"Generation 404 for model {cand}; trying next candidate if any")
                    if getattr(settings, 'pipeline_debug', False):
                        logger.info(f"[PIPELINE][GENERATE][model_404] model={cand}")
                    continue
                r.raise_for_status()
                data = r.json()
                runtime_state.set_gemini_success()
                if getattr(settings, 'pipeline_debug', False):
                    logger.info(f"[PIPELINE][GENERATE][model_ok] model={cand} retrieved={len(context_chunks)}")
                break
        except Exception as e:  # store and keep trying
            error_obj = e
            runtime_state.set_gemini_failure(f"gen_error: {e}")
            logger.warning(f"Generation attempt failed for {cand}: {e}")
            if getattr(settings, 'pipeline_debug', False):
                logger.error(f"[PIPELINE][GENERATE][model_error] model={cand} error={e}")
            continue
    if data is None:
        e = error_obj or Exception("All generation attempts failed")
        # Attempt local generation fallback first
        local_ctx = '\n'.join([c['text'][:800] for c in context_chunks])
        local_prompt = f"You are a grounding assistant. Use ONLY the provided context to answer. If answer not present say OUT_OF_SCOPE.\nQuestion: {question}\nContext:\n{local_ctx}\nAnswer:"  # noqa
        local_answer = None
        if settings.enable_local_generation_fallback:
            if getattr(settings, 'pipeline_debug', False):
                logger.info("[PIPELINE][GENERATE][fallback_try] strategy=local-llm model=%s" % settings.local_generation_model)
            local_answer = local_models.local_generate(local_prompt, max_tokens= settings.local_generation_max_tokens)
        if local_answer:
            if getattr(settings, 'pipeline_debug', False):
                logger.info("[PIPELINE][GENERATE][fallback_used] mode=local-llm")
            return {
                "answer": local_answer.strip(),
                "answer_type": "contextual",
                "sources": [f"page:{c['page']}" for c in context_chunks],
                "latency_ms": int((time.time() - start) * 1000),
                "retrieved": len(context_chunks),
                "generation_mode": "local-llm",
                "fallback_reason": f"gemini_error: {e}"[:160],
                "tried_models": tried_models,
            }
        # Heuristic fallback if no local model
        if getattr(settings, 'pipeline_debug', False):
            logger.info("[PIPELINE][GENERATE][fallback_used] mode=heuristic")
        q_terms = [t.lower() for t in question.split() if len(t) > 3][:8]
        sentences: List[str] = []
        for c in context_chunks:
            for part in c['text'].split('.'):
                s = part.strip()
                if not s:
                    continue
                if any(t in s.lower() for t in q_terms):
                    sentences.append(s)
        unique: List[str] = []
        for s in sentences:
            if s not in unique:
                unique.append(s)
        answer_fallback = '. '.join(unique[:4]) or 'Relevant context found but model generation failed.'
        return {
            "answer": answer_fallback,
            "answer_type": "contextual" if unique else "out_of_scope",
            "sources": [f"page:{c['page']}" for c in context_chunks],
            "latency_ms": int((time.time() - start) * 1000),
            "retrieved": len(context_chunks),
            "generation_mode": "fallback-heuristic",
            "fallback_reason": f"{e}"[:160],
            "tried_models": tried_models,
        }
    # Attempt to parse JSON from model output
    try:
        text = data["candidates"][0]["content"]["parts"][0]["text"]  # type: ignore
        first_brace = text.find('{')
        last_brace = text.rfind('}')
        if first_brace != -1:
            json_str = text[first_brace:last_brace+1]
            parsed = json.loads(json_str)
        else:
            parsed = {"answer": text.strip(), "answer_type": "factual", "sources": []}
    except Exception:
        parsed = {"answer": "Unable to parse model response.", "answer_type": "out_of_scope", "sources": []}
    parsed.setdefault("sources", [f"page:{c['page']}" for c in context_chunks])
    parsed["latency_ms"] = int((time.time() - start) * 1000)
    parsed["retrieved"] = len(context_chunks)
    parsed["generation_mode"] = "gemini"
    parsed.setdefault("model_used", tried_models[-1] if tried_models else settings.generation_model)
    parsed.setdefault("fallback_reason", None)
    if getattr(settings, 'pipeline_debug', False):
        logger.info(f"[PIPELINE][GENERATE][done] model={parsed.get('model_used')} latency_ms={parsed.get('latency_ms')} retrieved={parsed.get('retrieved')} answer_type={parsed.get('answer_type')}")
    return parsed

SUMMARY_PROMPT = """You are a summarization assistant. Produce a concise, comprehensive summary of the document content below. Return JSON with keys: answer (the summary), answer_type='summarization', sources (list of page numbers referenced).\n\nContent:\n{content}\n"""


async def summarize(content: str):
    runtime_key = runtime_state.get_gemini_key(settings.gemini_api_key)
    url = GEMINI_GEN_URL.format(model=settings.generation_model, key=runtime_key)
    prompt = SUMMARY_PROMPT.format(content=content[:60000])
    try:
        async with httpx.AsyncClient(timeout=180) as client:
            r = await client.post(url, json={"contents": [{"parts": [{"text": prompt}]}]})
            r.raise_for_status()
            data = r.json()
    except Exception as e:
        logger.warning(f"Summarization failed: {e}")
        return {"answer": "Summarization unavailable (model error).", "answer_type": "summarization", "sources": []}
    try:
        text = data["candidates"][0]["content"]["parts"][0]["text"]  # type: ignore
        first = text.find('{')
        last = text.rfind('}')
        if first != -1:
            js = text[first:last+1]
            j = json.loads(js)
        else:
            j = {"answer": text.strip()}
    except Exception:
        j = {"answer": "Summarization failed."}
    j.setdefault("answer_type", "summarization")
    j.setdefault("sources", [])
    return j
