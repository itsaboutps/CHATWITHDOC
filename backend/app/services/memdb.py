"""Simple in-memory metadata store for documents & chunks when no DB is desired.
Not persistent, single-process only. Enabled via settings.use_in_memory = True.
"""
from __future__ import annotations

from typing import Dict, List, Optional, Any
import time
from threading import RLock

_LOCK = RLock()
_DOCS: Dict[int, dict] = {}
_CHUNKS: Dict[int, List[dict]] = {}
_NEXT_ID = 1


def reset():
    global _DOCS, _CHUNKS, _NEXT_ID
    with _LOCK:
        _DOCS = {}
        _CHUNKS = {}
        _NEXT_ID = 1


def create_document(filename: str, content_type: str, original_path: str) -> dict:
    global _NEXT_ID
    with _LOCK:
        doc_id = _NEXT_ID
        _NEXT_ID += 1
        doc = {
            "id": doc_id,
            "filename": filename,
            "content_type": content_type,
            "original_path": original_path,
            "aggregated_text": None,
            "status": "uploaded",
            "created_at": time.time(),
            "updated_at": time.time(),
        }
        _DOCS[doc_id] = doc
        _CHUNKS[doc_id] = []
        return doc


def update_document(doc_id: int, **fields: Any):
    with _LOCK:
        doc = _DOCS.get(doc_id)
        if not doc:
            return None
        doc.update(fields)
        doc["updated_at"] = time.time()
        return doc


def add_chunks(document_id: int, chunks: List[dict]):
    with _LOCK:
        arr = _CHUNKS.setdefault(document_id, [])
        base = len(arr)
        for i, ch in enumerate(chunks):
            arr.append({
                "id": base + i + 1,
                "document_id": document_id,
                "page": ch.get("page", 0),
                "position": base + i,
                "text": ch["text"],
            })


def get_document(doc_id: int) -> Optional[dict]:
    return _DOCS.get(doc_id)


def list_documents() -> List[dict]:
    with _LOCK:
        return sorted(_DOCS.values(), key=lambda d: d["created_at"], reverse=True)


def delete_document(doc_id: int):
    with _LOCK:
        _DOCS.pop(doc_id, None)
        _CHUNKS.pop(doc_id, None)
