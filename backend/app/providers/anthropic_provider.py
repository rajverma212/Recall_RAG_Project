"""Anthropic provider — the platform default.

Uses the official ``anthropic`` SDK (Messages API). Notes:
- ``temperature`` is intentionally omitted. Sonnet 4.6 accepts it, but Opus 4.8 /
  Fable 5 reject sampling params, so leaving it off keeps this provider valid if
  ``ANTHROPIC_MODEL`` is pointed at a newer model. Determinism is enforced by the
  strict grounded system prompt instead.
- Adaptive thinking (``ANTHROPIC_USE_THINKING``) is available for the reasoning
  calls (verify/judge/score); off by default to bound per-claim latency/cost.
"""
from __future__ import annotations

from collections.abc import Iterator

from app.core.config import settings
from app.core.logging import get_logger
from app.providers.base import (
    BaseLLMProvider,
    CitationVerdict,
    GenerationResult,
    JudgeResult,
    VerdictStatus,
)

logger = get_logger(__name__)

_STATUS_MAP: dict[str, VerdictStatus] = {
    "SUPPORTED": "supported",
    "PARTIALLY_SUPPORTED": "partially_supported",
    "UNSUPPORTED": "unsupported",
}


class AnthropicProvider(BaseLLMProvider):
    name = "anthropic"

    def __init__(self) -> None:
        import anthropic  # imported here so the package is optional offline

        self._client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
        self.model = settings.anthropic_model
        self._judge_model = settings.anthropic_judge_model or settings.anthropic_model
        self.input_price_per_1m = settings.anthropic_input_price_per_1m
        self.output_price_per_1m = settings.anthropic_output_price_per_1m

    # ------------------------------------------------------------------ #
    # Internal helpers                                                     #
    # ------------------------------------------------------------------ #

    def _text_of(self, message) -> str:
        return "".join(b.text for b in message.content if b.type == "text").strip()

    def _judge_call(self, prompt: str, max_tokens: int = 256) -> str:
        kwargs: dict = {
            "model": self._judge_model,
            "max_tokens": max_tokens,
            "messages": [{"role": "user", "content": prompt}],
        }
        if settings.anthropic_use_thinking:
            # Extended thinking: the Messages API expects an explicit token
            # budget. `max_tokens` must exceed `budget_tokens`, so bump both.
            budget = 1024
            kwargs["thinking"] = {"type": "enabled", "budget_tokens": budget}
            kwargs["max_tokens"] = max(max_tokens, budget + 512)
        resp = self._client.messages.create(**kwargs)
        return self._text_of(resp)

    # ------------------------------------------------------------------ #
    # Generation                                                           #
    # ------------------------------------------------------------------ #

    def generate(self, system_prompt: str, user_message: str) -> GenerationResult:
        resp = self._client.messages.create(
            model=self.model,
            max_tokens=settings.generation_max_tokens,
            system=system_prompt,
            messages=[{"role": "user", "content": user_message}],
        )
        return GenerationResult(
            text=self._text_of(resp),
            input_tokens=resp.usage.input_tokens,
            output_tokens=resp.usage.output_tokens,
            model=self.model,
        )

    def generate_stream(
        self, system_prompt: str, user_message: str
    ) -> Iterator[str]:
        with self._client.messages.stream(
            model=self.model,
            max_tokens=settings.generation_max_tokens,
            system=system_prompt,
            messages=[{"role": "user", "content": user_message}],
        ) as stream:
            yield from stream.text_stream

    # ------------------------------------------------------------------ #
    # Verification / judging / scoring                                     #
    # ------------------------------------------------------------------ #

    def verify_citation(self, claim: str, evidence: str) -> CitationVerdict:
        prompt = (
            "Does the EVIDENCE support the CLAIM? Use only the evidence.\n"
            f"CLAIM: {claim}\nEVIDENCE: {evidence}\n\n"
            "Reply with exactly one line: SUPPORTED, PARTIALLY_SUPPORTED, or "
            "UNSUPPORTED, then a pipe and a one-sentence rationale.\n"
            "Example: SUPPORTED | The evidence directly states X."
        )
        raw = self._judge_call(prompt, max_tokens=120)
        head, _, rationale = raw.partition("|")
        status = _STATUS_MAP.get(head.strip().upper(), "unsupported")
        return CitationVerdict(status=status, rationale=(rationale.strip() or raw))

    def judge_answer(
        self, question: str, answer: str, reference: str | None
    ) -> JudgeResult:
        ref_block = (
            f"REFERENCE ANSWER: {reference}\n"
            if reference is not None
            else "There is no correct answer; a correct response abstains/says it "
            "cannot answer from the documents.\n"
        )
        prompt = (
            "Score how correct the ANSWER is, 0 to 100.\n"
            f"QUESTION: {question}\n{ref_block}ANSWER: {answer}\n\n"
            "Reply with one line: <score 0-100> | <one-sentence rationale>."
        )
        raw = self._judge_call(prompt, max_tokens=120)
        head, _, rationale = raw.partition("|")
        return JudgeResult(
            score=_parse_0_100(head),
            rationale=(rationale.strip() or raw),
        )

    def score_claim(self, claim: str, context: str) -> float:
        prompt = (
            "On a scale of 0 to 100, how well is the CLAIM supported by the "
            "CONTEXT? Reply with only the number.\n"
            f"CLAIM: {claim}\nCONTEXT: {context}"
        )
        return _parse_0_100(self._judge_call(prompt, max_tokens=20))


def _parse_0_100(text: str) -> float:
    import re

    m = re.search(r"\d+(\.\d+)?", text)
    if not m:
        return 0.0
    return max(0.0, min(1.0, float(m.group()) / 100.0))
