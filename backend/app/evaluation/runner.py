"""EvaluationRunner — end-to-end evaluation orchestrator.

Usage:
    runner = EvaluationRunner(config_overrides={"chunking_strategy": "recursive"})
    summary = runner.run(name="smoke", dataset_path="evaluation/datasets/eval_set.json")

The runner:
1. Ensures the sample corpus is ingested (idempotent via SHA256 dedup).
2. Loads the eval dataset JSON.
3. Runs each example through rag_service.ask().
4. Computes per-example metrics and a `passed` boolean.
5. Aggregates means per metric + per-category breakdown.
6. Persists EvaluationRun + EvaluationResult rows (best-effort, falls back to JSON).
7. Returns a summary dict.
"""
from __future__ import annotations

import json
import os
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

from app.core.config import settings
from app.core.logging import get_logger
from app.evaluation.metrics import (
    answer_correctness,
    citation_accuracy,
    confidence_calibration,
    faithfulness,
    retrieval_recall,
)
from app.schemas.ask import AskRequest

logger = get_logger(__name__)

# Repository root is two levels up from backend/
_REPO_ROOT = Path(__file__).resolve().parents[3]
_SAMPLE_DATA_DIR = _REPO_ROOT / "sample_data" / "raw"
_DEFAULT_DATASET = _REPO_ROOT / "evaluation" / "datasets" / "eval_set.json"
_REPORTS_DIR = _REPO_ROOT / "evaluation" / "reports"

# Passing threshold per metric
_PASS_THRESHOLDS = {
    "retrieval_recall": 0.5,
    "answer_correctness": 0.4,
    "faithfulness": 0.5,
    "citation_accuracy": 0.3,
}


def _get_content_type(filename: str) -> str:
    ext = Path(filename).suffix.lower()
    mapping = {
        ".md": "text/markdown",
        ".txt": "text/plain",
        ".html": "text/html",
        ".htm": "text/html",
        ".pdf": "application/pdf",
    }
    return mapping.get(ext, "application/octet-stream")


