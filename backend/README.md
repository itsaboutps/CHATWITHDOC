# Backend (Simplified Local Mode)

FastAPI service for single-document RAG without external infra (no Redis / Celery / MinIO / Postgres / Docker required). All metadata lives in memory; uploaded file bytes are stored on local filesystem (`data/uploads/`). State is lost on restart.

## Key Modules
- `app/api/routes.py` – HTTP endpoints
- `app/services/parsing.py` / `chunking.py` – file parsing & chunk generation
- `app/services/embeddings.py` – Gemini + hash fallback embeddings
- `app/services/retrieval.py` – in-memory vector + lexical hybrid search
- `app/services/rag.py` – answer & summarization generation
- `app/services/tasks.py` – synchronous ingestion pipeline
- `app/services/memdb.py` – in-memory document metadata store

## Run Locally
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r backend/requirements.txt

# Set your Gemini key (or put GEMINI_API_KEY in .env)
export GEMINI_API_KEY=your_key_here

# Start API (reload for dev)
uvicorn app.main:app --app-dir backend/app --reload
```

Visit: http://127.0.0.1:8000/docs

## Typical Flow
1. POST /upload (multipart file) – returns document_id
2. POST /ask {"question":"..."} – gets answer with sources
3. GET /summarize/{document_id}
4. GET /diagnostics or /health for status
5. DELETE /documents/{id} to clear
6. POST /admin/reset (if you set ADMIN_RESET_TOKEN and include token param) resets everything

## Tests
```bash
pytest -q
```

## Switching Back to Persistent Mode (Optional)
If you later need persistence, set `use_in_memory=False` in `.env` and provide a `DATABASE_URL` (SQLite or Postgres). Re-enable vector DB (Qdrant) by reinstalling its client and setting `qdrant_url`.

## Notes
- Single-process only. Do not scale with multiple workers in in-memory mode.
- All embeddings/generation requests require a valid Gemini key.
- Large files are capped at 50MB.

