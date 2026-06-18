"""Cross-encoder reranker with a three-tier backend:

1. sentence-transformers CrossEncoder (BAAI/bge-reranker-base) — shipped default
2. FlagEmbedding FlagReranker (same model)  — optional, used only if installed
3. Lexical overlap (Jaccard on word sets)   — offline / CI fallback

CrossEncoder is the default because it loads the identical cross-encoder model
from prebuilt wheels with no native build step. FlagReranker is heavier (it pulls
`ir-datasets`/`zlib-state`, which need C build tooling) so it is *not* a hard
dependency; if the package is present it is preferred (fp16 on GPU), otherwise it
is skipped silently. The model is lazy-loaded once on first use (module
singleton). Scores are normalised to [0, 1] via sigmoid.
"""
from __future__ import annotations

import importlib.util
import math
import re
import time
from typing import Protocol

from app.core.config import settings
from app.core.logging import get_logger
from app.schemas.retrieval import RetrievedChunk

logger = get_logger(__name__)

_WORD_RE = re.compile(r"\b\w+\b")


def _sigmoid(x: float) -> float:
    return 1.0 / (1.0 + math.exp(-x))


def _tokenize(text: str) -> set[str]:
    return set(_WORD_RE.findall(text.lower()))


def _jaccard(a: set[str], b: set[str]) -> float:
    if not a and not b:
        return 0.0
    return len(a & b) / len(a | b)


# ---------------------------------------------------------------------------
# Reranker backend protocol
# ---------------------------------------------------------------------------


class _Backend(Protocol):
    def score(self, query: str, passages: list[str]) -> list[float]: ...


class _FlagRerankerBackend:
    def __init__(self, model_name: str, device: str) -> None:
        from FlagEmbedding import FlagReranker  # type: ignore

        self._model = FlagReranker(model_name, use_fp16=(device != "cpu"))
        logger.info(f"FlagReranker loaded: {model_name}")

    def score(self, query: str, passages: list[str]) -> list[float]:
        pairs = [[query, p] for p in passages]
        raw = self._model.compute_score(pairs)
        if isinstance(raw, float):
            raw = [raw]
        return [_sigmoid(s) for s in raw]


class _CrossEncoderBackend:
    def __init__(self, model_name: str, device: str) -> None:
        from sentence_transformers import CrossEncoder  # type: ignore

        self._model = CrossEncoder(model_name, device=device)
        logger.info(f"CrossEncoder loaded: {model_name}")

    def score(self, query: str, passages: list[str]) -> list[float]:
        pairs = [(query, p) for p in passages]
        raw = self._model.predict(pairs)
        # CrossEncoder may return logits; apply sigmoid to normalise
        return [_sigmoid(float(s)) for s in raw]


class _LexicalBackend:
    """Deterministic offline fallback — no model download required."""

    def score(self, query: str, passages: list[str]) -> list[float]:
        q_toks = _tokenize(query)
        return [_jaccard(q_toks, _tokenize(p)) for p in passages]


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

_backend: _Backend | None = None
_backend_name: str = "none"


def _get_backend() -> _Backend:
    global _backend, _backend_name
    if _backend is not None:
        return _backend

    model = settings.reranker_model
    device = settings.reranker_device

    # 1. Prefer FlagReranker only if the optional package is actually installed
    #    (avoids a noisy import error on the default, FlagEmbedding-free image).
    if importlib.util.find_spec("FlagEmbedding") is not None:
        try:
            _backend = _FlagRerankerBackend(model, device)
            _backend_name = "FlagReranker"
            return _backend
        except Exception as exc:
            logger.warning(f"FlagReranker present but failed to load ({exc})")

    # 2. sentence-transformers CrossEncoder — shipped default
    try:
        _backend = _CrossEncoderBackend(model, device)
        _backend_name = "CrossEncoder"
        return _backend
    except Exception as exc:
        logger.warning(f"CrossEncoder unavailable ({exc}), using lexical fallback")

    # 3. Lexical fallback
    _backend = _LexicalBackend()
    _backend_name = "Lexical"
    logger.info("Reranker: using offline lexical fallback")
    return _backend


# ---------------------------------------------------------------------------
# Public class
# ---------------------------------------------------------------------------


class Reranker:
    """Lazy-loading reranker; call .rerank() to score and sort candidates."""

    def rerank(
        self,
        query: str,
        candidates: list[RetrievedChunk],
        top_k: int | None = None,
    ) -> list[RetrievedChunk]:
        """Score candidates and return top_k sorted by descending score.

        Scores are in [0, 1] (sigmoid-normalised).
        """
        if top_k is None:
            top_k = settings.rerank_top_k
        if not candidates:
            return []

        t0 = time.perf_counter()
        backend = _get_backend()
        passages = [c.text for c in candidates]
        scores = backend.score(query, passages)
        elapsed = int((time.perf_counter() - t0) * 1000)

        # Pair candidates with scores, sort descending
        paired = sorted(zip(candidates, scores), key=lambda x: x[1], reverse=True)
        top = paired[:top_k]

        result: list[RetrievedChunk] = []
        for rank, (chunk, score) in enumerate(top, start=1):
            result.append(
                RetrievedChunk(
                    chunk_id=chunk.chunk_id,
                    document_id=chunk.document_id,
                    text=chunk.text,
                    score=score,
                    source_file=chunk.source_file,
                    page_number=chunk.page_number,
                    section_title=chunk.section_title,
                    heading_path=chunk.heading_path,
                    rank=rank,
                )
            )

        logger.debug(
            f"Reranker ({_backend_name}): {len(candidates)} → {len(result)} "
            f"in {elapsed}ms"
        )
        return result


# Module-level singleton
_reranker: Reranker | None = None


def get_reranker() -> Reranker:
    global _reranker
    if _reranker is None:
        _reranker = Reranker()
    return _reranker
