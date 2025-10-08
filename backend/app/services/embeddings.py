import httpx
from app.core.config import get_settings
from app.core import runtime_state
from typing import List
from tenacity import retry, wait_exponential, stop_after_attempt
import hashlib
import math
import asyncio
from loguru import logger


class EmbeddingList(list):
    """Simple subclass of list so we can attach the `_embed_mode` attribute.
    Using setattr on a plain list raises AttributeError, which was causing
    tenacity retries and ingestion failures."""
    pass

settings = get_settings()

# Base endpoint; we'll prepend 'models/' exactly once.
GEMINI_EMBED_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:embedContent?key={key}"


@retry(wait=wait_exponential(multiplier=1, min=1, max=10), stop=stop_after_attempt(3))
async def embed_texts(texts: List[str]) -> List[List[float]]:
    """Return embeddings for texts.
    Annotates the returned list with attribute _embed_mode = 'hash' | 'gemini' | 'mixed'.
    If Gemini key is missing OR any chunk call fails, a hash fallback is used per chunk.
    """
    runtime_key = runtime_state.get_gemini_key(settings.gemini_api_key)
    # Helper to hash-embed one text
    def hash_embed(t: str) -> List[float]:
        h = hashlib.sha256(t.encode()).digest()
        raw = (h * (256 // len(h) + 1))[:256]
        vec = [(b / 255.0) for b in raw]
        norm = math.sqrt(sum(x * x for x in vec)) or 1.0
        return [x / norm for x in vec]

    if not runtime_key:
        vectors: EmbeddingList = EmbeddingList([hash_embed(t) for t in texts])
        setattr(vectors, "_embed_mode", "hash")
        return vectors

    raw_model = settings.embedding_model or "embedding-001"
    cleaned_model = raw_model.split('/')[-1] if raw_model.startswith('models/') else raw_model
    model_path = cleaned_model
    url = GEMINI_EMBED_URL.format(model=model_path, key=runtime_key)
    out: EmbeddingList = EmbeddingList()
    used_hash = False
    delay_ms = getattr(settings, "embedding_rate_delay_ms", 0)
    async with httpx.AsyncClient(timeout=60) as client:
        for t in texts:
            success = False
            for attempt in range(3):
                try:
                    payload = {"model": model_path, "content": {"parts": [{"text": t[:6000]}]}}
                    r = await client.post(url, json=payload)
                    if r.status_code == 429:
                        # rate limited; backoff then retry
                        wait_s = 0.4 * (attempt + 1)
                        logger.warning(f"Embedding 429 rate-limit (attempt {attempt+1}); backing off {wait_s:.2f}s")
                        await asyncio.sleep(wait_s)
                        continue
                    r.raise_for_status()
                    data = r.json()
                    try:
                        vec = data["embedding"]["values"]  # type: ignore[index]
                    except Exception:
                        raise ValueError(f"Unexpected embedding response shape: {data}")
                    out.append(vec)  # type: ignore[arg-type]
                    runtime_state.set_gemini_success()
                    success = True
                    break
                except Exception as e:
                    if attempt < 2:
                        await asyncio.sleep(0.2 * (attempt + 1))
                        continue
                    logger.warning(f"Embedding chunk failed ({e}); using hash fallback for this chunk")
                    runtime_state.set_gemini_failure(f"embed_error: {e}")
            if not success:
                out.append(hash_embed(t))
                used_hash = True
            if delay_ms and success:
                await asyncio.sleep(delay_ms / 1000.0)
    setattr(out, "_embed_mode", "mixed" if used_hash else "gemini")
    return out
