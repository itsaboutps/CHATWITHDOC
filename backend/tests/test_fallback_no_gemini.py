import pytest
import sys, os

# Ensure backend package is on path when tests invoked from repo root
repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
backend_path = os.path.join(repo_root, 'backend')
if backend_path not in sys.path:
    sys.path.insert(0, backend_path)

from app.core import runtime_state  # type: ignore
from app.core.config import get_settings  # type: ignore
from app.services import retrieval  # type: ignore
from app.services import rag  # type: ignore


@pytest.mark.asyncio
async def test_fallback_when_no_gemini_key():
    settings = get_settings()
    # Preserve originals
    orig_key = settings.gemini_api_key
    orig_local_gen = settings.enable_local_generation_fallback
    orig_local_emb = settings.enable_local_embedding_fallback
    try:
        # Force no key
        settings.gemini_api_key = ""
        runtime_state.clear_gemini_key()
        # Ensure local embedding fallback stays on; disable local generation to avoid heavy model download in CI
        settings.enable_local_embedding_fallback = True
        settings.enable_local_generation_fallback = False
        # Reset any prior index state
        retrieval.reset_all()
        # Add minimal sample chunks
        chunks = [
            {"text": "Alpha is the first test concept.", "page": 1, "document_id": 1},
            {"text": "Beta follows after Alpha in this tiny sample.", "page": 2, "document_id": 1},
        ]
        await retrieval.add_documents(chunks)
        res = await retrieval.search("What is Alpha?", top_k=3)
        assert res, "Expected retrieval results in fallback mode"
        # Confirm embedding mode is not gemini
        embed_mode = res[0].get("_embed_mode")
        assert embed_mode in ("local-sbert", "hash", "mixed", None), f"Unexpected embed mode: {embed_mode}"
        answer = await rag.generate_answer("What is Alpha?", res)
        assert answer.get("generation_mode") != "gemini", "Generation should not use gemini when key absent"
        assert answer.get("answer"), "Answer text should be present"
    finally:
        # Restore settings
        settings.gemini_api_key = orig_key
        settings.enable_local_generation_fallback = orig_local_gen
        settings.enable_local_embedding_fallback = orig_local_emb
        if orig_key:
            runtime_state.set_gemini_key(orig_key)
