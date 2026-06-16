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
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    # ----- App -----
    app_name: str = "Hybrid RAG Platform"
    environment: Literal["local", "ci", "production"] = "local"
    log_level: str = "INFO"
    api_v1_prefix: str = "/v1"

    # ----- Postgres -----
    postgres_user: str = "rag"
    postgres_password: str = "rag"
    postgres_db: str = "rag"
    postgres_host: str = "postgres"
    postgres_port: int = 5432

    @property
    def database_url(self) -> str:
        return (
            f"postgresql+psycopg://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    # ----- Qdrant -----
    qdrant_host: str = "qdrant"
    qdrant_port: int = 6333
    qdrant_collection: str = "rag_chunks"

    # ----- OpenAI / LLM -----
    openai_api_key: str = Field(default="", description="OpenAI API key")
    embedding_model: str = "text-embedding-3-small"
    embedding_dim: int = 1536
    generation_model: str = "gpt-4o-mini"
    generation_temperature: float = 0.0

    # Pricing (USD per 1M tokens) for cost tracking.
    embedding_price_per_1m: float = 0.02
    generation_input_price_per_1m: float = 0.15
    generation_output_price_per_1m: float = 0.60

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

    # ----- Storage -----
    raw_storage_dir: str = "/data/raw"
    processed_storage_dir: str = "/data/processed"


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
