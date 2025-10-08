from app.core.config import get_settings
from .embeddings import embed_texts
from typing import List, Dict, Optional
import logging, math, re, collections
try:  # optional embedded qdrant
    from qdrant_client import QdrantClient
    from qdrant_client.models import Distance, VectorParams, PointStruct, Filter, FieldCondition, MatchAny
except Exception:  # pragma: no cover
    QdrantClient = None  # type: ignore

logger = logging.getLogger(__name__)

settings = get_settings()

client = None  # embedded qdrant client if enabled

# In-memory fallback store (vector)
_MEM_INDEX: List[Dict] = []  # {vector, text, page, document_id}
_NEXT_ID = 0

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


def ensure_collection(vector_size: Optional[int] = None):
    global client
    if not getattr(settings, 'use_qdrant_embedded', False):
        return
    if QdrantClient is None:
        return
    if client is None:
        # Embedded (in-memory) Qdrant instance
        client = QdrantClient(path=':memory:')
    if vector_size:
        try:
            client.get_collection(settings.qdrant_collection)
        except Exception:
            client.recreate_collection(
                collection_name=settings.qdrant_collection,
                vectors_config=VectorParams(size=vector_size, distance=Distance.COSINE),
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
    global _NEXT_ID
    use_qdrant = getattr(settings, 'use_qdrant_embedded', False) and QdrantClient is not None
    if getattr(settings, 'pipeline_debug', False):
        logger.info(f"[PIPELINE][INDEX] adding_chunks={len(chunks)} embed_mode={embed_mode} dim={len(vectors[0])} qdrant_embedded={use_qdrant}")
    for chunk, vec in zip(chunks, vectors):
        rec = {
            "id": _NEXT_ID,
            "vector": vec,
            "text": chunk.get("text"),
            "page": chunk.get("page", 0),
            "document_id": chunk.get("document_id"),
            "_embed_mode": embed_mode
        }
        _MEM_INDEX.append(rec)
        _NEXT_ID += 1
    if use_qdrant:
        # push points to embedded qdrant
        try:
            pts = []
            for rec in _MEM_INDEX[-len(chunks):]:
                pts.append(PointStruct(id=rec['id'], vector=rec['vector'], payload={'document_id': rec.get('document_id'), 'text': rec['text'], 'page': rec['page']}))
            client.upsert(collection_name=settings.qdrant_collection, points=pts)  # type: ignore
            if getattr(settings, 'pipeline_debug', False):
                logger.info(f"[PIPELINE][INDEX] qdrant_upsert points={len(pts)} collection={settings.qdrant_collection}")
        except Exception as e:  # pragma: no cover
            logger.warning(f"Embedded Qdrant upsert failed: {e}")
    # lexical index update
    try:
        _lex_add(chunks)
    except Exception:  # pragma: no cover
        pass


async def search(query: str, top_k: Optional[int] = None, document_ids: Optional[List[int]] = None, hybrid_weight: float = 0.4):
    top_k = top_k or settings.top_k
    qvecs = await embed_texts([query])
    qvec = qvecs[0]
    query_embed_mode = getattr(qvecs, "_embed_mode", "unknown")
    if getattr(settings, 'pipeline_debug', False):
        logger.info(f"[PIPELINE][RETRIEVE][embed_query] query='{query[:80]}' mode={query_embed_mode} dim={len(qvec)}")
    vector_results = _memory_only_search(qvec, top_k, document_ids)
    for r in vector_results:
        r["_embed_mode"] = query_embed_mode
    # Keyword layer (internal)
    keyword_results = _lex_search(query, top_k, document_ids)
    def normalize(items):
        if not items:
            return
        scs = [i["score"] for i in items]
        mn, mx = min(scs), max(scs)
        if mx == mn:
            # All equal scores: if non-zero give full weight so a solitary keyword/vector hit isn't discarded.
            for i in items:
                i["norm"] = 1.0 if i["score"] > 0 else 0.0
            return
        rng = mx - mn
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
    if getattr(settings, 'pipeline_debug', False):
        vr = [round(r.get('score',0),4) for r in vector_results[:5]]
        kr = [round(r.get('score',0),4) for r in keyword_results[:5]]
        hr = [round(r.get('hybrid_score',0),4) for r in final[:top_k]]
        logger.info(f"[PIPELINE][RETRIEVE][merge] query_top_k={top_k} vector_modes={[r.get('mode') for r in vector_results[:1]]} vector_scores={vr} keyword_scores={kr} hybrid_scores={hr}")
        # Per-candidate verbose lines (top_k only) to diagnose wrong answers / missing context
        for idx, cand in enumerate(final[:top_k]):
            snippet = (cand.get('text') or '').replace('\n',' ')[:140]
            logger.info(
                f"[PIPELINE][RETRIEVE][cand] rank={idx+1} hybrid={cand.get('hybrid_score'):.4f} raw={cand.get('score',0):.4f} mode={cand.get('mode')} doc={cand.get('document_id')} page={cand.get('page')} text='{snippet}'")
    return final[:top_k]

def delete_document_vectors(document_id: int):
    global _MEM_INDEX
    to_remove_ids = {c.get("id") for c in _MEM_INDEX if c.get("document_id") == document_id}
    _MEM_INDEX = [c for c in _MEM_INDEX if c.get("document_id") != document_id]
    # Remove from embedded qdrant if enabled
    if getattr(settings, 'use_qdrant_embedded', False) and QdrantClient is not None and client is not None and to_remove_ids:
        try:
            client.delete(collection_name=settings.qdrant_collection, points=list(to_remove_ids))  # type: ignore
        except Exception as e:  # pragma: no cover
            logger.warning(f"Qdrant delete failed: {e}")


def _memory_only_search(qvec: List[float], top_k: int, document_ids: Optional[List[int]]):
    if not _MEM_INDEX:
        return []
    use_qdrant = getattr(settings, 'use_qdrant_embedded', False) and QdrantClient is not None and client is not None
    if use_qdrant:
        try:
            flt = None
            if document_ids:
                flt = Filter(must=[FieldCondition(key='document_id', match=MatchAny(any=document_ids))])  # type: ignore
            ensure_collection(len(qvec))
            qr = client.search(
                collection_name=settings.qdrant_collection,  # type: ignore
                query_vector=qvec,
                limit=top_k*3,
                query_filter=flt,
            )
            out = []
            for r in qr:
                out.append({
                    'score': r.score,
                    'text': r.payload.get('text', ''),
                    'page': r.payload.get('page', 0),
                    'document_id': r.payload.get('document_id'),
                    'mode': 'vector-qdrant',
                    'hybrid_score': 0.0
                })
            out.sort(key=lambda x: x['score'], reverse=True)
            return out[:top_k]
        except Exception as e:  # pragma: no cover
            logger.warning(f"Embedded Qdrant search failed, fallback to other methods: {e}")
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
            "mode": "vector-bruteforce",
            "hybrid_score": 0.0
        })
    scored.sort(key=lambda x: x["score"], reverse=True)
    return scored[:top_k]


