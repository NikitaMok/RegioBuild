from __future__ import annotations

from functools import lru_cache
from typing import Any

from app.core.config import get_settings


class ChromaStore:
    def __init__(self, persist_dir: str | None = None, collection_name: str | None = None) -> None:
        # chromadb тяжёлый — импорт только при реальном обращении к индексу
        import chromadb
        from chromadb.config import Settings as ChromaSettings

        settings = get_settings()
        self.persist_dir = persist_dir or settings.chroma_persist_dir
        self.collection_name = collection_name or settings.chroma_collection

        # иначе chromadb сыпет ошибками posthog в логи
        self._client = chromadb.PersistentClient(
            path=self.persist_dir,
            settings=ChromaSettings(anonymized_telemetry=False),
        )
        self._collection = self._client.get_or_create_collection(
            name=self.collection_name,
            metadata={"hnsw:space": "cosine"},
        )

    def reset(self) -> None:
        self._client.delete_collection(self.collection_name)
        self._collection = self._client.get_or_create_collection(
            name=self.collection_name,
            metadata={"hnsw:space": "cosine"},
        )

    def add(
        self,
        ids: list[str],
        embeddings: list[list[float]],
        documents: list[str],
        metadatas: list[dict[str, Any]],
    ) -> None:
        self._collection.add(ids=ids, embeddings=embeddings, documents=documents, metadatas=metadatas)

    def query(
        self,
        query_embedding: list[float],
        n_results: int = 5,
        where: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return self._collection.query(query_embeddings=[query_embedding], n_results=n_results, where=where)

    def count(self) -> int:
        return self._collection.count()

    def has_section(self, region_code: str, section_number: str) -> bool:
        """Есть ли в коллекции чанк с данным region_code + section_number."""
        try:
            result = self._collection.get(
                where={
                    "$and": [
                        {"region_code": region_code},
                        {"section_number": section_number},
                    ]
                },
                limit=1,
                include=["metadatas"],
            )
        except Exception:
            return False
        ids = result.get("ids") or []
        return len(ids) > 0


@lru_cache
def get_chroma_store() -> ChromaStore:
    return ChromaStore()
