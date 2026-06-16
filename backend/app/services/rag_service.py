"""RAGService — the top-level orchestrator for the /v1/ask endpoint.

Flow (ask):
    1. Resolve system prompt (DB PromptVersion → fallback DEFAULT_SYSTEM_PROMPT)
    2. HybridRetriever.retrieve(db, question)  → chunks + trace + embedding_tokens
    3. format_context(chunks)
    4. Generator.generate(context, question, system_prompt)  → answer + tokens
    5. extract_citations(answer, chunks)
    6. verify(answer, citations)
    7. compute_confidence(...)
    8. compute cost_usd from token counts + pricing settings
    9. persist QueryLog row (best-effort, no exception raised)
   10. return AskResponse

Flow (ask_stream):
    1-3. Same resolution + retrieval (synchronous)
    4.   Stream generation tokens → yield {"type":"token","text":...}
    5-9. Post-generation processing
   10.  Yield {"type":"done","data": <AskResponse as dict>}
"""
from __future__ import annotations

import time
import uuid
from typing import TYPE_CHECKING, Generator

from app.core.config import settings
from app.core.logging import get_logger
from app.generation.generator import get_generator
from app.generation.prompts import DEFAULT_SYSTEM_PROMPT, format_context
from app.retrieval.pipeline import HybridRetriever
from app.schemas.ask import AskRequest, AskResponse
from app.verification.citations import extract_citations
from app.verification.confidence import compute_confidence
from app.verification.verifier import verify

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _resolve_system_prompt(db: "Session", prompt_version: str | None) -> tuple[str, str]:
    """Return (system_prompt_text, version_string).

    Resolution order:
        1. If prompt_version given, look up that PromptVersion row.
        2. Look for the active PromptVersion (is_active=True).
        3. Fall back to DEFAULT_SYSTEM_PROMPT with settings.prompt_version.
    """
    try:
        from sqlalchemy import select

        from app.models.experiment import PromptVersion

        if prompt_version:
            row = db.execute(
                select(PromptVersion).where(PromptVersion.version == prompt_version)
            ).scalar_one_or_none()
            if row:
                return row.system_prompt, row.version

        # Active version
        row = db.execute(
            select(PromptVersion).where(PromptVersion.is_active == True)  # noqa: E712
        ).scalar_one_or_none()
        if row:
            return row.system_prompt, row.version
    except Exception as exc:
        logger.warning(f"Could not resolve PromptVersion from DB: {exc}")

    return DEFAULT_SYSTEM_PROMPT, settings.prompt_version


def _persist_query_log(
    db: "Session",
    *,
    query_id: str,
    question: str,
    answer: str,
    chunk_ids: list[str],
    citations_data: list[dict],
    confidence_breakdown,
    citation_accuracy: float,
    prompt_version: str | None,
    experiment_id: str | None,
    embedding_tokens: int,
    input_tokens: int,
    output_tokens: int,
    cost_usd: float,
    latency_ms: int,
) -> None:
    """Persist a QueryLog row; silently swallowed on any error."""
    try:
        from app.models.query_log import QueryLog

        log = QueryLog(
            id=query_id,
            question=question,
            answer=answer,
            retrieved_chunk_ids=chunk_ids,
            citations=[c for c in citations_data],
            confidence=confidence_breakdown.score,
            citation_accuracy=citation_accuracy,
            retrieval_confidence=confidence_breakdown.retrieval_confidence,
            reranker_confidence=confidence_breakdown.reranker_confidence,
            prompt_version=prompt_version,
            experiment_id=experiment_id,
            embedding_tokens=embedding_tokens,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost_usd=cost_usd,
            latency_ms=latency_ms,
        )
        db.add(log)
        db.commit()
        logger.debug(f"QueryLog persisted: {query_id}")
    except Exception as exc:
        logger.warning(f"QueryLog persist failed (non-fatal): {exc}")
        try:
            db.rollback()
        except Exception:
            pass


def _compute_cost(
    embedding_tokens: int, input_tokens: int, output_tokens: int
) -> float:
    return (
        embedding_tokens / 1_000_000 * settings.embedding_price_per_1m
        + input_tokens / 1_000_000 * settings.generation_input_price_per_1m
        + output_tokens / 1_000_000 * settings.generation_output_price_per_1m
    )


# ---------------------------------------------------------------------------
# RAGService
# ---------------------------------------------------------------------------


