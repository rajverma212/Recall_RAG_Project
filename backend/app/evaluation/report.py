"""Report generator for evaluation runs.

Produces:
- Markdown report: evaluation/reports/<run_name>.md
- Self-contained HTML report: evaluation/reports/<run_name>.html

Both include:
- Aggregate metrics table
- Per-category metrics table
- Per-example pass/fail listing
- Config snapshot
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

_REPORTS_DIR = Path(__file__).resolve().parents[3] / "evaluation" / "reports"

_METRIC_LABELS = {
    "retrieval_recall": "Retrieval Recall",
    "answer_correctness": "Answer Correctness",
    "faithfulness": "Faithfulness",
    "citation_accuracy": "Citation Accuracy",
    "confidence_calibration": "Confidence Calibration",
    "pass_rate": "Pass Rate",
}


def _fmt(v) -> str:
    """Format a metric value for display."""
    if v is None:
        return "—"
    if isinstance(v, float):
        return f"{v:.3f}"
    return str(v)


def _pct(v) -> str:
    if v is None:
        return "—"
    return f"{v * 100:.1f}%"


# ---------------------------------------------------------------------------
# Markdown generation
# ---------------------------------------------------------------------------


def _md_table(headers: list[str], rows: list[list[str]]) -> str:
    """Build a Markdown table string."""
    sep = ["-" * max(len(h), 4) for h in headers]
    lines = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join(sep) + " |",
    ]
    for row in rows:
        lines.append("| " + " | ".join(str(c) for c in row) + " |")
    return "\n".join(lines)


def generate_markdown(summary: dict, run_name: str) -> Path:
    """Generate a Markdown report and write to evaluation/reports/<run_name>.md.

    Args:
        summary: Summary dict returned by EvaluationRunner.run().
        run_name: Base name for the output file.

    Returns:
        Path to the written .md file.
    """
    agg = summary.get("aggregate", {})
    per_cat = summary.get("per_category", {})
    per_ex = summary.get("per_example", [])
    config = summary.get("config", {})
    created_at = summary.get("created_at", datetime.utcnow().isoformat() + "Z")

    lines: list[str] = []
    lines.append(f"# Evaluation Report: {run_name}")
    lines.append(f"\n**Run ID**: `{summary.get('run_id', 'unknown')}`")
    lines.append(f"**Dataset**: `{summary.get('dataset', 'unknown')}`")
    lines.append(f"**Created**: {created_at}")
    lines.append(f"**Examples**: {summary.get('num_examples', 0)}")
    lines.append("")

    # --- Aggregate metrics ---
    lines.append("## Aggregate Metrics\n")
    metric_keys = [
        "retrieval_recall",
        "answer_correctness",
        "faithfulness",
        "citation_accuracy",
        "confidence_calibration",
        "pass_rate",
    ]
    agg_rows = [[_METRIC_LABELS.get(k, k), _fmt(agg.get(k))] for k in metric_keys]
    lines.append(_md_table(["Metric", "Score"], agg_rows))
    lines.append("")

    # --- Per-category ---
    if per_cat:
        lines.append("## Per-Category Breakdown\n")
        cats = sorted(per_cat.keys())
        hdrs = ["Category"] + [_METRIC_LABELS.get(k, k) for k in metric_keys] + ["N"]
        cat_rows = []
        for cat in cats:
            cd = per_cat[cat]
            row = [cat] + [_fmt(cd.get(k)) for k in metric_keys] + [str(cd.get("num_examples", ""))]
            cat_rows.append(row)
        lines.append(_md_table(hdrs, cat_rows))
        lines.append("")

    # --- Config snapshot ---
    lines.append("## Configuration Snapshot\n")
    lines.append("```json")
    lines.append(json.dumps(config, indent=2, default=str))
    lines.append("```\n")

    # --- Per-example results ---
    lines.append("## Per-Example Results\n")
    ex_hdrs = ["ID", "Category", "Pass", "R-Recall", "A-Correct", "Faith", "Cit-Acc", "Conf", "Question"]
    ex_rows = []
    for r in per_ex:
        m = r.get("metrics", {})
        ex_rows.append([
            r.get("example_id", ""),
            r.get("category", ""),
            "✓" if r.get("passed") else "✗",
            _fmt(m.get("retrieval_recall")),
            _fmt(m.get("answer_correctness")),
            _fmt(m.get("faithfulness")),
            _fmt(m.get("citation_accuracy")),
            _fmt(m.get("confidence")),
            (r.get("question", "")[:60] + "…") if len(r.get("question", "")) > 60 else r.get("question", ""),
        ])
    lines.append(_md_table(ex_hdrs, ex_rows))
    lines.append("")

    _REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    md_path = _REPORTS_DIR / f"{run_name}.md"
    md_path.write_text("\n".join(lines), encoding="utf-8")
    return md_path


# ---------------------------------------------------------------------------
# HTML generation
# ---------------------------------------------------------------------------


def _html_escape(s: str) -> str:
    return (
        s.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def _pct_bar(v: float | None) -> str:
    """Return a small HTML progress bar representing a 0–1 metric."""
    if v is None:
        return "—"
    pct = min(100.0, v * 100)
    color = "#4caf50" if pct >= 60 else "#ff9800" if pct >= 40 else "#f44336"
    return (
        f'<div style="display:flex;align-items:center;gap:6px">'
        f'<div style="width:80px;height:10px;background:#eee;border-radius:4px">'
        f'<div style="width:{pct:.0f}%;height:10px;background:{color};border-radius:4px"></div>'
        f'</div>{pct:.1f}%</div>'
    )


def generate_html(summary: dict, run_name: str) -> Path:
    """Generate a self-contained HTML report and write to evaluation/reports/<run_name>.html.

    Args:
        summary: Summary dict returned by EvaluationRunner.run().
        run_name: Base name for the output file.

    Returns:
        Path to the written .html file.
    """
    agg = summary.get("aggregate", {})
    per_cat = summary.get("per_category", {})
    per_ex = summary.get("per_example", [])
    config = summary.get("config", {})
    created_at = summary.get("created_at", datetime.utcnow().isoformat() + "Z")
    run_id = summary.get("run_id", "unknown")

    metric_keys = [
        "retrieval_recall",
        "answer_correctness",
        "faithfulness",
        "citation_accuracy",
        "confidence_calibration",
        "pass_rate",
    ]

    css = """
    body { font-family: system-ui, sans-serif; max-width: 1200px; margin: 40px auto; padding: 0 20px; color: #333; }
    h1 { color: #1a1a2e; border-bottom: 3px solid #4caf50; padding-bottom: 10px; }
    h2 { color: #16213e; margin-top: 36px; }
    table { border-collapse: collapse; width: 100%; margin-bottom: 24px; }
    th { background: #1a1a2e; color: white; padding: 10px 14px; text-align: left; }
    td { padding: 8px 14px; border-bottom: 1px solid #e0e0e0; }
    tr:nth-child(even) { background: #f9f9f9; }
    .pass { color: #4caf50; font-weight: bold; }
    .fail { color: #f44336; font-weight: bold; }
    .meta { background: #f5f5f5; border-left: 4px solid #4caf50; padding: 12px 18px; border-radius: 4px; margin-bottom: 20px; }
    pre { background: #1a1a2e; color: #d4d4d4; padding: 16px; border-radius: 6px; overflow-x: auto; font-size: 13px; }
    .tag { display: inline-block; padding: 2px 8px; border-radius: 12px; font-size: 12px; font-weight: bold; }
    .direct { background: #e3f2fd; color: #1565c0; }
    .multi_hop { background: #f3e5f5; color: #6a1b9a; }
    .ambiguous { background: #fff3e0; color: #e65100; }
    .no_answer { background: #fce4ec; color: #ad1457; }
    """

    def th_row(headers: list[str]) -> str:
        return "<tr>" + "".join(f"<th>{h}</th>" for h in headers) + "</tr>"

    def td_row(cells: list[str]) -> str:
        return "<tr>" + "".join(f"<td>{c}</td>" for c in cells) + "</tr>"

    # Aggregate table
    agg_rows_html = ""
    for k in metric_keys:
        agg_rows_html += td_row([_METRIC_LABELS.get(k, k), _pct_bar(agg.get(k))])

    # Per-category table
    cats = sorted(per_cat.keys())
    cat_hdrs = ["Category"] + [_METRIC_LABELS.get(k, k) for k in metric_keys] + ["N"]
    cat_rows_html = th_row(cat_hdrs)
    for cat in cats:
        cd = per_cat[cat]
        cells = [
            f'<span class="tag {cat}">{cat}</span>',
        ] + [_pct_bar(cd.get(k)) for k in metric_keys] + [str(cd.get("num_examples", ""))]
        cat_rows_html += td_row(cells)

    # Per-example table
    ex_hdrs = ["ID", "Cat", "Pass", "R-Recall", "A-Correct", "Faith", "Cit-Acc", "Conf", "Question"]
    ex_rows_html = th_row(ex_hdrs)
    for r in per_ex:
        m = r.get("metrics", {})
        cat = r.get("category", "")
        passed = r.get("passed", False)
        q = _html_escape((r.get("question", "")[:70] + "…") if len(r.get("question", "")) > 70 else r.get("question", ""))
        err = m.get("error", "")
        err_html = f' <span style="color:#f44336;font-size:11px" title="{_html_escape(err)}">⚠</span>' if err else ""
        ex_rows_html += td_row([
            f'<code>{r.get("example_id", "")}</code>',
            f'<span class="tag {cat}">{cat}</span>',
            '<span class="pass">✓</span>' if passed else '<span class="fail">✗</span>',
            _pct_bar(m.get("retrieval_recall")),
            _pct_bar(m.get("answer_correctness")),
            _pct_bar(m.get("faithfulness")),
            _pct_bar(m.get("citation_accuracy")),
            _pct_bar(m.get("confidence")),
            q + err_html,
        ])

    config_json = _html_escape(json.dumps(config, indent=2, default=str))

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>Eval Report: {_html_escape(run_name)}</title>
  <style>{css}</style>
</head>
<body>
  <h1>Evaluation Report: {_html_escape(run_name)}</h1>
  <div class="meta">
    <strong>Run ID:</strong> <code>{run_id}</code><br/>
    <strong>Dataset:</strong> <code>{_html_escape(summary.get('dataset', ''))}</code><br/>
    <strong>Created:</strong> {_html_escape(created_at)}<br/>
    <strong>Examples:</strong> {summary.get('num_examples', 0)}
  </div>

  <h2>Aggregate Metrics</h2>
  <table>
    <thead><tr><th>Metric</th><th>Score</th></tr></thead>
    <tbody>{agg_rows_html}</tbody>
  </table>

  <h2>Per-Category Breakdown</h2>
  <table>
    <thead>{th_row(cat_hdrs)}</thead>
    <tbody>{"".join(td_row([f'<span class="tag {cat}">{cat}</span>'] + [_pct_bar(per_cat[cat].get(k)) for k in metric_keys] + [str(per_cat[cat].get("num_examples",""))]) for cat in cats)}</tbody>
  </table>

  <h2>Configuration Snapshot</h2>
  <pre><code>{config_json}</code></pre>

  <h2>Per-Example Results</h2>
  <table>
    <thead>{th_row(ex_hdrs)}</thead>
    <tbody>{ex_rows_html}</tbody>
  </table>
</body>
</html>"""

    _REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    html_path = _REPORTS_DIR / f"{run_name}.html"
    html_path.write_text(html, encoding="utf-8")
    return html_path


# ---------------------------------------------------------------------------
# Convenience wrapper: generate both
# ---------------------------------------------------------------------------


def generate_reports(summary: dict, run_name: str) -> tuple[Path, Path]:
    """Generate both Markdown and HTML reports.

    Returns:
        (md_path, html_path)
    """
    md_path = generate_markdown(summary, run_name)
    html_path = generate_html(summary, run_name)
    return md_path, html_path


# ---------------------------------------------------------------------------
# Comparison report
# ---------------------------------------------------------------------------


def generate_comparison_report(
    summaries: list[dict],
    run_names: list[str],
    output_name: str = "comparison",
) -> tuple[Path, Path]:
    """Generate a side-by-side comparison of multiple evaluation runs.

    Args:
        summaries:   List of summary dicts (one per run).
        run_names:   Human-readable labels for each run.
        output_name: Base name for output files.

    Returns:
        (md_path, html_path)
    """
    metric_keys = [
        "retrieval_recall",
        "answer_correctness",
        "faithfulness",
        "citation_accuracy",
        "confidence_calibration",
        "pass_rate",
    ]

    # --- Markdown ---
    lines: list[str] = []
    lines.append("# Evaluation Comparison Report")
    lines.append(f"\n**Generated**: {datetime.utcnow().isoformat()}Z")
    lines.append(f"**Runs compared**: {', '.join(run_names)}\n")

    lines.append("## Side-by-Side Aggregate Metrics\n")
    hdrs = ["Metric"] + run_names
    rows = []
    for k in metric_keys:
        row = [_METRIC_LABELS.get(k, k)]
        for s in summaries:
            row.append(_fmt(s.get("aggregate", {}).get(k)))
        rows.append(row)
    lines.append(_md_table(hdrs, rows))
    lines.append("")

    # Per-category for each run
    all_cats = sorted({
        cat
        for s in summaries
        for cat in s.get("per_category", {}).keys()
    })

    for k in metric_keys:
        lines.append(f"## Per-Category: {_METRIC_LABELS.get(k, k)}\n")
        hdrs2 = ["Category"] + run_names
        cat_rows = []
        for cat in all_cats:
            row = [cat]
            for s in summaries:
                row.append(_fmt(s.get("per_category", {}).get(cat, {}).get(k)))
            cat_rows.append(row)
        lines.append(_md_table(hdrs2, cat_rows))
        lines.append("")

    # Config snapshots
    lines.append("## Configuration Snapshots\n")
    for name, s in zip(run_names, summaries):
        lines.append(f"### {name}")
        lines.append("```json")
        lines.append(json.dumps(s.get("config", {}), indent=2, default=str))
        lines.append("```\n")

    _REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    md_path = _REPORTS_DIR / f"{output_name}.md"
    md_path.write_text("\n".join(lines), encoding="utf-8")

    # --- HTML ---
    css = """
    body { font-family: system-ui, sans-serif; max-width: 1400px; margin: 40px auto; padding: 0 20px; color: #333; }
    h1 { color: #1a1a2e; border-bottom: 3px solid #2196f3; padding-bottom: 10px; }
    h2 { color: #16213e; margin-top: 32px; }
    table { border-collapse: collapse; width: 100%; margin-bottom: 24px; }
    th { background: #1a1a2e; color: white; padding: 10px 14px; text-align: left; }
    td { padding: 8px 14px; border-bottom: 1px solid #e0e0e0; }
    tr:nth-child(even) { background: #f9f9f9; }
    pre { background: #1a1a2e; color: #d4d4d4; padding: 16px; border-radius: 6px; font-size: 13px; overflow-x:auto; }
    .best { background: #e8f5e9; font-weight: bold; }
    """

    def best_idx(vals: list) -> int | None:
        """Return index of the maximum numeric value, or None."""
        try:
            nums = [float(v) if v != "—" else -1 for v in vals]
            best = max(nums)
            return nums.index(best) if best >= 0 else None
        except Exception:
            return None

    table_html = ""
    table_html += "<table><thead><tr>" + "".join(f"<th>{h}</th>" for h in (["Metric"] + run_names)) + "</tr></thead><tbody>"
    for k in metric_keys:
        vals = [_fmt(s.get("aggregate", {}).get(k)) for s in summaries]
        bi = best_idx(vals)
        row_cells = [_METRIC_LABELS.get(k, k)]
        for i, v in enumerate(vals):
            cls = ' class="best"' if i == bi else ""
            row_cells.append(f"<td{cls}>{v}</td>")
        table_html += "<tr>" + f"<td>{row_cells[0]}</td>" + "".join(row_cells[1:]) + "</tr>"
    table_html += "</tbody></table>"

    config_html = ""
    for name, s in zip(run_names, summaries):
        config_html += f"<h3>{_html_escape(name)}</h3><pre>{_html_escape(json.dumps(s.get('config', {}), indent=2, default=str))}</pre>"

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <title>Evaluation Comparison</title>
  <style>{css}</style>
</head>
<body>
  <h1>Evaluation Comparison Report</h1>
  <p><strong>Generated:</strong> {datetime.utcnow().isoformat()}Z &nbsp;|&nbsp; <strong>Runs:</strong> {', '.join(_html_escape(n) for n in run_names)}</p>
  <h2>Side-by-Side Aggregate Metrics</h2>
  {table_html}
  <h2>Configuration Snapshots</h2>
  {config_html}
</body>
</html>"""

    html_path = _REPORTS_DIR / f"{output_name}.html"
    html_path.write_text(html, encoding="utf-8")

    return md_path, html_path
