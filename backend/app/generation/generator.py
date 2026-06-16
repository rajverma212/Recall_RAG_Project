"""Answer generation — prompt assembly over the provider layer.

This module owns *prompt assembly* (turning context + question into a user
message); the actual model call is delegated to the active LLM provider, so the
generator has no knowledge of which model/vendor is in use. The public surface
(``Generator.generate`` / ``.stream``) is unchanged, so ``RAGService`` is
agnostic to the refactor.
"""
from __future__ import annotations

from collections.abc import Iterator

from app.core.logging import get_logger
from app.generation.prompts import DEFAULT_SYSTEM_PROMPT, USER_TEMPLATE
from app.providers.factory import get_llm_provider

logger = get_logger(__name__)


class Generator:
    def _build_user_message(self, context: str, question: str) -> str:
        return USER_TEMPLATE.format(context=context, question=question)

    def generate(
        self,
        context: str,
        question: str,
        system_prompt: str | None = None,
    ) -> tuple[str, int, int]:
        """Return (answer_text, input_tokens, output_tokens)."""
        system_prompt = system_prompt or DEFAULT_SYSTEM_PROMPT
        user_message = self._build_user_message(context, question)
        result = get_llm_provider().generate(system_prompt, user_message)
        return result.text, result.input_tokens, result.output_tokens

    def stream(
        self,
        context: str,
        question: str,
        system_prompt: str | None = None,
    ) -> Iterator[str]:
        """Yield answer text deltas from the active provider."""
        system_prompt = system_prompt or DEFAULT_SYSTEM_PROMPT
        user_message = self._build_user_message(context, question)
        yield from get_llm_provider().generate_stream(system_prompt, user_message)


_generator: Generator | None = None


def get_generator() -> Generator:
    global _generator
    if _generator is None:
        _generator = Generator()
    return _generator