class EvaluationRunner:
    """Orchestrates evaluation of the RAG pipeline against a labeled dataset."""

    def __init__(
        self,
        config_overrides: dict[str, Any] | None = None,
        corpus_dir: str | Path | None = None,
    ) -> None:
        """
        Args:
            config_overrides: dict of settings overrides, e.g.
                {"chunking_strategy": "fixed", "dense_weight": 1.0, "sparse_weight": 0.0}
            corpus_dir: directory containing sample corpus files to ingest.
                Defaults to sample_data/raw/ relative to repo root.
        """
        self.config_overrides = config_overrides or {}
        self.corpus_dir = Path(corpus_dir) if corpus_dir else _SAMPLE_DATA_DIR
        self._apply_config_overrides()

    def _apply_config_overrides(self) -> None:
        """Monkey-patch settings for this run (process-level, not persistent)."""
        for key, value in self.config_overrides.items():
            if hasattr(settings, key):
                setattr(settings, key, value)
                logger.info(f"Config override: {key}={value!r}")
            else:
                logger.warning(f"Unknown config key: {key!r} — ignored")

    # ------------------------------------------------------------------
    # Corpus ingestion
    # ------------------------------------------------------------------

    def ensure_corpus_ingested(self, db) -> dict[str, str]:
        """Ingest all files in corpus_dir.

        If a DB session is available, uses the full IngestionService pipeline
        (idempotent via SHA256 dedup, persists Document/Chunk rows).

        If no DB is available, falls back to _offline_ingest which directly
        loads, chunks, embeds and upserts into the in-memory vector store
        (no persistence, but retrieval will work for the duration of the process).

        Returns dict mapping filename → ingest status/message.
        """
        if db is not None:
            return self._online_ingest(db)
        else:
            return self._offline_ingest()

    def _online_ingest(self, db) -> dict[str, str]:
        """Full ingestion via IngestionService (requires DB)."""
        from app.services.ingestion_service import get_ingestion_service

        ingestion_svc = get_ingestion_service()
        results = {}
        strategy = self.config_overrides.get(
            "chunking_strategy", settings.chunking_strategy
        )

        if not self.corpus_dir.exists():
            logger.warning(f"Corpus dir does not exist: {self.corpus_dir}")
            return results

        for path in sorted(self.corpus_dir.iterdir()):
            if not path.is_file():
                continue
            filename = path.name
            content_type = _get_content_type(filename)
            try:
                raw_bytes = path.read_bytes()
                resp = ingestion_svc.ingest_upload(
                    db,
                    filename=filename,
                    content_type=content_type,
                    raw_bytes=raw_bytes,
                    strategy=strategy,
                )
                results[filename] = resp.message or resp.status
                logger.info(
                    f"Ingested {filename!r}: {resp.num_chunks} chunks "
                    f"({resp.message or resp.status})"
                )
            except Exception as exc:
                logger.error(f"Failed to ingest {filename!r}: {exc}")
                results[filename] = f"error: {exc}"

        return results

    def _offline_ingest(self) -> dict[str, str]:
        """Offline ingestion: load → chunk → embed → upsert into in-memory store.

        Bypasses DB entirely.  Retrieval will work within the same process.
        """
        import uuid as _uuid

        from app.chunking import get_chunker
        from app.ingestion.detect import detect_doc_type
        from app.ingestion.loaders import get_loader
        from app.services.embeddings import get_embedding_client
        from app.services.vector_store import get_vector_store

        strategy = self.config_overrides.get(
            "chunking_strategy", settings.chunking_strategy
        )
        chunker = get_chunker(strategy)
        embedding_client = get_embedding_client()
        vector_store = get_vector_store()
        results: dict[str, str] = {}

        if not self.corpus_dir.exists():
            logger.warning(f"Corpus dir does not exist: {self.corpus_dir}")
            return results

        for path in sorted(self.corpus_dir.iterdir()):
            if not path.is_file():
                continue
            filename = path.name
            content_type = _get_content_type(filename)
            try:
                doc_type = detect_doc_type(filename, content_type)
                raw_bytes = path.read_bytes()
                loader = get_loader(doc_type)
                sections = loader.load(raw_bytes, filename)
                chunk_pieces = chunker.chunk(sections)

                if not chunk_pieces:
                    results[filename] = "no chunks produced"
                    continue

                texts = [cp.text for cp in chunk_pieces]
                embedding_result = embedding_client.embed(texts)
                vectors = embedding_result.vectors

                doc_id = str(_uuid.uuid4())
                chunk_ids = [str(_uuid.uuid4()) for _ in chunk_pieces]
                payloads = [
                    {
                        "document_id": doc_id,
                        "chunk_id": cid,
                        "source_file": filename,
                        "page_number": cp.page_number,
                        "section_title": cp.section_title,
                        "text": cp.text,
                    }
                    for cid, cp in zip(chunk_ids, chunk_pieces)
                ]

                vector_store.upsert(chunk_ids, vectors, payloads)
                results[filename] = f"offline: {len(chunk_pieces)} chunks indexed"
                logger.info(
                    f"Offline ingested {filename!r}: {len(chunk_pieces)} chunks"
                )
            except Exception as exc:
                logger.error(f"Offline ingest failed for {filename!r}: {exc}")
                results[filename] = f"error: {exc}"

        return results

    # ------------------------------------------------------------------
    # Dataset loading
    # ------------------------------------------------------------------

    @staticmethod
    def load_dataset(dataset_path: str | Path) -> list[dict]:
        """Load eval dataset JSON and return list of example dicts."""
        path = Path(dataset_path)
        if not path.exists():
            raise FileNotFoundError(f"Dataset not found: {path}")
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        logger.info(f"Loaded {len(data)} examples from {path}")
        return data

    # ------------------------------------------------------------------
    # Single example evaluation
    # ------------------------------------------------------------------

    def _evaluate_example(
        self,
        example: dict,
        rag_service,
        db,
    ) -> dict:
        """Run RAG pipeline on one example and return per-example metrics dict."""
        question = example["question"]
        expected = example.get("expected_answer")
        must_include = example.get("must_include", [])
        relevant_files = example.get("relevant_source_files", [])

        req = AskRequest(
            question=question,
            include_trace=True,
            prompt_version=self.config_overrides.get("prompt_version"),
        )

        t0 = time.perf_counter()
        try:
            resp = rag_service.ask(db, req)
        except Exception as exc:
            logger.error(f"RAG ask failed for example {example['id']!r}: {exc}")
            return {
                "example_id": example["id"],
                "category": example["category"],
                "question": question,
                "expected_answer": expected,
                "predicted_answer": None,
                "metrics": {
                    "retrieval_recall": 0.0,
                    "answer_correctness": 0.0,
                    "faithfulness": 0.0,
                    "citation_accuracy": 0.0,
                    "confidence": 0.0,
                    "latency_ms": 0,
                    "error": str(exc),
                },
                "passed": False,
            }

        latency_ms = int((time.perf_counter() - t0) * 1000)
        predicted = resp.answer

        # Collect retrieved source files from the trace
        retrieved_files: list[str] = []
        if resp.trace:
            for chunk in resp.trace.reranked.results:
                if chunk.source_file and chunk.source_file not in retrieved_files:
                    retrieved_files.append(chunk.source_file)
            # Also include RRF stage for broader recall
            for chunk in resp.trace.rrf.results:
                if chunk.source_file and chunk.source_file not in retrieved_files:
                    retrieved_files.append(chunk.source_file)

        # Compute metrics
        r_recall = retrieval_recall(retrieved_files, relevant_files)
        a_correct = answer_correctness(predicted, expected, must_include)
        faith = faithfulness(resp.verifications)
        cit_acc = citation_accuracy(resp.verifications)
        conf_normalized = resp.confidence.score / 100.0  # convert 0-100 → 0-1

        metrics = {
            "retrieval_recall": round(r_recall, 4),
            "answer_correctness": round(a_correct, 4),
            "faithfulness": round(faith, 4),
            "citation_accuracy": round(cit_acc, 4),
            "confidence": round(conf_normalized, 4),
            "latency_ms": latency_ms,
        }

        # Determine pass/fail
        passed = (
            r_recall >= _PASS_THRESHOLDS["retrieval_recall"]
            and a_correct >= _PASS_THRESHOLDS["answer_correctness"]
            and faith >= _PASS_THRESHOLDS["faithfulness"]
        )

        return {
            "example_id": example["id"],
            "category": example["category"],
            "question": question,
            "expected_answer": expected,
            "predicted_answer": predicted,
            "metrics": metrics,
            "passed": passed,
        }

    # ------------------------------------------------------------------
    # Main run
    # ------------------------------------------------------------------

    def run(
        self,
        name: str,
        dataset_path: str | Path | None = None,
        db=None,
    ) -> dict:
        """Run full evaluation and return summary dict.

        Args:
            name:         Human-readable name for this run.
            dataset_path: Path to eval dataset JSON. Defaults to eval_set.json.
            db:           SQLAlchemy session. If None, a new one is created.
                          If DB is unavailable, falls back to JSON persistence.

        Returns:
            Summary dict with aggregate metrics, per-category breakdown, and
            the path to the persisted run (DB id or JSON file path).
        """
        dataset_path = Path(dataset_path) if dataset_path else _DEFAULT_DATASET
        run_id = str(uuid.uuid4())

        # Create or reuse DB session
        _own_db = False
        if db is None:
            db, _own_db = self._get_db_session()

        try:
            # 1. Ingest corpus (works with or without DB)
            logger.info(f"=== EvaluationRun '{name}' ({run_id}) ===")
            ingest_results = self.ensure_corpus_ingested(db)
            logger.info(f"Corpus ingestion: {len(ingest_results)} files processed")

            # 2. Load dataset
            examples = self.load_dataset(dataset_path)

            # 3. Initialise RAG service
            from app.services.rag_service import get_rag_service

            rag_svc = get_rag_service()

            # 4. Evaluate each example
            results: list[dict] = []
            for i, ex in enumerate(examples):
                logger.info(
                    f"[{i+1}/{len(examples)}] {ex['id']} ({ex['category']})"
                )
                result = self._evaluate_example(ex, rag_svc, db)
                results.append(result)

            # 5. Aggregate metrics
            summary = self._aggregate(name, run_id, results, dataset_path)

            # 6. Persist
            run_config = {
                **self.config_overrides,
                "dataset": str(dataset_path),
                "chunking_strategy": settings.chunking_strategy,
                "dense_weight": settings.dense_weight,
                "sparse_weight": settings.sparse_weight,
                "prompt_version": settings.prompt_version,
            }
            summary["config"] = run_config

            self._persist(
                run_id=run_id,
                name=name,
                dataset_path=dataset_path,
                config=run_config,
                summary=summary,
                results=results,
                db=db,
            )

            return summary

        finally:
            if _own_db and db is not None:
                try:
                    db.close()
                except Exception:
                    pass

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _get_db_session():
        """Return (session, owned). Returns (None, False) if DB unavailable."""
        try:
            from app.db.session import SessionLocal

            db = SessionLocal()
            # Quick connection check
            db.execute(__import__("sqlalchemy").text("SELECT 1"))
            return db, True
        except Exception as exc:
            logger.warning(f"DB unavailable ({exc}), will use JSON fallback")
            return None, False

    def _aggregate(
        self,
        name: str,
        run_id: str,
        results: list[dict],
        dataset_path: Path,
    ) -> dict:
        """Compute aggregate and per-category metrics."""
        if not results:
            return {
                "run_id": run_id,
                "name": name,
                "dataset": str(dataset_path),
                "num_examples": 0,
                "aggregate": {},
                "per_category": {},
                "per_example": results,
            }

        metric_keys = [
            "retrieval_recall",
            "answer_correctness",
            "faithfulness",
            "citation_accuracy",
        ]

        # Confidence calibration (needs confidences + passed lists)
        confidences = [r["metrics"].get("confidence", 0.0) for r in results]
        passed_list = [r["passed"] for r in results]
        cal_score = confidence_calibration(confidences, passed_list)

        def mean_metrics(subset: list[dict]) -> dict:
            agg: dict[str, float] = {}
            for k in metric_keys:
                vals = [r["metrics"].get(k, 0.0) for r in subset if "error" not in r.get("metrics", {})]
                agg[k] = round(sum(vals) / len(vals), 4) if vals else 0.0
            # Calibration computed globally (not sliced per category)
            agg["confidence_calibration"] = round(cal_score, 4)
            passed = [r["passed"] for r in subset]
            agg["pass_rate"] = round(sum(passed) / len(passed), 4) if passed else 0.0
            agg["num_examples"] = len(subset)
            return agg

        aggregate = mean_metrics(results)

        # Per-category breakdown
        categories = sorted({r["category"] for r in results})
        per_category: dict[str, dict] = {}
        for cat in categories:
            subset = [r for r in results if r["category"] == cat]
            per_category[cat] = mean_metrics(subset)

        return {
            "run_id": run_id,
            "name": name,
            "dataset": str(dataset_path),
            "created_at": datetime.utcnow().isoformat() + "Z",
            "num_examples": len(results),
            "aggregate": aggregate,
            "per_category": per_category,
            "per_example": results,
        }

    def _persist(
        self,
        *,
        run_id: str,
        name: str,
        dataset_path: Path,
        config: dict,
        summary: dict,
        results: list[dict],
        db,
    ) -> None:
        """Persist the run to DB (primary) or JSON (fallback)."""
        agg = summary.get("aggregate", {})

        # --- DB persistence ---
        if db is not None:
            try:
                from app.models.evaluation import EvaluationResult, EvaluationRun

                run = EvaluationRun(
                    id=run_id,
                    name=name,
                    dataset=str(dataset_path),
                    config=config,
                    retrieval_recall=agg.get("retrieval_recall"),
                    answer_correctness=agg.get("answer_correctness"),
                    faithfulness=agg.get("faithfulness"),
                    citation_accuracy=agg.get("citation_accuracy"),
                    confidence_calibration=agg.get("confidence_calibration"),
                )
                db.add(run)
                db.flush()

                for r in results:
                    er = EvaluationResult(
                        id=str(uuid.uuid4()),
                        run_id=run_id,
                        example_id=r["example_id"],
                        category=r["category"],
                        question=r["question"],
                        expected_answer=r.get("expected_answer"),
                        predicted_answer=r.get("predicted_answer"),
                        metrics=r.get("metrics", {}),
                        passed=r.get("passed", False),
                    )
                    db.add(er)

                db.commit()
                logger.info(f"EvaluationRun {run_id!r} persisted to DB")
                summary["persisted_to"] = "db"
                return
            except Exception as exc:
                logger.warning(f"DB persist failed ({exc}); falling back to JSON")
                try:
                    db.rollback()
                except Exception:
                    pass

        # --- JSON fallback ---
        _REPORTS_DIR.mkdir(parents=True, exist_ok=True)
        json_path = _REPORTS_DIR / f"{name}_{run_id[:8]}.json"
        # Remove per_example from summary to avoid redundancy (stored separately)
        output = {k: v for k, v in summary.items() if k != "per_example"}
        output["results"] = results
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(output, f, indent=2, default=str)
        logger.warning(f"DB unavailable — run saved to {json_path}")
        summary["persisted_to"] = str(json_path)
