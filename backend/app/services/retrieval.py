from qdrant_client import QdrantClient
from qdrant_client.http import models as qmodels
from app.core.config import get_settings
from .embeddings import embed_texts
from typing import List, Dict, Optional
from loguru import logger
import math, re, collections

settings = get_settings()

client = QdrantClient(url=settings.qdrant_url)

# In-memory fallback store (vector)
_MEM_INDEX: List[Dict] = []  # {vector, text, page, document_id}

# Simple lexical index for keyword scoring
_LEX_CHUNKS: List[Dict] = []  # parallel list of chunk dicts
_LEX_TERM_FREQS: List[Dict[str, int]] = []
_LEX_DOC_FREQ: Dict[str, int] = collections.defaultdict(int)
_LEX_TOTAL: int = 0
_WORD_RE = re.compile(r"[A-Za-z0-9_]{2,}")


def _tokenize(text: str):
    return _WORD_RE.findall((text or "").lower())[:5000]


def _lex_add(chunks: List[Dict]):
    global _LEX_TOTAL
    for ch in chunks:
        tokens = _tokenize(ch.get("text", ""))
        if not tokens:
            continue
        tf: Dict[str, int] = collections.defaultdict(int)
        for t in tokens:
            tf[t] += 1
        _LEX_CHUNKS.append(ch)
        _LEX_TERM_FREQS.append(tf)
        for term in set(tf.keys()):
            _LEX_DOC_FREQ[term] += 1
        _LEX_TOTAL += 1


def _lex_search(query: str, top_k: int, document_ids: Optional[List[int]]):
    if not _LEX_CHUNKS or not query.strip():
        return []
    q_tokens = _tokenize(query)
    if not q_tokens:
        return []
    q_set = set(q_tokens)
    scored: List[tuple[float, int]] = []
    for idx, (chunk, tf) in enumerate(zip(_LEX_CHUNKS, _LEX_TERM_FREQS)):
        if document_ids and chunk.get("document_id") not in document_ids:
            continue
        score = 0.0
        for term in q_set:
            if term in tf:
                df = _LEX_DOC_FREQ.get(term, 1)
                idf = math.log((1 + _LEX_TOTAL) / (1 + df)) + 1
                score += tf[term] * idf
        if score > 0:
            scored.append((score, idx))
    scored.sort(key=lambda x: x[0], reverse=True)
    out: List[Dict] = []
    for sc, idx in scored[:top_k]:
        ch = _LEX_CHUNKS[idx]
        out.append({
            "score": sc,
            "text": ch.get("text"),
            "page": ch.get("page", 0),
            "document_id": ch.get("document_id"),
            "mode": "keyword"
        })
    return out


def ensure_collection(vector_size: int | None = None):
    try:
        existing = {c.name: c for c in client.get_collections().collections}
    except Exception:
        # Qdrant not available yet
        return
    if settings.qdrant_collection in existing:
        return
    if vector_size is None:
        # Defer creation until we know vector size (first add_documents or search call)
        logger.debug("Deferring collection creation until vector size known")
        return
    client.recreate_collection(
        collection_name=settings.qdrant_collection,
        vectors_config=qmodels.VectorParams(size=vector_size, distance=qmodels.Distance.COSINE),
    )


async def add_documents(chunks: List[Dict]):
    if not chunks:
        return
    texts = [c["text"] for c in chunks]
    vectors = await embed_texts(texts)
    embed_mode = getattr(vectors, "_embed_mode", "unknown")
    if not vectors:
        logger.warning("No vectors returned for chunks; skipping add_documents")
        return
    # Ensure collection with actual size
    ensure_collection(len(vectors[0]))
    points = []
    for idx, (chunk, vec) in enumerate(zip(chunks, vectors)):
        # Qdrant PointStruct requires an id (int or UUID). Use a simple incremental integer.
        points.append(qmodels.PointStruct(id=idx, vector=vec, payload={**chunk}))
        _MEM_INDEX.append({
            "vector": vec,
            "text": chunk.get("text"),
            "page": chunk.get("page", 0),
            "document_id": chunk.get("document_id"),
            "_embed_mode": embed_mode
        })
    try:
        client.upsert(collection_name=settings.qdrant_collection, points=points)
    except Exception:
        logger.warning("Vector upsert skipped (Qdrant unreachable)")
    # lexical index update
    try:
        _lex_add(chunks)
    except Exception:  # pragma: no cover
        pass


