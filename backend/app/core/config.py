"""Application configuration.

All tunable behaviour of the platform is centralised here and surfaced via
environment variables so the same image runs unchanged across local Docker,
CI, and production. Defaults are chosen to give a working system out of the box.
"""
from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        # Fields carrying a validation_alias (database_url_override -> DATABASE_URL)
        # are otherwise settable *only* by that alias, which would make direct
        # construction in tests and scripts silently fall through to defaults.
        populate_by_name=True,
    )

    # ----- App -----
    app_name: str = "Hybrid RAG Platform"
    app_version: str = "1.0.0"
    environment: Literal["local", "ci", "production"] = "local"
    log_level: str = "INFO"
    api_v1_prefix: str = "/v1"

    # ----- CORS -----
    # Comma-separated browser origins allowed to call the API. "*" allows any
    # origin (fine for local Docker / a public read-only demo); in production set
    # this to the deployed frontend origin(s), e.g.
    # "https://recall.vercel.app,https://recall.yourdomain.dev". When it is not
    # "*", credentialed requests are permitted (the spec forbids credentials with
    # a wildcard origin).
    allowed_origins: str = "*"

    @property
    def allowed_origins_list(self) -> list[str]:
        raw = self.allowed_origins.strip()
        if raw == "*" or not raw:
            return ["*"]
        return [o.strip() for o in raw.split(",") if o.strip()]

    # ----- Rate limiting (per client IP) -----
    # A public URL means anyone can call the API; the generation endpoints spend
    # real LLM-provider budget, so they get a stricter per-IP cap. Behind a proxy
    # (Railway/Vercel) the client IP is read from X-Forwarded-For.
    rate_limit_enabled: bool = True
    rate_limit_default: str = "200/minute"  # all routes except liveness /health
    rate_limit_ask: str = "15/minute"       # /v1/ask + /v1/ask/stream (LLM spend)

    # ----- Admin guard (optional; OFF by default) -----
    # Reading and asking are always open so anyone can try the demo with no
    # sign-in. Destructive/expensive routes (ingest, delete corpus/document,
    # run evaluation) are gated by this key *only when it is set*: leave it blank
    # and those routes stay open (current behaviour); set ADMIN_API_KEY and
    # callers must send it in the `X-Admin-Key` header or get 401. This is the
    # provision for locking the app down later without adding a login wall.
    admin_api_key: str = Field(default="", description="If set, required for admin/destructive routes")

    # ----- Postgres -----
    postgres_user: str = "rag"
    postgres_password: str = "rag"
    postgres_db: str = "rag"
    postgres_host: str = "postgres"
    postgres_port: int = 5432

    # Managed Postgres (Neon, Supabase, Railway) issues one connection string
    # rather than discrete parts, usually carrying query args like
    # ?sslmode=require that the assembled form below cannot express. When
    # DATABASE_URL is set it takes precedence, mirroring how QDRANT_URL
    # overrides QDRANT_HOST/QDRANT_PORT.
    database_url_override: str = Field(
        default="",
        validation_alias="DATABASE_URL",
        description="Full SQLAlchemy/libpq connection string; overrides POSTGRES_* when set",
    )

    @property
    def database_url(self) -> str:
        override = self.database_url_override.strip()
        if not override:
            return (
                f"postgresql+psycopg://{self.postgres_user}:{self.postgres_password}"
                f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
            )
        # Providers hand out `postgres://` or `postgresql://`. SQLAlchemy maps
        # both to psycopg2, which this project does not install (it uses
        # psycopg 3), so the driver has to be named explicitly or engine
        # creation fails with ModuleNotFoundError: no module named 'psycopg2'.
        for scheme in ("postgresql://", "postgres://"):
            if override.startswith(scheme):
                return "postgresql+psycopg://" + override[len(scheme) :]
        return override

    # ----- Qdrant -----
    qdrant_host: str = "qdrant"
    qdrant_port: int = 6333
    qdrant_collection: str = "rag_chunks"
    # Managed Qdrant Cloud: set QDRANT_URL (https://...:6333) + QDRANT_API_KEY to
    # connect over TLS with auth. When QDRANT_URL is set it takes precedence over
    # host/port (used for local Docker). See docs/DEPLOYMENT_GUIDE.md.
    qdrant_url: str = ""
    qdrant_api_key: str = ""

    # ===== LLM provider abstraction =====
    # Which generation/judge provider to use: anthropic | openai | local.
    # `local` is a deterministic offline provider (no network/key) used as the
    # automatic fallback when the selected provider has no API key configured.
    llm_provider: Literal["anthropic", "openai", "local"] = "anthropic"

    # ----- Anthropic (default) -----
    anthropic_api_key: str = Field(default="", description="Anthropic API key")
    # Current Sonnet 4.x id. Generation/verification/judging all run through this.
    anthropic_model: str = "claude-sonnet-4-6"
    # Optional separate (often larger) model for judging/scoring; blank = reuse above.
    anthropic_judge_model: str = ""
    # Adaptive thinking on judge/verify/score calls (reasoning tasks). Off by
    # default to bound latency/cost on high-volume per-claim verification.
    anthropic_use_thinking: bool = False
    # Pricing (USD per 1M tokens) — Claude Sonnet 4.6.
    anthropic_input_price_per_1m: float = 3.00
    anthropic_output_price_per_1m: float = 15.00

    # ----- OpenAI -----
    openai_api_key: str = Field(default="", description="OpenAI API key")
    openai_model: str = "gpt-4o-mini"
    openai_input_price_per_1m: float = 0.15
    openai_output_price_per_1m: float = 0.60

    generation_temperature: float = 0.0
    generation_max_tokens: int = 1024

    # ===== Embedding provider abstraction =====
    # openai | bge | voyage | local
    embedding_provider: Literal["openai", "bge", "voyage", "local"] = "openai"
    embedding_model: str = "text-embedding-3-small"
    embedding_dim: int = 1536  # must match the active embedding model's dimension
    embedding_price_per_1m: float = 0.02

    bge_embedding_model: str = "BAAI/bge-small-en-v1.5"  # 384-dim if selected
    voyage_api_key: str = Field(default="", description="Voyage AI API key")
    voyage_embedding_model: str = "voyage-3"

    # ----- Chunking -----
    # Strategy: "fixed" | "recursive" | "semantic"
    chunking_strategy: Literal["fixed", "recursive", "semantic"] = "recursive"
    chunk_size: int = 512
    chunk_overlap: int = 64
    semantic_breakpoint_percentile: float = 95.0

    # ----- Deduplication -----
    dedup_enabled: bool = True
    dedup_cosine_threshold: float = 0.95

    # ----- Retrieval -----
    dense_top_k: int = 20
    sparse_top_k: int = 20
    rrf_k: int = 60  # RRF smoothing constant
    dense_weight: float = 1.0
    sparse_weight: float = 1.0
    fusion_top_k: int = 20  # candidates passed to reranker

    # ----- Reranking -----
    reranker_model: str = "BAAI/bge-reranker-base"
    rerank_top_k: int = 5  # final context size
    reranker_device: str = "cpu"

    # ----- Generation / Citations -----
    min_confidence_to_answer: float = 20.0
    prompt_version: str = "v1"

    # ----- Uploads -----
    # Hard cap on a single ingested file. Bounds memory (the file is read into
    # RAM for parsing) and disk, so an oversized/abusive upload can't OOM the
    # worker or fill the data volume. Default 10 MiB — ample for docs/PDFs.
    max_upload_bytes: int = 10 * 1024 * 1024

    # ----- Storage -----
    raw_storage_dir: str = "/data/raw"
    processed_storage_dir: str = "/data/processed"


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
