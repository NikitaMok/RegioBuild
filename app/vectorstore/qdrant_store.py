"""Qdrant vector store: dense + payload filters (region OR federal)."""

from __future__ import annotations

from functools import lru_cache
from typing import Any

from loguru import logger

from app.core.config import get_settings

# размерность MiniLM; e5-large = 1024 — задаётся при создании коллекции
_MINILM_DIM = 384
_E5_LARGE_DIM = 1024


def _vector_size_for_model(model_name: str) -> int:
    lower = (model_name or "").lower()
    if "e5-large" in lower or "e5_large" in lower:
        return _E5_LARGE_DIM
    if "minilm" in lower:
        return _MINILM_DIM
    return _MINILM_DIM


class QdrantStore:
    def __init__(self) -> None:
        from qdrant_client import QdrantClient
        from qdrant_client.http import models as qm

        self._qm = qm
        settings = get_settings()
        self.collection = settings.qdrant_collection
        kwargs: dict[str, Any] = {"url": settings.qdrant_url}
        if settings.qdrant_api_key:
            kwargs["api_key"] = settings.qdrant_api_key
        self._client = QdrantClient(**kwargs)
        self._vector_size = _vector_size_for_model(
            settings.embedding_model_enterprise
            if settings.deploy_profile == "enterprise"
            else settings.embedding_model_name
        )
        self._ensure_collection()

    def _ensure_collection(self) -> None:
        from qdrant_client.http import models as qm

        names = {c.name for c in self._client.get_collections().collections}
        if self.collection not in names:
            self._client.create_collection(
                collection_name=self.collection,
                vectors_config=qm.VectorParams(size=self._vector_size, distance=qm.Distance.COSINE),
            )
            logger.info(f"создана коллекция Qdrant «{self.collection}» dim={self._vector_size}")
        self._ensure_payload_indexes()

    def _ensure_payload_indexes(self) -> None:
        """Qdrant Cloud требует индекс для filter; на существующей коллекции тоже."""
        from qdrant_client.http import models as qm

        specs: list[tuple[str, Any]] = [
            ("region_iso", qm.PayloadSchemaType.KEYWORD),
            ("regulatory_level", qm.PayloadSchemaType.KEYWORD),
            ("doc_type", qm.PayloadSchemaType.KEYWORD),
            ("clause_number", qm.PayloadSchemaType.KEYWORD),
            ("is_active", qm.PayloadSchemaType.BOOL),
        ]
        for field_name, schema in specs:
            try:
                self._client.create_payload_index(
                    collection_name=self.collection,
                    field_name=field_name,
                    field_schema=schema,
                )
                logger.info(f"payload index: {field_name}={schema}")
            except Exception as exc:  # noqa: BLE001 — уже есть / гонка
                msg = str(exc).lower()
                if "already" in msg or "exists" in msg or "409" in msg:
                    continue
                logger.warning(f"не удалось создать index {field_name}: {exc}")

    def reset(self) -> None:
        names = {c.name for c in self._client.get_collections().collections}
        if self.collection in names:
            self._client.delete_collection(self.collection)
        self._ensure_collection()

    def upsert(
        self,
        ids: list[str],
        embeddings: list[list[float]],
        payloads: list[dict[str, Any]],
    ) -> None:
        from qdrant_client.http import models as qm

        points = [
            qm.PointStruct(id=self._point_id(pid), vector=vec, payload={**pay, "chunk_id": pid})
            for pid, vec, pay in zip(ids, embeddings, payloads)
        ]
        self._client.upsert(collection_name=self.collection, points=points)

    @staticmethod
    def _point_id(chunk_id: str) -> str:
        """Qdrant принимает UUID или unsigned int — стабильный UUID5 из chunk_id."""
        import uuid

        return str(uuid.uuid5(uuid.NAMESPACE_URL, chunk_id))

    def search(
        self,
        query_embedding: list[float],
        *,
        region_iso: str | None = None,
        include_federal: bool = True,
        top_k: int = 20,
    ) -> list[dict[str, Any]]:
        from qdrant_client.http import models as qm

        must_active = qm.FieldCondition(key="is_active", match=qm.MatchValue(value=True))
        should: list = []
        if region_iso and region_iso != "RU-FED":
            should.append(
                qm.FieldCondition(key="region_iso", match=qm.MatchValue(value=region_iso))
            )
        if include_federal or region_iso == "RU-FED":
            should.append(
                qm.FieldCondition(
                    key="regulatory_level", match=qm.MatchValue(value="federal")
                )
            )
        if not should:
            query_filter = qm.Filter(must=[must_active])
        else:
            query_filter = qm.Filter(
                must=[
                    must_active,
                    qm.Filter(should=should),
                ]
            )

        hits = self._client.search(
            collection_name=self.collection,
            query_vector=query_embedding,
            query_filter=query_filter,
            limit=top_k,
            with_payload=True,
        )
        rows: list[dict[str, Any]] = []
        for hit in hits:
            payload = dict(hit.payload or {})
            rows.append(
                {
                    "id": payload.get("chunk_id") or str(hit.id),
                    "score": float(hit.score),
                    "text": payload.get("text") or "",
                    "region_code": payload.get("region_iso") or "",
                    "section_number": payload.get("clause_number"),
                    "category": payload.get("category"),
                    "payload": payload,
                }
            )
        return rows

    def count(self) -> int:
        info = self._client.get_collection(self.collection)
        return int(info.points_count or 0)


@lru_cache
def get_qdrant_store() -> QdrantStore:
    return QdrantStore()
