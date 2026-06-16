"""Provider-agnostic LLM interface.

Every model interaction in the platform — answer generation, citation
verification, answer judging, and claim scoring — goes through a
``BaseLLMProvider``. No code outside ``app/providers/`` imports a vendor SDK or
references a model name, so swapping Anthropic ↔ OpenAI ↔ Local is a one-line
config change (``LLM_PROVIDER``).
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Literal

VerdictStatus = Literal["supported", "partially_supported", "unsupported"]


@dataclass
class GenerationResult:
    text: str
    input_tokens: int
    output_tokens: int
    model: str


@dataclass
class CitationVerdict:
    status: VerdictStatus
    rationale: str


@dataclass
class JudgeResult:
    score: float  # 0.0–1.0 answer correctness
    rationale: str


class BaseLLMProvider(ABC):
    """Contract implemented by Anthropic, OpenAI, and Local providers."""

    name: str = "base"
    model: str = ""
    # USD per 1M tokens — used by the cost tracker.
    input_price_per_1m: float = 0.0
    output_price_per_1m: float = 0.0

    @abstractmethod
    def generate(self, system_prompt: str, user_message: str) -> GenerationResult:
        """Produce a grounded answer for a fully-assembled user message."""

    @abstractmethod
    def generate_stream(
        self, system_prompt: str, user_message: str
    ) -> Iterator[str]:
        """Yield answer text deltas for streaming responses."""

    @abstractmethod
    def verify_citation(self, claim: str, evidence: str) -> CitationVerdict:
        """Decide whether ``evidence`` supports ``claim``."""

    @abstractmethod
    def judge_answer(
        self, question: str, answer: str, reference: str | None
    ) -> JudgeResult:
        """Score answer correctness against an optional reference (0–1)."""

    @abstractmethod
    def score_claim(self, claim: str, context: str) -> float:
        """Return a 0–1 support score for ``claim`` given ``context`` (faithfulness)."""