async def search(query: str, top_k: int | None = None, document_ids: Optional[List[int]] = None, hybrid_weight: float = 0.4):
    top_k = top_k or settings.top_k
    qvecs = await embed_texts([query])
    qvec = qvecs[0]
    query_embed_mode = getattr(qvecs, "_embed_mode", "unknown")
    ensure_collection(len(qvec))
    search_filter = None
    if document_ids:
        try:
            search_filter = qmodels.Filter(
                must=[qmodels.FieldCondition(key="document_id", match=qmodels.MatchAny(any=document_ids))]
            )
        except Exception:  # pragma: no cover
            search_filter = None
    try:
        res = client.search(
            collection_name=settings.qdrant_collection,
            query_vector=qvec,
            limit=top_k,
            query_filter=search_filter,
        )
    except Exception:
        return _memory_only_search(qvec, top_k, document_ids)
    vector_results = []
    for r in res:
        payload = r.payload or {}
        vector_results.append({
            "score": r.score,
            "text": payload.get("text"),
            "page": payload.get("page", 0),
            "document_id": payload.get("document_id"),
            "mode": "vector",
            "_embed_mode": query_embed_mode
        })
    # Keyword layer (internal)
    keyword_results = _lex_search(query, top_k, document_ids)
    def normalize(items):
        if not items:
            return
        scs = [i["score"] for i in items]
        mn, mx = min(scs), max(scs)
        rng = (mx - mn) or 1.0
        for i in items:
            i["norm"] = (i["score"] - mn) / rng
    normalize(vector_results)
    normalize(keyword_results)
    merged: Dict[tuple, Dict] = {}
    for it in vector_results:
        merged[(it["text"], it.get("document_id"))] = it
    for it in keyword_results:
        key = (it["text"], it.get("document_id"))
        if key in merged:
            existing = merged[key]
            existing["hybrid_score"] = (1 - hybrid_weight) * existing.get("norm", 0) + hybrid_weight * it.get("norm", 0)
        else:
            it["norm"] = it.get("norm", 0)
            it["hybrid_score"] = hybrid_weight * it.get("norm", 0)
            merged[key] = it
    final = list(merged.values())
    for f in final:
        if "hybrid_score" not in f:
            f["hybrid_score"] = f.get("norm", 0)
    final.sort(key=lambda x: x["hybrid_score"], reverse=True)
    return final[:top_k]

def delete_document_vectors(document_id: int):
    try:
        client.delete(
            collection_name=settings.qdrant_collection,
            points_selector=qmodels.FilterSelector(
                filter=qmodels.Filter(must=[qmodels.FieldCondition(key="document_id", match=qmodels.MatchValue(value=document_id))])
            ),
        )
    except Exception:
        logger.warning(f"Failed to delete vectors for document {document_id} (Qdrant unreachable)")
    global _MEM_INDEX
    _MEM_INDEX = [c for c in _MEM_INDEX if c.get("document_id") != document_id]


def _memory_only_search(qvec: List[float], top_k: int, document_ids: Optional[List[int]]):
    if not _MEM_INDEX:
        return []
    def cosine(a, b):
        return sum(x*y for x,y in zip(a,b)) / ((math.sqrt(sum(x*x for x in a)) or 1.0) * (math.sqrt(sum(y*y for y in b)) or 1.0))
    candidates = _MEM_INDEX
    if document_ids:
        candidates = [c for c in candidates if c.get("document_id") in document_ids]
    scored = []
    for c in candidates:
        scored.append({
            "score": cosine(qvec, c["vector"]),
            "text": c["text"],
            "page": c["page"],
            "document_id": c.get("document_id"),
            "mode": "vector-fallback",
            "hybrid_score": 0.0
        })
    scored.sort(key=lambda x: x["score"], reverse=True)
    return scored[:top_k]
