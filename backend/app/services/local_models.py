"""Local model helpers for offline / keyless fallback.

Embeddings: sentence-transformers (MiniLM, etc.)
Generation: GPT4All (light local quantized models)

Lazy load to avoid startup penalty if Gemini is available.
"""
from __future__ import annotations
from typing import List, Optional
from functools import lru_cache
from app.core.config import get_settings
import logging

logger = logging.getLogger(__name__)
settings = get_settings()

_EMBED_MODEL = None
_GEN_MODEL = None

def have_sentence_transformers():
    try:
        import sentence_transformers  # noqa
        return True
    except Exception:
        return False

def have_gpt4all():
    try:
        import gpt4all  # noqa
        return True
    except Exception:
        return False

def load_embed_model():
    global _EMBED_MODEL
    if _EMBED_MODEL is not None:
        return _EMBED_MODEL
    if not settings.enable_local_embedding_fallback:
        return None
    if not have_sentence_transformers():
        logger.warning("sentence-transformers not installed; local embedding fallback disabled")
        return None
    from sentence_transformers import SentenceTransformer  # type: ignore
    name = settings.local_embedding_model
    logger.info(f"[LOCAL][EMBED] loading model={name}")
    _EMBED_MODEL = SentenceTransformer(name)
    return _EMBED_MODEL

def local_embed(texts: List[str]) -> Optional[List[List[float]]]:
    mdl = load_embed_model()
    if mdl is None:
        return None
    try:
        import numpy as np  # type: ignore
        embs = mdl.encode(texts, convert_to_numpy=True, show_progress_bar=False)
        return [e.astype(float).tolist() for e in embs]
    except Exception as e:
        logger.warning(f"Local embedding failed: {e}")
        return None

def load_gen_model():
    global _GEN_MODEL
    if _GEN_MODEL is not None:
        return _GEN_MODEL
    if not settings.enable_local_generation_fallback:
        return None
    if not have_gpt4all():
        logger.warning("gpt4all not installed; local generation fallback disabled")
        return None
    from gpt4all import GPT4All  # type: ignore
    name = settings.local_generation_model
    logger.info(f"[LOCAL][GEN] loading model={name}")
    try:
        _GEN_MODEL = GPT4All(name)
    except Exception as e:
        logger.warning(f"Failed to load GPT4All model {name}: {e}")
        _GEN_MODEL = None
    return _GEN_MODEL

def local_generate(prompt: str, max_tokens: Optional[int] = None) -> Optional[str]:
    mdl = load_gen_model()
    if mdl is None:
        return None
    try:
        mtoks = max_tokens or settings.local_generation_max_tokens
        return mdl.generate(prompt, max_tokens=mtoks, temp=0.2)
    except Exception as e:
        logger.warning(f"Local generation failed: {e}")
        return None
