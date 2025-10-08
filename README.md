# Document Q&A RAG System (Simplified No-Infra Mode)
# Document Q&A RAG System (Ultra Simplified Local Mode)

Lightweight Retrieval Augmented Generation Q&A with minimal dependencies:
* FastAPI backend
* Next.js frontend (optional)
* Optional Qdrant (otherwise in‑memory + lexical TF‑IDF)
* In‑memory (default) or SQLite persistence (Postgres removed)
* Local filesystem storage (MinIO removed)
* Inline ingestion (Redis/Celery removed)
* Gemini models (hash fallback offline embeddings)

## Features
* Upload PDF / DOCX / TXT
* Parse → chunk → embed → index inline
* Hybrid semantic + lexical retrieval
* Embedded in-memory Qdrant vector index (no external service daemon, replaces prior HNSW path)
* Summarization
* Ephemeral runtime Gemini key

## Quick Start (No Docker – Docker artifacts removed)
```bash
cp .env.example .env
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r backend/requirements.txt
python backend/run_local.py
```
Frontend (optional):
```bash
cd frontend
npm install
npm run dev
```
Open http://localhost:3000

### Full Stack (Backend + Frontend) Concurrent Dev
In one shell (backend):
```bash
source .venv/bin/activate
python backend/run_local.py
```
In another shell (frontend):
```bash
cd frontend
echo "NEXT_PUBLIC_BACKEND_URL=http://localhost:8000" > .env.local
npm install   # first time only
npm run dev
```
Then browse: http://localhost:3000

If port 8000 is busy, start backend on 8010:
```bash
uvicorn app.main:app --host 127.0.0.1 --port 8010 --reload
```
and set `NEXT_PUBLIC_BACKEND_URL=http://localhost:8010`.

Optional helper (create a single script):
## One-Step Scripts (added)
* Unix/macOS: `./dev_all.sh` (creates venv, installs deps, launches backend + frontend; Ctrl+C stops)
* Windows: `dev_all.bat` (opens backend in new window, runs frontend in current)

Override ports:
```bash
BACKEND_PORT=8010 FRONTEND_PORT=3100 ./dev_all.sh
```
Check configuration without starting:
```bash
./dev_all.sh check
dev_all.bat check
```
```bash
cat > dev_all.sh <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
BACKEND_PORT=${BACKEND_PORT:-8000}
if [ ! -d .venv ]; then python3 -m venv .venv; fi
source .venv/bin/activate
pip install -q -r backend/requirements.txt
(
	cd backend
	uvicorn app.main:app --host 127.0.0.1 --port $BACKEND_PORT --reload &
	BPID=$!
	echo "Backend PID: $BPID"
)
(
	cd frontend
	echo "NEXT_PUBLIC_BACKEND_URL=http://localhost:$BACKEND_PORT" > .env.local
	[ -d node_modules ] || npm install
	npm run dev
)
EOF
chmod +x dev_all.sh
./dev_all.sh
```

Default is memory only. For SQLite persistence edit `.env`:
```
USE_IN_MEMORY=false
DATABASE_URL=sqlite+aiosqlite:///./app.db
```

## Gemini Key
Set `GEMINI_API_KEY` in `.env` or POST `/gemini/key` with `{ "key": "..." }` (ephemeral in-process).

## Persistence Modes
| Mode | Setting | Persists | Use When |
|------|---------|----------|----------|
| Memory | `USE_IN_MEMORY=true` | Nothing | Quick demo / single doc |
| Memory + Embedded Qdrant | `USE_IN_MEMORY=true` + `USE_QDRANT_EMBEDDED=true` | Nothing | Multi-doc vector search |
| SQLite | `USE_IN_MEMORY=false` | Docs + status + text | Need restart survival |
| External Qdrant | `QDRANT_URL` | Vectors externally | Larger corpora |

## Core Endpoints
`POST /upload` – upload & ingest
`GET /documents` – list docs
`POST /ask` – question answering
`GET /summarize/{id}` – summarization
`DELETE /documents/{id}` – remove doc
`POST /gemini/key` / `GET /gemini/key` / `DELETE /gemini/key`
`GET /gemini/models` + `POST /gemini/models/config`
`GET /health` – component status
`GET /diagnostics` – ingestion + Gemini stats
`POST /admin/reset?token=...` – clear all state

## Processing Flow
FastAPI → Parse (PyMuPDF / python-docx) → RecursiveCharacterTextSplitter → Gemini Embeddings → Embedded Qdrant (in-memory) → Question Embedding → Qdrant Retrieval → Gemini Generation (fallback if needed)

## Admin Reset
```
curl -X POST "http://localhost:8000/admin/reset?token=YOUR_TOKEN"
```
Clears: runtime key, SQLite tables (if used), Qdrant collection, local files, in‑memory indexes.

## Tests
```bash
pytest -q
```

## Roadmap (Future)
Optional re-introduction scripts for container builds (if needed), reranking, citation spans, versioning, evaluation harness, observability, prompt caching, RBAC.

## License
MIT








# Go to repo root
cd ~/Downloads/CodeBase/ChatWithDoc

# (Optional) Clean any old venv
rm -rf backend/.venv

# Create & activate virtual env
python3 -m venv backend/.venv
source backend/.venv/bin/activate

# Upgrade pip
pip install --upgrade pip

# Install dependencies
pip install -r backend/requirements.txt



brew install tesseract

cd backend
source .venv/bin/activate  # if not already active
python run_local.py        # hot reload enabled (uses uvicorn programmatically)

uvicorn app.main:app --reload --port 8000


cd ~/Downloads/CodeBase/ChatWithDoc
source backend/.venv/bin/activate
uvicorn backend.app.main:app --reload --port 8000



text-embedding-004 
gemini-2.5-flash
AIzaSyC0_UWujD0SSGDIejLNUosbTcd3fuBM8Zo