class RAGService:
    """Top-level ask/ask_stream orchestrator."""

    def __init__(self) -> None:
        self._retriever = HybridRetriever()
        self._generator = get_generator()

    # ------------------------------------------------------------------ #
    # Non-streaming ask                                                    #
    # ------------------------------------------------------------------ #

    def ask(self, db: "Session", req: AskRequest) -> AskResponse:
        """Run the full RAG pipeline and return an AskResponse."""
        t_start = time.perf_counter()
        query_id = str(uuid.uuid4())

        # 1. Resolve system prompt
        system_prompt, resolved_version = _resolve_system_prompt(db, req.prompt_version)

        # 2. Retrieve
        chunks, trace, embedding_tokens = self._retriever.retrieve(db, req.question)

        # 3. Format context
        context_dicts = [
            {
                "text": c.text,
                "source_file": c.source_file,
                "page_number": c.page_number,
            }
            for c in chunks
        ]
        context = format_context(context_dicts)

        # 4. Generate
        answer, input_tokens, output_tokens = self._generator.generate(
            context=context,
            question=req.question,
            system_prompt=system_prompt,
        )

        # 5. Extract citations
        citations = extract_citations(answer, chunks)

        # 6. Verify
        verifications, citation_accuracy = verify(answer, citations)

        # 7. Confidence
        retrieval_scores = [c.score for c in trace.rrf.results]
        reranker_scores = [c.score for c in chunks]
        confidence = compute_confidence(
            retrieval_scores=retrieval_scores,
            reranker_scores=reranker_scores,
            citations=citations,
            verifications=verifications,
            num_context=len(chunks),
            answer=answer,
            citation_accuracy=citation_accuracy,
        )

        # 8. Cost + latency
        cost_usd = _compute_cost(embedding_tokens, input_tokens, output_tokens)
        latency_ms = int((time.perf_counter() - t_start) * 1000)

        # Handle low-confidence + empty retrieval: keep the answer but it'll
        # be the "not enough info" extractive text already.
        if confidence.score < settings.min_confidence_to_answer and not chunks:
            logger.info(
                f"Low confidence ({confidence.score:.1f}) with no retrieved chunks; "
                "returning grounded 'not enough info' answer"
            )

        # 9. Persist
        _persist_query_log(
            db,
            query_id=query_id,
            question=req.question,
            answer=answer,
            chunk_ids=[c.chunk_id for c in chunks],
            citations_data=[c.model_dump() for c in citations],
            confidence_breakdown=confidence,
            citation_accuracy=citation_accuracy,
            prompt_version=resolved_version,
            experiment_id=req.experiment_id,
            embedding_tokens=embedding_tokens,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost_usd=cost_usd,
            latency_ms=latency_ms,
        )

        # 10. Build response
        return AskResponse(
            query_id=query_id,
            question=req.question,
            answer=answer,
            citations=citations,
            verifications=verifications,
            confidence=confidence,
            trace=trace if req.include_trace else None,
            cost_usd=round(cost_usd, 8),
            latency_ms=latency_ms,
            prompt_version=resolved_version,
        )

    # ------------------------------------------------------------------ #
    # Streaming ask                                                        #
    # ------------------------------------------------------------------ #

    def ask_stream(
        self, db: "Session", req: AskRequest
    ) -> Generator[dict, None, None]:
        """Stream the answer token-by-token, then emit a final done event.

        Yields:
            {"type": "token", "text": <delta>}   — during generation
            {"type": "done",  "data": <AskResponse dict>}  — at the end
        """
        t_start = time.perf_counter()
        query_id = str(uuid.uuid4())

        # 1. Resolve system prompt
        system_prompt, resolved_version = _resolve_system_prompt(db, req.prompt_version)

        # 2. Retrieve
        chunks, trace, embedding_tokens = self._retriever.retrieve(db, req.question)

        # 3. Format context
        context_dicts = [
            {
                "text": c.text,
                "source_file": c.source_file,
                "page_number": c.page_number,
            }
            for c in chunks
        ]
        context = format_context(context_dicts)

        # 4. Stream generation
        answer_parts: list[str] = []
        for delta in self._generator.stream(
            context=context,
            question=req.question,
            system_prompt=system_prompt,
        ):
            answer_parts.append(delta)
            yield {"type": "token", "text": delta}

        answer = "".join(answer_parts)

        # Estimate tokens for offline mode (stream doesn't return usage)
        input_tokens = len((system_prompt + " " + context + " " + req.question).split())
        output_tokens = len(answer.split())

        # 5. Extract citations
        citations = extract_citations(answer, chunks)

        # 6. Verify
        verifications, citation_accuracy = verify(answer, citations)

        # 7. Confidence
        retrieval_scores = [c.score for c in trace.rrf.results]
        reranker_scores = [c.score for c in chunks]
        confidence = compute_confidence(
            retrieval_scores=retrieval_scores,
            reranker_scores=reranker_scores,
            citations=citations,
            verifications=verifications,
            num_context=len(chunks),
            answer=answer,
            citation_accuracy=citation_accuracy,
        )

        # 8. Cost + latency
        cost_usd = _compute_cost(embedding_tokens, input_tokens, output_tokens)
        latency_ms = int((time.perf_counter() - t_start) * 1000)

        # 9. Persist
        _persist_query_log(
            db,
            query_id=query_id,
            question=req.question,
            answer=answer,
            chunk_ids=[c.chunk_id for c in chunks],
            citations_data=[c.model_dump() for c in citations],
            confidence_breakdown=confidence,
            citation_accuracy=citation_accuracy,
            prompt_version=resolved_version,
            experiment_id=req.experiment_id,
            embedding_tokens=embedding_tokens,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost_usd=cost_usd,
            latency_ms=latency_ms,
        )

        # 10. Final done event
        response = AskResponse(
            query_id=query_id,
            question=req.question,
            answer=answer,
            citations=citations,
            verifications=verifications,
            confidence=confidence,
            trace=trace if req.include_trace else None,
            cost_usd=round(cost_usd, 8),
            latency_ms=latency_ms,
            prompt_version=resolved_version,
        )
        yield {"type": "done", "data": response.model_dump()}


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

_rag_service: RAGService | None = None


def get_rag_service() -> RAGService:
    global _rag_service
    if _rag_service is None:
        _rag_service = RAGService()
    return _rag_service
