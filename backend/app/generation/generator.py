"""LLM generation with extractive offline fallback.

Primary path: OpenAI chat completion (settings.generation_model).
Fallback (no OPENAI_API_KEY): deterministic extractive summariser that
  composes an answer from the top context chunks with [n] citation markers,
  so the entire pipeline works offline with no network access.
"""
from __future__ import annotations

import re
from typing import Generator

from app.core.config import settings
from app.core.logging import get_logger
from app.generation.prompts import DEFAULT_SYSTEM_PROMPT, USER_TEMPLATE

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Extractive fallback
# ---------------------------------------------------------------------------

_SENT_RE = re.compile(r"(?<=[.!?])\s+")


def _split_sentences(text: str) -> list[str]:
    return [s.strip() for s in _SENT_RE.split(text) if s.strip()]


def _extractive_answer(context: str, question: str) -> str:
    """Build a short grounded answer by picking sentences from top passages.

    Each context passage is prefixed with [n]; we pick the first 2 sentences
    from each passage and label them with the passage number.
    """
    # Parse [n] (loc)\ntext blocks from format_context output
    blocks = re.split(r"\n\n(?=\[\d+\])", context)
    if not blocks:
        return "I don't have enough information in the provided documents to answer that."

    parts: list[str] = []
    for block in blocks[:3]:  # top 3 passages
        m = re.match(r"\[(\d+)\]", block)
        if not m:
            continue
        marker = int(m.group(1))
        # Extract text portion (after the header line)
        lines = block.split("\n", 1)
        text = lines[1].strip() if len(lines) > 1 else ""
        sentences = _split_sentences(text)
        if sentences:
            extract = " ".join(sentences[:2])
            parts.append(f"{extract} [{marker}]")

    if not parts:
        return "I don't have enough information in the provided documents to answer that."

    answer = " ".join(parts)
    return answer


# ---------------------------------------------------------------------------
# OpenAI generator
# ---------------------------------------------------------------------------


def _openai_generate(system_prompt: str, user_message: str) -> tuple[str, int, int]:
    """Call OpenAI chat completion. Returns (answer, input_tokens, output_tokens)."""
    from openai import OpenAI

    client = OpenAI(api_key=settings.openai_api_key)
    response = client.chat.completions.create(
        model=settings.generation_model,
        temperature=settings.generation_temperature,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ],
    )
    answer = response.choices[0].message.content or ""
    usage = response.usage
    return answer, usage.prompt_tokens, usage.completion_tokens


def _openai_stream(
    system_prompt: str, user_message: str
) -> Generator[str, None, None]:
    """Stream tokens from OpenAI chat completion."""
    from openai import OpenAI

    client = OpenAI(api_key=settings.openai_api_key)
    stream = client.chat.completions.create(
        model=settings.generation_model,
        temperature=settings.generation_temperature,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ],
        stream=True,
    )
    for chunk in stream:
        delta = chunk.choices[0].delta.content
        if delta:
            yield delta


# ---------------------------------------------------------------------------
# Public Generator class
# ---------------------------------------------------------------------------


class Generator:
    """Generates an answer given a system prompt + formatted context + question."""

    def _build_user_message(self, context: str, question: str) -> str:
        return USER_TEMPLATE.format(context=context, question=question)

    def generate(
        self,
        context: str,
        question: str,
        system_prompt: str | None = None,
    ) -> tuple[str, int, int]:
        """Generate an answer.

        Returns:
            (answer_text, input_tokens, output_tokens)
        """
        if system_prompt is None:
            system_prompt = DEFAULT_SYSTEM_PROMPT

        user_message = self._build_user_message(context, question)

        if settings.openai_api_key:
            try:
                return _openai_generate(system_prompt, user_message)
            except Exception as exc:
                logger.warning(f"OpenAI generation failed, using fallback: {exc}")

        # Offline extractive fallback
        answer = _extractive_answer(context, question)
        # Estimate tokens as word count (rough)
        input_tokens = len((system_prompt + " " + user_message).split())
        output_tokens = len(answer.split())
        return answer, input_tokens, output_tokens

    def stream(
        self,
        context: str,
        question: str,
        system_prompt: str | None = None,
    ) -> Generator[str, None, None]:
        """Stream answer tokens as text deltas.

        Yields str deltas. Falls back to yielding the full answer at once
        when OpenAI is unavailable.
        """
        if system_prompt is None:
            system_prompt = DEFAULT_SYSTEM_PROMPT

        user_message = self._build_user_message(context, question)

        if settings.openai_api_key:
            try:
                yield from _openai_stream(system_prompt, user_message)
                return
            except Exception as exc:
                logger.warning(f"OpenAI streaming failed, using fallback: {exc}")

        # Offline fallback: yield the full extractive answer at once
        answer = _extractive_answer(context, question)
        yield answer


# Module-level singleton
_generator: Generator | None = None


def get_generator() -> Generator:
    global _generator
    if _generator is None:
        _generator = Generator()
    return _generator
