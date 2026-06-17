"""Tests for provider selection, fallback, and startup validation.

All offline: no API keys, no network. Exercises the factory resolution logic,
the embedding-dimension guardrail, and the fail-fast/strict behaviour.
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest


# --------------------------------------------------------------------------- #
# LLM provider selection / fallback                                            #
# --------------------------------------------------------------------------- #


class TestLLMProviderSelection:
    def setup_method(self):
        from app.providers.factory import reset_llm_provider

        reset_llm_provider()

    def teardown_method(self):
        from app.providers.factory import reset_llm_provider

        reset_llm_provider()

    def test_local_provider_when_configured_local(self, monkeypatch):
        from app.core.config import settings
        from app.providers.factory import get_llm_provider, reset_llm_provider

        monkeypatch.setattr(settings, "llm_provider", "local")
        reset_llm_provider()
        provider = get_llm_provider()
        assert provider.name == "local"

    def test_anthropic_falls_back_to_local_without_key(self, monkeypatch):
        """Configured anthropic + no key → silent fallback to local."""
        from app.core.config import settings
        from app.providers.factory import get_llm_provider, reset_llm_provider

        monkeypatch.setattr(settings, "llm_provider", "anthropic")
        monkeypatch.setattr(settings, "anthropic_api_key", "")
        reset_llm_provider()
        provider = get_llm_provider()
        assert provider.name == "local"

    def test_anthropic_selected_when_key_present(self, monkeypatch):
        """With a key set, the factory builds the real AnthropicProvider.

        We don't make a network call — just assert the resolved provider is the
        Anthropic one (its client is constructed lazily/cheaply).
        """
        from app.core.config import settings
        from app.providers.factory import get_llm_provider, reset_llm_provider

        monkeypatch.setattr(settings, "llm_provider", "anthropic")
        monkeypatch.setattr(settings, "anthropic_api_key", "sk-ant-test-not-real")
        reset_llm_provider()
        provider = get_llm_provider()
        assert provider.name == "anthropic"
        assert provider.model == settings.anthropic_model
        assert provider.input_price_per_1m > 0

    def test_provider_is_cached(self, monkeypatch):
        from app.core.config import settings
        from app.providers.factory import get_llm_provider, reset_llm_provider

        monkeypatch.setattr(settings, "llm_provider", "local")
        reset_llm_provider()
        assert get_llm_provider() is get_llm_provider()


# --------------------------------------------------------------------------- #
# Embedding provider selection                                                 #
# --------------------------------------------------------------------------- #


class TestEmbeddingProviderSelection:
    def test_openai_falls_back_to_local_without_key(self, monkeypatch):
        from app.core.config import settings
        from app.providers.embeddings.factory import (
            get_embedding_provider,
            reset_embedding_provider,
        )

        monkeypatch.setattr(settings, "embedding_provider", "openai")
        monkeypatch.setattr(settings, "openai_api_key", "")
        reset_embedding_provider()
        provider = get_embedding_provider()
        assert provider.name == "local"
        reset_embedding_provider()

    def test_local_embedding_dim_matches_settings(self, monkeypatch):
        from app.core.config import settings
        from app.providers.embeddings.factory import (
            get_embedding_provider,
            reset_embedding_provider,
        )

        monkeypatch.setattr(settings, "embedding_provider", "local")
        reset_embedding_provider()
        provider = get_embedding_provider()
        assert provider.dim == settings.embedding_dim
        reset_embedding_provider()


# --------------------------------------------------------------------------- #
# Startup validation + embedding-dimension guardrail                           #
# --------------------------------------------------------------------------- #


class TestStartupValidation:
    def teardown_method(self):
        from app.providers.embeddings.factory import reset_embedding_provider
        from app.providers.factory import reset_llm_provider

        reset_llm_provider()
        reset_embedding_provider()

    def test_local_setup_passes(self, monkeypatch):
        from app.core.config import settings
        from app.core.startup import run_startup_checks
        from app.providers.embeddings.factory import reset_embedding_provider
        from app.providers.factory import reset_llm_provider

        monkeypatch.setattr(settings, "llm_provider", "local")
        monkeypatch.setattr(settings, "embedding_provider", "local")
        reset_llm_provider()
        reset_embedding_provider()
        report = run_startup_checks(strict=False)
        assert report.ok

    def test_non_strict_downgrade_is_warning_not_error(self, monkeypatch):
        from app.core.config import settings
        from app.core.startup import run_startup_checks
        from app.providers.embeddings.factory import reset_embedding_provider
        from app.providers.factory import reset_llm_provider

        monkeypatch.setattr(settings, "llm_provider", "anthropic")
        monkeypatch.setattr(settings, "anthropic_api_key", "")
        reset_llm_provider()
        reset_embedding_provider()
        report = run_startup_checks(strict=False)
        assert report.ok  # downgrade tolerated outside production
        assert any("llm" in w for w in report.warnings)

    def test_strict_downgrade_is_fatal(self, monkeypatch):
        """In production (strict), a silent cloud→local downgrade fails boot."""
        from app.core.config import settings
        from app.core.startup import run_startup_checks
        from app.providers.embeddings.factory import reset_embedding_provider
        from app.providers.factory import reset_llm_provider

        monkeypatch.setattr(settings, "llm_provider", "anthropic")
        monkeypatch.setattr(settings, "anthropic_api_key", "")
        reset_llm_provider()
        reset_embedding_provider()
        report = run_startup_checks(strict=True)
        assert not report.ok
        assert report.errors

    def test_embedding_dim_mismatch_detected(self, monkeypatch):
        """Active model dim != EMBEDDING_DIM is a fatal, actionable error."""
        from app.core.config import settings
        from app.core.startup import StartupReport, validate_embedding_dimensions
        from app.providers.embeddings.factory import reset_embedding_provider

        # Local provider reads dim from settings at construction; build it at
        # 384, then flip EMBEDDING_DIM to 1536 to simulate a mismatch.
        monkeypatch.setattr(settings, "embedding_provider", "local")
        monkeypatch.setattr(settings, "embedding_dim", 384)
        reset_embedding_provider()
        from app.providers.embeddings.factory import get_embedding_provider

        get_embedding_provider()  # constructs at dim=384
        monkeypatch.setattr(settings, "embedding_dim", 1536)

        report = StartupReport()
        validate_embedding_dimensions(report)
        assert not report.ok
        assert any("dimension mismatch" in e.lower() for e in report.errors)
        reset_embedding_provider()

    def test_strict_defaults_to_production_env(self, monkeypatch):
        from app.core.config import settings
        from app.core.startup import run_startup_checks
        from app.providers.embeddings.factory import reset_embedding_provider
        from app.providers.factory import reset_llm_provider

        monkeypatch.setattr(settings, "environment", "production")
        monkeypatch.setattr(settings, "llm_provider", "anthropic")
        monkeypatch.setattr(settings, "anthropic_api_key", "")
        reset_llm_provider()
        reset_embedding_provider()
        report = run_startup_checks()  # strict inferred from environment
        assert not report.ok
