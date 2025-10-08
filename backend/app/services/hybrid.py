"""Lightweight keyword / TF-IDF style hybrid helper.

Maintains an in-process inverted index over ingested chunks to provide a
simple lexical score that we blend with vector similarity.

Data kept in-memory only; restarting the backend resets it (acceptable for dev).
"""
from __future__ import annotations
from typing import List, Dict, Optional
from collections import defaultdict
import math
import re

_CHUNKS: List[Dict] = []  # each: {text, document_id, page}
_TERM_FREQS: List[Dict[str, int]] = []  # parallel to _CHUNKS
_DOC_FREQ: Dict[str, int] = defaultdict(int)
_TOTAL_DOCS: int = 0

WORD_RE = re.compile(r"[A-Za-z0-9_]{2,}")


def _tokenize(text: str) -> List[str]:
    return WORD_RE.findall(text.lower())[:5000]


def add(chunks: List[Dict]):
    global _TOTAL_DOCS
    for ch in chunks:
        text = ch.get("text") or ""
        tokens = _tokenize(text)
        if not tokens:
            continue
        tf: Dict[str, int] = defaultdict(int)
        for t in tokens:
            tf[t] += 1
        _CHUNKS.append(ch)
        _TERM_FREQS.append(tf)
        # update doc freq (unique terms for this chunk treated as a doc surrogate)
        for term in set(tf.keys()):
            _DOC_FREQ[term] += 1
        _TOTAL_DOCS += 1


def search(query: str, top_k: int, document_ids: Optional[List[int]] = None) -> List[Dict]:
    if not _CHUNKS or not query.strip():
        return []
    q_tokens = _tokenize(query)
    if not q_tokens:
        return []
    scores: List[tuple[float, int]] = []  # (score, idx)
    q_set = set(q_tokens)
    for idx, (chunk, tf) in enumerate(zip(_CHUNKS, _TERM_FREQS)):
        if document_ids and chunk.get("document_id") not in document_ids:
            continue
        score = 0.0
        for term in q_set:
            if term in tf:
                # simple tf-idf
                df = _DOC_FREQ.get(term, 1)
                idf = math.log((1 + _TOTAL_DOCS) / (1 + df)) + 1
                score += tf[term] * idf
        if score > 0:
            scores.append((score, idx))
    scores.sort(reverse=True, key=lambda x: x[0])
    out: List[Dict] = []
    for sc, idx in scores[:top_k]:
        ch = _CHUNKS[idx]
        out.append({
            "score": sc,
            "text": ch.get("text"),
            "page": ch.get("page", 0),
            "document_id": ch.get("document_id"),
            "mode": "keyword"
        })
    return out
