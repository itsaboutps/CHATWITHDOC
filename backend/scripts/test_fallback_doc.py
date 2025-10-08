"""End-to-end fallback flow test (no Gemini key required).

Usage:
  Activate your virtualenv, then run:
      python backend/scripts/test_fallback_doc.py --file /absolute/path/to/sample1.docx \
             --question "Give me an overview of this document"

This will:
  1. Clear any runtime Gemini key and force settings.gemini_api_key="".
  2. Enable local embedding fallback (sentence-transformers) and disable local generation fallback by default
     to avoid large model downloads (pass --enable-local-gen to change).
  3. Upload the provided document via the /upload endpoint (inline ingest).
  4. Issue one or more /ask queries (overview + optional specific question).
  5. Print structured JSON showing retrieval + generation modes and answer snippet.

Exit code will be non-zero if a critical step fails.
"""
from __future__ import annotations
import argparse, os, sys, json, textwrap
from typing import List

# Allow running from repo root or elsewhere
REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
BACKEND_PATH = os.path.join(REPO_ROOT, 'backend')
if BACKEND_PATH not in sys.path:
    sys.path.insert(0, BACKEND_PATH)

from fastapi.testclient import TestClient  # type: ignore
from app.main import app  # type: ignore
from app.core.config import get_settings  # type: ignore
from app.core import runtime_state  # type: ignore


def run(file_path: str, questions: List[str], enable_local_gen: bool) -> int:
    settings = get_settings()
    # Force keyless mode
    settings.gemini_api_key = ""
    runtime_state.clear_gemini_key()
    settings.enable_local_embedding_fallback = True
    settings.enable_local_generation_fallback = enable_local_gen
    client = TestClient(app)

    if not os.path.isfile(file_path):
        print(f"ERROR: File not found: {file_path}", file=sys.stderr)
        return 2

    # Infer simple content type
    ext = file_path.lower().split('.')[-1]
    if ext == 'pdf':
        ctype = 'application/pdf'
    elif ext in ('docx',):
        ctype = 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'
    else:
        ctype = 'text/plain'

    print(f"[STEP] Uploading file: {file_path} (content-type={ctype})")
    with open(file_path, 'rb') as f:
        files = {"file": (os.path.basename(file_path), f.read(), ctype)}
    r = client.post('/upload', files=files)
    if r.status_code != 200:
        print(f"ERROR: Upload failed status={r.status_code} body={r.text}", file=sys.stderr)
        return 3
    up = r.json()
    doc_id = up.get('document_id')
    status = up.get('status')
    print(f"[OK] Uploaded document_id={doc_id} status={status}")
    if status != 'ingested':
        print(f"WARN: Document status '{status}' not 'ingested'—continuing anyway")

    failures = 0
    for q in questions:
        payload = {"question": q, "document_ids": [doc_id]}
        print(f"\n[STEP] Asking: {q}")
        ans = client.post('/ask', json=payload)
        if ans.status_code != 200:
            print(f"ERROR: /ask failed status={ans.status_code} body={ans.text}", file=sys.stderr)
            failures += 1
            continue
        data = ans.json()
        # Summarize key fields
        summary = {
            'question': q,
            'answer_preview': (data.get('answer') or '')[:220],
            'retrieved': data.get('retrieved'),
            'generation_mode': data.get('generation_mode'),
            'embed_mode': data.get('embed_mode'),
            'answer_type': data.get('answer_type'),
            'sources': data.get('sources'),
            'fallback_reason': data.get('fallback_reason'),
        }
        print(json.dumps(summary, indent=2))
        if data.get('generation_mode') == 'gemini':
            print("ERROR: Gemini path used unexpectedly in keyless test", file=sys.stderr)
            failures += 1
    return 0 if failures == 0 else 4


def main():
    parser = argparse.ArgumentParser(formatter_class=argparse.RawDescriptionHelpFormatter, description=__doc__)
    parser.add_argument('--file', required=True, help='Absolute path to the document (pdf, docx, txt).')
    parser.add_argument('--question', default='Give me an overview of this document', help='Primary question to ask.')
    parser.add_argument('--extra-question', action='append', default=[], help='Additional /ask question(s)')
    parser.add_argument('--enable-local-gen', action='store_true', help='Enable local LLM generation fallback (may download model).')
    args = parser.parse_args()
    questions = [args.question] + list(args.extra_question)
    code = run(args.file, questions, args.enable_local_gen)
    sys.exit(code)


if __name__ == '__main__':
    main()
