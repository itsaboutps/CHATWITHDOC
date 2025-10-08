import io, json, sys, os, asyncio
import pytest
from fastapi.testclient import TestClient

repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
backend_path = os.path.join(repo_root, 'backend')
if backend_path not in sys.path:
    sys.path.insert(0, backend_path)

from app.main import app  # type: ignore
from app.core.config import get_settings  # type: ignore
from app.core import runtime_state  # type: ignore


@pytest.mark.asyncio
async def test_http_upload_and_ask_no_gemini():
    settings = get_settings()
    # Force no key and ensure fallbacks enabled
    settings.gemini_api_key = ""
    runtime_state.clear_gemini_key()
    settings.enable_local_embedding_fallback = True
    # We disable local generation to avoid large model download in CI; heuristic is fine for flow check.
    settings.enable_local_generation_fallback = False

    client = TestClient(app)
    # 1. Upload a small pseudo text file
    content = b"Alpha is the very first concept. Beta comes next."
    files = {"file": ("sample.txt", content, "text/plain")}
    up = client.post("/upload", files=files)
    assert up.status_code == 200, up.text
    doc_id = up.json()["document_id"]
    # 2. Ask a question relying on fallback embeddings and generation
    payload = {"question": "What is Alpha?", "document_ids": [doc_id]}
    ans = client.post("/ask", json=payload)
    assert ans.status_code == 200, ans.text
    data = ans.json()
    # Validate fields
    assert data.get("retrieved", 0) >= 1
    # Ensure we did NOT use gemini generation
    assert data.get("generation_mode") != "gemini"
    # Accept local-llm, fallback-heuristic, or local generation disabled path
    assert data.get("answer"), "Expected an answer string"
    # Embedding mode should not be gemini when no key
    embed_mode = data.get("embed_mode")
    assert embed_mode in (None, "local-sbert", "hash", "mixed"), embed_mode
