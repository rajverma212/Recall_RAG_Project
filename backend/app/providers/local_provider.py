"""Deterministic, offline LLM provider.

Requires no API key or network. Used directly when ``LLM_PROVIDER=local`` and as
the automatic fallback whenever the selected cloud provider has no key — this is
what keeps the whole platform runnable in CI, tests, and offline demos. The
heuristics (extractive generation, lexical entailment) are intentionally simple;
they exist to keep every downstream stage exercisable, not to match LLM quality.
"""
from __future__ import annotations

import re
from collections.abc import Iterator

from app.providers.base import (
    BaseLLMProvider,
    CitationVerdict,
    GenerationResult,
    JudgeResult,
    VerdictStatus,
)

_SENT_RE = re.compile(r"(?<=[.!?])\s+")
_MARKER_RE = re.compile(r"\[(\d+)\]")
_WORD_RE = re.compile(r"\b\w+\b")

# Jaccard thresholds for the lexical entailment heuristic.
HIGH_THRESHOLD = 0.15
LOW_THRESHOLD = 0.05

_ABSTAIN = "I don't have enough information in the provided documents to answer that."


def _words(text: str) -> set[str]:
    return set(_WORD_RE.findall(text.lower()))


def _jaccard(a: set[str], b: set[str]) -> float:
    if not a and not b:
        return 0.0
    return len(a & b) / len(a | b)


def _split_sentences(text: str) -> list[str]:
    return [s.strip() for s in _SENT_RE.split(text) if s.strip()]


# Matches each "[n] (loc)\n<body>" passage inside a USER_TEMPLATE-wrapped
# message, capturing the body up to the next passage, the "Question:" line, or
# end of string. Robust to the "Context passages:" prefix / "Answer:" suffix.
_PASSAGE_RE = re.compile(
    r"\[(\d+)\][^\n]*\n(.*?)(?=\n\s*\[\d+\][^\n]*\n|\n\s*Question:|\Z)",
    re.DOTALL,
)


def _extractive_answer(user_message: str) -> str:
    """Compose an answer from the numbered ``[n] (loc)\\ntext`` context passages.

    Takes the first two sentences of the top 3 passages and tags them with the
    passage number, so citation extraction and verification have grounded
    ``[n]`` markers to act on — exactly as a grounded model would.
    """
    parts: list[str] = []
    for marker_str, body in _PASSAGE_RE.findall(user_message)[:3]:
        sents = _split_sentences(body.strip())
        if sents:
            parts.append(f"{' '.join(sents[:2])} [{int(marker_str)}]")
    return " ".join(parts) if parts else _ABSTAIN


class LocalProvider(BaseLLMProvider):
    name = "local"
    model = "local-deterministic"
    input_price_per_1m = 0.0
    output_price_per_1m = 0.0

    def generate(self, system_prompt: str, user_message: str) -> GenerationResult:
        answer = _extractive_answer(user_message)
        return GenerationResult(
            text=answer,
            input_tokens=len((system_prompt + " " + user_message).split()),
            output_tokens=len(answer.split()),
            model=self.model,
        )

    def generate_stream(
        self, system_prompt: str, user_message: str
    ) -> Iterator[str]:
        # No real token streaming offline — emit the full extractive answer once.
        yield _extractive_answer(user_message)

    def verify_citation(self, claim: str, evidence: str) -> CitationVerdict:
        claim_clean = _MARKER_RE.sub("", claim)
        overlap = _jaccard(_words(claim_clean), _words(evidence))
        if overlap >= HIGH_THRESHOLD:
            status: VerdictStatus = "supported"
        elif overlap >= LOW_THRESHOLD:
            status = "partially_supported"
        else:
            status = "unsupported"
        return CitationVerdict(
            status=status,
            rationale=f"Lexical overlap with cited passage(s): {overlap:.2f}",
        )

    def judge_answer(
        self, question: str, answer: str, reference: str | None
    ) -> JudgeResult:
        if reference is None:
            # No-answer case: correct iff the model abstained.
            abstained = "don't have enough information" in answer.lower()
            return JudgeResult(
                score=1.0 if abstained else 0.0,
                rationale="Abstention check (no-answer example).",
            )
        score = _jaccard(_words(answer), _words(reference))
        return JudgeResult(
            score=min(1.0, score * 2.0),  # rescale: lexical overlap is conservative
            rationale=f"Lexical overlap with reference: {score:.2f}",
        )

    def score_claim(self, claim: str, context: str) -> float:
        return _jaccard(_words(_MARKER_RE.sub("", claim)), _words(context))
