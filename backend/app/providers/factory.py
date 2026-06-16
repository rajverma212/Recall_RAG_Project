"""LLM provider factory.

Resolves ``settings.llm_provider`` to a concrete provider, falling back to the
deterministic ``LocalProvider`` whenever the selected provider is unavailable
(missing API key, missing SDK, or init error). This is what lets the platform
boot and the test-suite run with no credentials, while honoring the configured
provider the moment a key is present.
"""
from __future__ import annotations

from app.core.config import settings
from app.core.logging import get_logger
from app.providers.base import BaseLLMProvider
from app.providers.local_provider import LocalProvider

logger = get_logger(__name__)

_provider: BaseLLMProvider | None = None


def _build(name: str) -> BaseLLMProvider:
    if name == "anthropic":
        if not settings.anthropic_api_key:
            raise RuntimeError("ANTHROPIC_API_KEY not set")
        from app.providers.anthropic_provider import AnthropicProvider

        return AnthropicProvider()
    if name == "openai":
        if not settings.openai_api_key:
            raise RuntimeError("OPENAI_API_KEY not set")
        from app.providers.openai_provider import OpenAIProvider

        return OpenAIProvider()
    if name == "local":
        return LocalProvider()
    raise RuntimeError(f"Unknown LLM provider: {name}")


def get_llm_provider() -> BaseLLMProvider:
    global _provider
    if _provider is None:
        try:
            _provider = _build(settings.llm_provider)
            logger.info(f"LLM provider: {_provider.name} ({_provider.model})")
        except Exception as exc:
            logger.warning(
                f"LLM provider '{settings.llm_provider}' unavailable "
                f"({exc}); falling back to LocalProvider"
            )
            _provider = LocalProvider()
    return _provider


def reset_llm_provider() -> None:
    """Drop the cached provider (used by tests that change config)."""
    global _provider
    _provider = None
