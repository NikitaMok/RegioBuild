from __future__ import annotations

from functools import lru_cache
from typing import Any, Literal

import numpy as np
from loguru import logger

from app.core.config import get_settings

_FALLBACK_EMBEDDING_MODEL = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
EmbeddingBackend = Literal["fastembed", "sentence_transformers"]


def resolve_embedding_backend() -> EmbeddingBackend:
    """bothost-demo → fastembed (ONNX, низкий RAM); enterprise по умолчанию — torch ST."""
    settings = get_settings()
    explicit = (settings.embedding_backend or "").strip().lower()
    if explicit in {"fastembed", "sentence_transformers"}:
        return explicit  # type: ignore[return-value]
    if settings.deploy_profile == "enterprise":
        return "sentence_transformers"
    return "fastembed"


def resolve_embedding_model_name() -> str:
    settings = get_settings()
    if settings.deploy_profile == "enterprise":
        return settings.embedding_model_enterprise
    return settings.embedding_model_name


def _configure_ort_low_memory() -> None:
    """Сжимает RSS onnxruntime: без CPU arena и с одним потоком."""
    try:
        import onnxruntime as ort
    except ImportError:
        return
    if getattr(ort, "_regiobuild_low_mem", False):
        return

    original = ort.InferenceSession

    def _session(path_or_bytes, sess_options=None, providers=None, **kwargs):  # noqa: ANN001
        options = sess_options or ort.SessionOptions()
        options.enable_cpu_mem_arena = False
        options.enable_mem_pattern = False
        options.intra_op_num_threads = 1
        options.inter_op_num_threads = 1
        return original(path_or_bytes, sess_options=options, providers=providers, **kwargs)

    ort.InferenceSession = _session  # type: ignore[misc, assignment]
    ort._regiobuild_low_mem = True  # type: ignore[attr-defined]


class Embedder:
    """Единый контракт encode_* для индексации и retrieval.

    Backend:
    - fastembed — прод Bothost / demo (ONNX, без PyTorch в RAM)
    - sentence_transformers — enterprise / локальные эксперименты (e5-large и т.п.)
    """

    def __init__(
        self,
        model_name: str | None = None,
        backend: EmbeddingBackend | None = None,
    ) -> None:
        self.backend: EmbeddingBackend = backend or resolve_embedding_backend()
        self.model_name = model_name or resolve_embedding_model_name()
        self._model: Any
        if self.backend == "fastembed":
            self._init_fastembed()
        else:
            self._init_sentence_transformers()
        logger.info(f"embedder ready: backend={self.backend} model={self.model_name}")

    def _init_fastembed(self) -> None:
        import warnings

        from fastembed import TextEmbedding

        _configure_ort_low_memory()
        try:
            with warnings.catch_warnings():
                warnings.filterwarnings(
                    "ignore",
                    message=r".*mean pooling instead of CLS.*",
                    category=UserWarning,
                )
                self._model = TextEmbedding(model_name=self.model_name, threads=1)
        except Exception as exc:
            if self.model_name == _FALLBACK_EMBEDDING_MODEL:
                raise
            logger.warning(
                f"fastembed «{self.model_name}» недоступен ({exc}); "
                f"fallback → {_FALLBACK_EMBEDDING_MODEL}"
            )
            self.model_name = _FALLBACK_EMBEDDING_MODEL
            with warnings.catch_warnings():
                warnings.filterwarnings(
                    "ignore",
                    message=r".*mean pooling instead of CLS.*",
                    category=UserWarning,
                )
                self._model = TextEmbedding(model_name=self.model_name, threads=1)

    def _init_sentence_transformers(self) -> None:
        try:
            from sentence_transformers import SentenceTransformer
        except ModuleNotFoundError as exc:
            raise ModuleNotFoundError(
                "sentence-transformers не установлен. Для enterprise/torch-стека: "
                "pip install -r requirements-enterprise-embeddings.txt"
            ) from exc

        try:
            self._model = SentenceTransformer(self.model_name)
        except Exception as exc:
            if self.model_name == _FALLBACK_EMBEDDING_MODEL:
                raise
            logger.warning(
                f"не удалось загрузить embedding «{self.model_name}»: {exc}; "
                f"fallback → {_FALLBACK_EMBEDDING_MODEL}"
            )
            self.model_name = _FALLBACK_EMBEDDING_MODEL
            self._model = SentenceTransformer(self.model_name)

    def encode(self, texts: list[str], batch_size: int = 32, show_progress: bool = False) -> np.ndarray:
        if not texts:
            return np.zeros((0, 0), dtype=np.float32)
        if self.backend == "fastembed":
            vectors = list(self._model.embed(texts, batch_size=batch_size))
            arr = np.asarray(vectors, dtype=np.float32)
            norms = np.linalg.norm(arr, axis=1, keepdims=True)
            norms = np.maximum(norms, 1e-12)
            return arr / norms
        return self._model.encode(
            texts,
            batch_size=batch_size,
            show_progress_bar=show_progress,
            normalize_embeddings=True,
            convert_to_numpy=True,
        )

    def _is_e5(self) -> bool:
        return "e5" in (self.model_name or "").lower()

    def encode_passages(self, texts: list[str], batch_size: int = 32, show_progress: bool = False) -> np.ndarray:
        if self._is_e5():
            texts = [f"passage: {t}" for t in texts]
        return self.encode(texts, batch_size=batch_size, show_progress=show_progress)

    def encode_query(self, text: str) -> np.ndarray:
        if self._is_e5():
            text = f"query: {text}"
        return self.encode([text])[0]

    def encode_one(self, text: str) -> np.ndarray:
        return self.encode_query(text)


@lru_cache
def get_embedder() -> Embedder:
    return Embedder(
        model_name=resolve_embedding_model_name(),
        backend=resolve_embedding_backend(),
    )
