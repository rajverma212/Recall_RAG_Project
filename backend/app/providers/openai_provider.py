"""OpenAI provider — chat completions implementation of BaseLLMProvider."""
from __future__ import annotations

import re
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


class OpenAIProvider(BaseLLMProvider):
    name = "openai"

    def __init__(self) -> None:
        from openai import OpenAI

        self._client = OpenAI(api_key=settings.openai_api_key)
        self.model = settings.openai_model
        self.input_price_per_1m = settings.openai_input_price_per_1m
        self.output_price_per_1m = settings.openai_output_price_per_1m

    def _chat(self, messages: list[dict], max_tokens: int) -> str:
        resp = self._client.chat.completions.create(
            model=self.model,
            temperature=settings.generation_temperature,
            messages=messages,
            max_tokens=max_tokens,
        )
        return (resp.choices[0].message.content or "").strip()

    def generate(self, system_prompt: str, user_message: str) -> GenerationResult:
        resp = self._client.chat.completions.create(
            model=self.model,
            temperature=settings.generation_temperature,
            max_tokens=settings.generation_max_tokens,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ],
        )
        usage = resp.usage
        return GenerationResult(
            text=(resp.choices[0].message.content or ""),
            input_tokens=usage.prompt_tokens,
            output_tokens=usage.completion_tokens,
            model=self.model,
        )

    def generate_stream(
        self, system_prompt: str, user_message: str
    ) -> Iterator[str]:
        stream = self._client.chat.completions.create(
            model=self.model,
            temperature=settings.generation_temperature,
            max_tokens=settings.generation_max_tokens,
            stream=True,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ],
        )
        for chunk in stream:
            delta = chunk.choices[0].delta.content
            if delta:
                yield delta

    def verify_citation(self, claim: str, evidence: str) -> CitationVerdict:
        prompt = (
            "Does the EVIDENCE support the CLAIM?\n"
            f"CLAIM: {claim}\nEVIDENCE: {evidence}\n\n"
            "Reply with one line: SUPPORTED, PARTIALLY_SUPPORTED, or UNSUPPORTED, "
            "then a pipe and a one-sentence rationale."
        )
        raw = self._chat([{"role": "user", "content": prompt}], max_tokens=80)
        head, _, rationale = raw.partition("|")
        status = _STATUS_MAP.get(head.strip().upper(), "unsupported")
        return CitationVerdict(status=status, rationale=(rationale.strip() or raw))

    def judge_answer(
        self, question: str, answer: str, reference: str | None
    ) -> JudgeResult:
        ref_block = (
            f"REFERENCE ANSWER: {reference}\n"
            if reference is not None
            else "There is no correct answer; a correct response abstains.\n"
        )
        prompt = (
            "Score how correct the ANSWER is, 0 to 100.\n"
            f"QUESTION: {question}\n{ref_block}ANSWER: {answer}\n\n"
            "Reply: <score 0-100> | <one-sentence rationale>."
        )
        raw = self._chat([{"role": "user", "content": prompt}], max_tokens=80)
        head, _, rationale = raw.partition("|")
        return JudgeResult(score=_parse_0_100(head), rationale=(rationale.strip() or raw))

    def score_claim(self, claim: str, context: str) -> float:
        prompt = (
            "On a scale of 0 to 100, how well is the CLAIM supported by the "
            "CONTEXT? Reply with only the number.\n"
            f"CLAIM: {claim}\nCONTEXT: {context}"
        )
        return _parse_0_100(self._chat([{"role": "user", "content": prompt}], 10))


def _parse_0_100(text: str) -> float:
    m = re.search(r"\d+(\.\d+)?", text)
    if not m:
        return 0.0
    return max(0.0, min(1.0, float(m.group()) / 100.0))
