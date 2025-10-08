# Document Q&A RAG System

End-to-end Retrieval Augmented Generation document Q&A system with FastAPI backend, Next.js frontend, Qdrant vector DB, Postgres metadata DB, MinIO object storage, Redis/Celery ingestion workers, and Gemini API for embeddings + generation.

## Features
- Upload PDF/DOCX/TXT (OCR for scanned PDFs)
- Async ingestion (parsing -> chunking -> embeddings -> vector store)
- RAG question answering with answer classification & out-of-scope detection
- Chat UI with source display

## Quick Start

1. Copy environment file:
```bash
cp .env.example .env
```
2. (Optional) Set `GEMINI_API_KEY` OR leave it blank and enter the key in the Chat UI (ephemeral, not persisted). If left blank and no UI key, system uses offline deterministic hash embeddings (lower semantic quality but functional).
3. Launch stack:
```bash
docker compose up --build
```
4. Open frontend (single-page workspace): http://localhost:3000
	All actions (upload, delete, select docs, summarize, ask, stream answers, set Gemini key) happen on the landing page.
5. (Optional) Run migrations (if using Postgres & Alembic):
```bash
make migrate
```

If embedding dimension mismatches (Gemini may change), adjust `vector_size` in `app/services/retrieval.py` inside `ensure_collection`.

### Gemini Key via UI
You can omit `GEMINI_API_KEY` in `.env`. On the top navbar, enter your Gemini key and click "Set". The key:
* Lives only in process memory (not saved to disk or DB)
* Is propagated to ingestion workers at upload time so document embeddings use the same key
* Clearing the key reverts to offline hash embedding mode

### Hybrid Retrieval
Vector similarity blended with TF-IDF (or naive keyword fallback). Blending logic lives in `retrieval.search`; adjust weight parameter there.

### API Key Auth
Set `API_KEY` in `.env` and send `x-api-key: <value>` header for protected endpoints. (Currently disabled in examples for faster local iteration.)

### JWT Auth (Multi-User)
Endpoints: `/auth/register`, `/auth/login` returning Bearer token. Include `Authorization: Bearer <token>` to scope documents per user.

### Alembic Migrations
Apply latest:
```bash
make migrate
```
Create new after model change:
```bash
make revision
make migrate
```

### Evaluation
Run sample evaluation:
```bash
make eval
```
Outputs `backend/eval_results.json`.

### Bulk Upload Script
Inside backend container (example):
```bash
docker compose exec backend python -m scripts.bulk_upload --dir /data/docs --email tester@example.com --password Test123 --concurrency 4
```
Match host directory by bind-mounting or copying docs into the container. Use `--pattern` to filter extensions.

### Streaming
`POST /ask/stream` returns SSE events with incremental `partial` payloads then final answer.

### Source Snippets
Field `source_snippets` (list) returned in `/ask` for showing context previews in UI.

## API (Backend)
The UI calls these endpoints behind the single-page interface:
- `POST /upload` — multipart file upload
- `GET /documents` — list documents + status
- `POST /ask` — answer a question (optionally filter with `document_ids`)
- `POST /ask/stream` — Server-Sent Events streaming answers
- `GET /tasks/{task_id}` — ingestion Celery task status
- `GET /health` — component health snapshot
- `GET /summarize/{document_id}` — summarize an ingested document
- `DELETE /documents/{document_id}` — remove document + vectors + object storage asset
- `POST /gemini/key` / `GET /gemini/key` / `DELETE /gemini/key` — manage ephemeral Gemini key
- `POST /admin/reset?token=...` — wipe DB, Qdrant collection, MinIO objects (Redis removed) (requires `ADMIN_RESET_TOKEN`)

## Tests
Inside backend container:
```bash
pytest -q
```

### Admin Reset
Set `ADMIN_RESET_TOKEN` in `.env` (e.g. `ADMIN_RESET_TOKEN=devreset123`). Then:
```
curl -X POST "http://localhost:8000/admin/reset?token=devreset123"
```
This clears: runtime key, tables, Qdrant collection, MinIO objects, in-memory indices.

## Roadmap Improvements
- Advanced reranking (e.g., Cohere/ColBERT) and MMR diversification
- Fine-grained citation spans & color-coded highlights
- Per-user storage quotas & lifecycle management
- Doc versioning & re-index diffing
- Batch evaluation & regression dashboards
- Observability (OpenTelemetry traces + structured logs)
- Prompt caching & answer reuse
- RBAC / organization teams

## License
MIT





docker compose logs --tail=60 backend
docker compose down
Simplified stack (Celery/Redis removed). Run:

```bash
docker compose down --remove-orphans
docker compose up -d --build backend frontend qdrant postgres minio
docker compose logs --tail=60 backend
```


# CHATWITHDOC
