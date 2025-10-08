"""End-to-end smoke test (in-memory mode).
Runs against the FastAPI `app` object directly (no network server needed).
Verifies: /health -> /upload -> /documents -> /ask -> /summarize.

Usage:
  source .venv_e2e/bin/activate  # or your venv
  python backend/scripts/e2e_smoke.py
"""
from __future__ import annotations

import sys, pathlib, json, time
from typing import Any

# Ensure backend root (containing `app`) is on sys.path
ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.main import app  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402


def main() -> int:
    client = TestClient(app)
    report: dict[str, Any] = {"steps": []}

    # 1. Health
    r = client.get("/health")
    report["health"] = r.json()
    report["steps"].append("health_ok" if r.status_code == 200 else "health_fail")

    # 2. Upload sample text file
    content = b"Apples are nutritious fruits. Oranges are citrus. The sky appears blue due to Rayleigh scattering."
    files = {"file": ("sample.txt", content, "text/plain")}
    r_up = client.post("/upload", files=files)
    if r_up.status_code != 200:
        print("Upload failed", r_up.status_code, r_up.text)
        return 1
    upload_payload = r_up.json()
    doc_id = upload_payload["document_id"]
    report["upload"] = upload_payload
    report["steps"].append("upload_ok")

    # 3. List documents
    r_docs = client.get("/documents")
    report["documents"] = r_docs.json()
    report["steps"].append("documents_ok")

    # 4. Ask a question (forces retrieval + generation fallback if no key)
    q_payload = {"question": "What color is the sky?", "document_ids": [doc_id]}
    r_ask = client.post("/ask", json=q_payload)
    report["ask"] = r_ask.json()
    report["steps"].append("ask_ok" if r_ask.status_code == 200 else "ask_fail")

    # 5. Summarize
    # Document ingestion is inline; summarization may fallback if no Gemini key.
    r_sum = client.get(f"/summarize/{doc_id}")
    report["summarize"] = r_sum.json()
    report["steps"].append("summarize_ok" if r_sum.status_code == 200 else "summarize_fail")

    # Compact output
    print(json.dumps(report, indent=2)[:4000])
    # Basic success heuristic
    success = all(s.endswith("_ok") for s in report["steps"])
    return 0 if success else 2


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
