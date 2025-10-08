# Backend Service

FastAPI application providing document ingestion, retrieval, and RAG endpoints.

See root `README.md` for full project overview.

Key modules:
- `app/services/` parsing, chunking, embeddings, retrieval, rag generation
- `app/api/routes.py` API endpoints
- `app/services/tasks.py` ingestion (Celery + sync mode)

Run locally (minimal, no external infra):
```bash
export SYNC_INGEST=true
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Tests:
```bash
pytest -q
```
