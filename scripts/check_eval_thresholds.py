"""Eval-gated CI: run the evaluation suite and fail on metric regression.

Runs the offline evaluation (deterministic local provider, no keys/DB needed)
and compares aggregate metrics against configurable thresholds. Exits non-zero
if any metric falls below its floor, so CI blocks regressions.

Thresholds are read from environment variables so they can be tuned per branch
or raised once a real provider key is available in CI:

    EVAL_MIN_RETRIEVAL_RECALL    (default 0.70)   provider-independent
    EVAL_MIN_ANSWER_CORRECTNESS  (default 0.15)
    EVAL_MIN_FAITHFULNESS        (default 0.30)
    EVAL_MIN_CITATION_ACCURACY   (default 0.25)

Defaults are calibrated to pass on the local provider (an extractive heuristic),
which makes the gate a genuine regression detector offline while staying green
without secrets. With ANTHROPIC_API_KEY set in CI, raise these toward production
targets (e.g. faithfulness ≥ 0.80) to gate on real generation quality.

Usage:
    python scripts/check_eval_thresholds.py
    python scripts/check_eval_thresholds.py --name ci --strategy recursive
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
for _cand in (_REPO_ROOT / "backend", _REPO_ROOT):
    if (_cand / "app").is_dir():
        sys.path.insert(0, str(_cand))


# Metric -> (env var, default floor)
_THRESHOLDS = {
    "retrieval_recall": ("EVAL_MIN_RETRIEVAL_RECALL", 0.70),
    "answer_correctness": ("EVAL_MIN_ANSWER_CORRECTNESS", 0.15),
    "faithfulness": ("EVAL_MIN_FAITHFULNESS", 0.30),
    "citation_accuracy": ("EVAL_MIN_CITATION_ACCURACY", 0.25),
}


def _threshold(metric: str) -> float:
    env_var, default = _THRESHOLDS[metric]
    return float(os.environ.get(env_var, default))


def main() -> int:
    parser = argparse.ArgumentParser(description="Eval threshold gate for CI")
    parser.add_argument("--name", default="ci")
    parser.add_argument(
        "--strategy", default="recursive", choices=["fixed", "recursive", "semantic"]
    )
    parser.add_argument("--dataset", default=None)
    args = parser.parse_args()

    from app.evaluation.runner import EvaluationRunner

    runner = EvaluationRunner(config_overrides={"chunking_strategy": args.strategy})
    # db=None → offline ingest + JSON persistence; no Postgres needed in CI.
    summary = runner.run(name=args.name, dataset_path=args.dataset, db=None)
    agg = summary.get("aggregate", {})

    print("\n" + "=" * 60)
    print(f"EVAL GATE — run '{args.name}' ({summary.get('num_examples', 0)} examples)")
    print("=" * 60)
    print(f"{'metric':<22}{'score':>8}{'floor':>8}   result")
    print("-" * 60)

    failures: list[str] = []
    for metric in _THRESHOLDS:
        score = float(agg.get(metric, 0.0))
        floor = _threshold(metric)
        ok = score >= floor
        if not ok:
            failures.append(
                f"{metric}={score:.3f} below floor {floor:.3f}"
            )
        print(f"{metric:<22}{score:>8.3f}{floor:>8.3f}   {'PASS' if ok else 'FAIL'}")

    print("-" * 60)
    if failures:
        print(f"\n❌ EVAL GATE FAILED:\n  - " + "\n  - ".join(failures))
        return 1
    print("\n✅ EVAL GATE PASSED — all metrics at or above their floors.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
