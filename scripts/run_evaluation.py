"""CLI entrypoint for the RAG evaluation suite.

Usage (from repo root):
    python scripts/run_evaluation.py --name smoke --strategy recursive
    python scripts/run_evaluation.py --name dense_only --strategy fixed --dense-weight 1.0 --sparse-weight 0.0
    python scripts/run_evaluation.py --name compare_all --compare

Options:
    --name STR          Name for this evaluation run (default: "eval")
    --strategy STR      Chunking strategy: fixed | recursive | semantic (default: recursive)
    --dense-weight F    Weight for dense retrieval in RRF fusion (default: 1.0)
    --sparse-weight F   Weight for sparse/BM25 retrieval in RRF fusion (default: 1.0)
    --dataset PATH      Path to eval dataset JSON (default: evaluation/datasets/eval_set.json)
    --compare           Run multiple configurations and produce comparison report
    --no-ingest         Skip corpus ingestion (useful if already ingested)
    --verbose           Print per-example results to stdout

Sys.path note:
    This script inserts <repo_root>/backend/ into sys.path so that
    `from app...` imports work when executed from the repo root.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# sys.path setup — must happen before any app imports
# ---------------------------------------------------------------------------
_REPO_ROOT = Path(__file__).resolve().parent.parent
# Support both layouts: host repo-root (app lives in backend/app) and the
# Docker container (app lives directly at /app/app, repo root mounted as /app).
for _cand in (_REPO_ROOT / "backend", _REPO_ROOT):
    if (_cand / "app").is_dir():
        sys.path.insert(0, str(_cand))


def _get_db():
    """Return a DB session, or None if unavailable."""
    try:
        import sqlalchemy
        from app.db.session import SessionLocal

        db = SessionLocal()
        db.execute(sqlalchemy.text("SELECT 1"))
        return db
    except Exception as e:
        print(f"[WARN] Database unavailable ({e}). Using JSON fallback for persistence.")
        return None


def run_single(args: argparse.Namespace) -> dict:
    """Run a single evaluation configuration and generate reports."""
    from app.evaluation.report import generate_reports
    from app.evaluation.runner import EvaluationRunner

    config = {
        "chunking_strategy": args.strategy,
        "dense_weight": args.dense_weight,
        "sparse_weight": args.sparse_weight,
    }
    if args.prompt_version:
        config["prompt_version"] = args.prompt_version

    runner = EvaluationRunner(config_overrides=config)
    db = _get_db() if not args.no_db else None

    print(f"\n{'='*60}")
    print(f"Run: {args.name!r} | strategy={args.strategy} | "
          f"dense={args.dense_weight} sparse={args.sparse_weight}")
    print(f"{'='*60}\n")

    try:
        summary = runner.run(
            name=args.name,
            dataset_path=args.dataset,
            db=db,
        )

        # Generate Markdown + HTML reports
        md_path, html_path = generate_reports(summary, args.name)

        # Print summary to stdout
        agg = summary.get("aggregate", {})
        print(f"\n{'='*60}")
        print(f"RESULTS: {args.name}")
        print(f"{'='*60}")
        print(f"  Examples evaluated : {summary.get('num_examples', 0)}")
        print(f"  Retrieval Recall   : {agg.get('retrieval_recall', 0):.3f}")
        print(f"  Answer Correctness : {agg.get('answer_correctness', 0):.3f}")
        print(f"  Faithfulness       : {agg.get('faithfulness', 0):.3f}")
        print(f"  Citation Accuracy  : {agg.get('citation_accuracy', 0):.3f}")
        print(f"  Conf Calibration   : {agg.get('confidence_calibration', 0):.3f}")
        print(f"  Pass Rate          : {agg.get('pass_rate', 0):.3f}")
        print("\n  Per-category breakdown:")
        for cat, cd in sorted(summary.get("per_category", {}).items()):
            print(
                f"    {cat:<12}: recall={cd.get('retrieval_recall',0):.3f}  "
                f"correct={cd.get('answer_correctness',0):.3f}  "
                f"faith={cd.get('faithfulness',0):.3f}  "
                f"pass={cd.get('pass_rate',0):.3f}  N={cd.get('num_examples',0)}"
            )

        print(f"\n  Persisted to: {summary.get('persisted_to', 'unknown')}")
        print(f"  Markdown report : {md_path}")
        print(f"  HTML report     : {html_path}")

        if args.verbose:
            print(f"\n{'='*60}")
            print("PER-EXAMPLE RESULTS")
            print(f"{'='*60}")
            for r in summary.get("per_example", []):
                m = r.get("metrics", {})
                status = "PASS" if r.get("passed") else "FAIL"
                print(
                    f"  [{status}] {r['example_id']:<20} "
                    f"recall={m.get('retrieval_recall',0):.2f} "
                    f"correct={m.get('answer_correctness',0):.2f} "
                    f"| {r['question'][:55]}"
                )

        return summary

    finally:
        if db is not None:
            try:
                db.close()
            except Exception:
                pass


def run_compare(args: argparse.Namespace) -> None:
    """Run multiple configurations and produce a comparison report."""
    from app.evaluation.report import generate_comparison_report
    from app.evaluation.runner import EvaluationRunner

    CONFIGS = [
        {
            "name": f"{args.name}_fixed_hybrid",
            "chunking_strategy": "fixed",
            "dense_weight": 1.0,
            "sparse_weight": 1.0,
        },
        {
            "name": f"{args.name}_recursive_hybrid",
            "chunking_strategy": "recursive",
            "dense_weight": 1.0,
            "sparse_weight": 1.0,
        },
        {
            "name": f"{args.name}_recursive_dense",
            "chunking_strategy": "recursive",
            "dense_weight": 1.0,
            "sparse_weight": 0.0,
        },
        {
            "name": f"{args.name}_recursive_sparse",
            "chunking_strategy": "recursive",
            "dense_weight": 0.0,
            "sparse_weight": 1.0,
        },
    ]

    summaries: list[dict] = []
    run_names: list[str] = []

    for cfg in CONFIGS:
        run_name = cfg.pop("name")
        runner = EvaluationRunner(config_overrides=cfg)
        db = _get_db()

        print(f"\n{'='*60}")
        print(f"Comparison run: {run_name}")
        print(f"Config: {cfg}")
        print(f"{'='*60}")

        try:
            summary = runner.run(
                name=run_name,
                dataset_path=args.dataset,
                db=db,
            )
            summaries.append(summary)
            run_names.append(run_name)

            agg = summary.get("aggregate", {})
            print(f"  -> recall={agg.get('retrieval_recall',0):.3f}  "
                  f"correct={agg.get('answer_correctness',0):.3f}  "
                  f"pass_rate={agg.get('pass_rate',0):.3f}")
        finally:
            if db is not None:
                try:
                    db.close()
                except Exception:
                    pass

    # Generate comparison reports
    from app.evaluation.report import generate_reports

    for s, n in zip(summaries, run_names):
        generate_reports(s, n)

    md_path, html_path = generate_comparison_report(
        summaries, run_names, output_name="comparison"
    )

    print(f"\n{'='*60}")
    print("COMPARISON SUMMARY")
    print(f"{'='*60}")
    print(f"  Runs compared: {', '.join(run_names)}")
    metric_keys = [
        "retrieval_recall", "answer_correctness", "faithfulness",
        "citation_accuracy", "confidence_calibration", "pass_rate"
    ]
    for k in metric_keys:
        vals = [f"{s.get('aggregate',{}).get(k,0):.3f}" for s in summaries]
        print(f"  {k:<30}: {' | '.join(vals)}")
    print(f"\n  Comparison Markdown : {md_path}")
    print(f"  Comparison HTML     : {html_path}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run RAG evaluation suite",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--name", default="eval", help="Run name")
    parser.add_argument(
        "--strategy",
        default="recursive",
        choices=["fixed", "recursive", "semantic"],
        help="Chunking strategy",
    )
    parser.add_argument(
        "--dense-weight", type=float, default=1.0, help="Dense retrieval weight"
    )
    parser.add_argument(
        "--sparse-weight", type=float, default=1.0, help="Sparse/BM25 retrieval weight"
    )
    parser.add_argument(
        "--dataset",
        default=str(_REPO_ROOT / "evaluation" / "datasets" / "eval_set.json"),
        help="Path to eval dataset JSON",
    )
    parser.add_argument(
        "--prompt-version", default=None, help="Prompt version override"
    )
    parser.add_argument(
        "--compare",
        action="store_true",
        help="Run multiple configurations and produce a comparison report",
    )
    parser.add_argument(
        "--no-db",
        action="store_true",
        help="Skip database (force JSON fallback persistence)",
    )
    parser.add_argument(
        "--verbose", "-v", action="store_true", help="Print per-example results"
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    print("\n=== Acme RAG Evaluation Suite ===")
    print(f"Dataset: {args.dataset}")

    if args.compare:
        run_compare(args)
    else:
        run_single(args)


if __name__ == "__main__":
    main()
