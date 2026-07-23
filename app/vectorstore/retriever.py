"""Гибридный retrieval: dense (Qdrant/Chroma) + BM25 fusion."""

from __future__ import annotations

import re
from collections import defaultdict

from app.core.config import get_settings
from app.core.regions import FEDERAL_CODE, get_region, resolve_region_code
from app.vectorstore.types import RetrievedChunk

__all__ = ["RetrievedChunk", "retrieve", "hybrid_retrieve", "retrieve_curated"]

_TOKEN = re.compile(r"[а-яa-z0-9./\-]+", re.IGNORECASE)


def _region_where(region_code: str | None) -> dict | None:
    if not region_code:
        return None
    resolved = resolve_region_code(region_code)
    doc = get_region(resolved)
    codes = list(dict.fromkeys([resolved, *doc.aliases]))
    if len(codes) == 1:
        return {"region_code": codes[0]}
    return {"region_code": {"$in": codes}}


def _tokenize(text: str) -> list[str]:
    return [t.lower() for t in _TOKEN.findall(text or "") if len(t) > 1]


def _bm25_scores(query: str, documents: list[str]) -> list[float]:
    """Лёгкий BM25 без внешней зависимости (Okapi-подобная формула)."""
    if not documents:
        return []
    q_tokens = _tokenize(query)
    if not q_tokens:
        return [0.0] * len(documents)
    doc_tokens = [_tokenize(d) for d in documents]
    df: dict[str, int] = defaultdict(int)
    for toks in doc_tokens:
        for t in set(toks):
            df[t] += 1
    n = len(documents)
    avgdl = sum(len(t) for t in doc_tokens) / max(n, 1)
    k1, b = 1.5, 0.75
    scores: list[float] = []
    for toks in doc_tokens:
        tf: dict[str, int] = defaultdict(int)
        for t in toks:
            tf[t] += 1
        score = 0.0
        dl = len(toks) or 1
        for qt in q_tokens:
            if qt not in tf:
                continue
            idf = max(0.0, (n - df[qt] + 0.5) / (df[qt] + 0.5))
            idf = __import__("math").log(1.0 + idf)
            freq = tf[qt]
            score += idf * (freq * (k1 + 1)) / (freq + k1 * (1 - b + b * dl / avgdl))
        scores.append(score)
    return scores


def _rrf_fuse(
    dense: list[RetrievedChunk],
    bm25_order: list[int],
    *,
    k: int = 60,
    limit: int = 20,
) -> list[RetrievedChunk]:
    scores: dict[str, float] = defaultdict(float)
    by_id = {c.id: c for c in dense}
    for rank, chunk in enumerate(dense):
        scores[chunk.id] += 1.0 / (k + rank + 1)
    for rank, idx in enumerate(bm25_order):
        if 0 <= idx < len(dense):
            scores[dense[idx].id] += 1.0 / (k + rank + 1)
    ordered = sorted(scores.keys(), key=lambda i: scores[i], reverse=True)
    return [by_id[i] for i in ordered[:limit] if i in by_id]


def _retrieve_chroma(query: str, region_code: str | None, top_k: int) -> list[RetrievedChunk]:
    from app.embeddings.embedder import get_embedder
    from app.vectorstore.chroma_store import get_chroma_store

    embedder = get_embedder()
    store = get_chroma_store()
    query_embedding = embedder.encode_query(query).tolist()
    where = _region_where(region_code)
    raw_results = store.query(query_embedding=query_embedding, n_results=top_k, where=where)
    ids = raw_results.get("ids", [[]])[0]
    documents = raw_results.get("documents", [[]])[0]
    metadatas = raw_results.get("metadatas", [[]])[0]
    distances = raw_results.get("distances", [[]])[0]
    chunks: list[RetrievedChunk] = []
    for chunk_id, document, metadata, distance in zip(ids, documents, metadatas, distances):
        chunks.append(
            RetrievedChunk(
                id=chunk_id,
                text=document,
                region_code=metadata.get("region_code", ""),
                section_number=metadata.get("section_number") or None,
                category=metadata.get("category") or None,
                distance=distance,
                tags=list(metadata.get("tags") or []),
                doc_type=str(metadata.get("doc_type") or ""),
            )
        )
    return chunks


def _rows_to_chunks(rows: list[dict]) -> list[RetrievedChunk]:
    return [
        RetrievedChunk(
            id=r["id"],
            text=r["text"],
            region_code=r["region_code"],
            section_number=r.get("section_number"),
            category=r.get("category"),
            distance=1.0 - float(r["score"]),
            tags=list((r.get("payload") or {}).get("tags") or []),
            doc_type=str((r.get("payload") or {}).get("doc_type") or ""),
        )
        for r in rows
    ]


def _retrieve_qdrant(
    query: str,
    region_code: str | None,
    top_k: int,
    *,
    doc_type: str | None = None,
) -> list[RetrievedChunk]:
    from app.embeddings.embedder import get_embedder
    from app.vectorstore.qdrant_store import get_qdrant_store

    embedder = get_embedder()
    store = get_qdrant_store()
    query_embedding = embedder.encode_query(query).tolist()
    region_iso = resolve_region_code(region_code) if region_code else None
    if region_iso == FEDERAL_CODE:
        rows = store.search(
            query_embedding,
            region_iso=FEDERAL_CODE,
            include_federal=True,
            top_k=top_k,
            doc_type=doc_type,
        )
    else:
        rows = store.search(
            query_embedding,
            region_iso=region_iso,
            include_federal=False,
            top_k=top_k,
            doc_type=doc_type,
        )
    return _rows_to_chunks(rows)


def retrieve(query: str, region_code: str | None = None, top_k: int = 5) -> list[RetrievedChunk]:
    return hybrid_retrieve(query, region_code=region_code, top_k=top_k)


def retrieve_curated(
    query: str,
    region_code: str | None = None,
    top_k: int = 8,
) -> list[RetrievedChunk]:
    """Dense search только по indexed CURATED (не JSONL-inject): similarity в подмножестве якорей."""
    settings = get_settings()
    if settings.vector_backend != "qdrant":
        return []
    return _retrieve_qdrant(query, region_code, top_k, doc_type="CURATED")


def hybrid_retrieve(
    query: str,
    region_code: str | None = None,
    top_k: int = 20,
) -> list[RetrievedChunk]:
    settings = get_settings()
    # шире dense-пул: точечные якоря часто на ранге 20–80 в полном корпусе
    fetch_k = max(top_k, 96)
    if settings.vector_backend == "qdrant":
        dense = _retrieve_qdrant(query, region_code, fetch_k)
    else:
        dense = _retrieve_chroma(query, region_code, fetch_k)
    if not dense:
        return []
    texts = [c.text for c in dense]
    bm25 = _bm25_scores(query, texts)
    order = sorted(range(len(bm25)), key=lambda i: bm25[i], reverse=True)
    return _rrf_fuse(dense, order, limit=top_k)