def stats() -> Dict[str, int]:
    """Return counts of vectors and lexical entries (best-effort)."""
    vec_count = len(_MEM_INDEX)
    lex_count = len(_LEX_CHUNKS)
    qdrant_points = None
    if getattr(settings, 'use_qdrant_embedded', False) and QdrantClient is not None and client is not None:
        try:  # count points if possible
            q = client.count(collection_name=settings.qdrant_collection, exact=True)  # type: ignore
            qdrant_points = q.count if hasattr(q, 'count') else None
        except Exception:  # pragma: no cover
            qdrant_points = None
    out = {"vectors": vec_count, "lexical_chunks": lex_count}
    if qdrant_points is not None:
        out["qdrant_points"] = qdrant_points
    return out


def reset_all():
    """Clear in-memory indexes and embedded qdrant collection."""
    global _MEM_INDEX, _NEXT_ID, _LEX_CHUNKS, _LEX_TERM_FREQS, _LEX_DOC_FREQ, _LEX_TOTAL, client
    _MEM_INDEX.clear()
    _NEXT_ID = 0
    _LEX_CHUNKS.clear()
    _LEX_TERM_FREQS.clear()
    _LEX_DOC_FREQ.clear()
    _LEX_TOTAL = 0
    if getattr(settings, 'use_qdrant_embedded', False) and QdrantClient is not None and client is not None:
        try:
            # Recreate empty collection preserving vector parameters if known; simplest is to drop and ignore errors.
            client.delete_collection(settings.qdrant_collection)  # type: ignore
        except Exception:
            pass
        # collection will be lazily recreated on next add
