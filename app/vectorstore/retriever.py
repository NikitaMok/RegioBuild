from __future__ import annotations

from app.vectorstore.types import RetrievedChunk

__all__ = ["RetrievedChunk", "retrieve"]


def retrieve(query: str, region_code: str | None = None, top_k: int = 5) -> list[RetrievedChunk]:
    from app.embeddings.embedder import get_embedder
    from app.vectorstore.chroma_store import get_chroma_store

    embedder = get_embedder()
    store = get_chroma_store()

    query_embedding = embedder.encode_one(query).tolist()
    where = {"region_code": region_code} if region_code else None
    raw_results = store.query(query_embedding=query_embedding, n_results=top_k, where=where)

    ids = raw_results.get("ids", [[]])[0]
    documents = raw_results.get("documents", [[]])[0]
    metadatas = raw_results.get("metadatas", [[]])[0]
    distances = raw_results.get("distances", [[]])[0]

    chunks = []
    for chunk_id, document, metadata, distance in zip(ids, documents, metadatas, distances):
        chunks.append(
            RetrievedChunk(
                id=chunk_id,
                text=document,
                region_code=metadata.get("region_code", ""),
                section_number=metadata.get("section_number") or None,
                category=metadata.get("category") or None,
                distance=distance,
            )
        )
    return chunks
