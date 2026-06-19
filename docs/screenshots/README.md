# Screenshots — capture guide

The README embeds these five images. Capture them from a running instance and
save them here with the exact filenames below; they will then render in the
README automatically.

## Setup (one time)

```bash
docker compose up -d --build
# seed answerable content so the pages show real data:
docker compose exec backend python scripts/seed_sample_data.py
```

Open http://localhost:5173 and ask a couple of questions first (e.g. one of the
**Sample questions** chips on the Ask page) so Analytics and System pages have data.

## Capture list

| Filename | Page (route) | What to show |
|---|---|---|
| `ask.png` | Ask (`/`) | An answered question with the confidence gauge, the trust-tinted answer heatmap, and the Sources cards expanded. |
| `retrieval.png` | Retrieval Inspector (`/retrieval`) | The 4-column trace (Dense · BM25 · RRF · Reranked) with score bars; survivors highlighted. |
| `hallucination.png` | Hallucination (`/hallucination`) | The trust metric cards + the Claim Verification table with supported/partial/unsupported rows. |
| `analytics.png` | Analytics (`/analytics`) | Summary cards (note Avg Confidence now reads a sane 0–100%) + the charts. |
| `system.png` | System (`/system`) | The Services dashboard with Healthy/Degraded pills, version, Qdrant vector count, and active providers. |

## Tips

- Use a viewport around **1440×900** for crisp, consistently-framed shots.
- macOS: `Cmd+Shift+4` then space to capture a window; or use the browser
  devtools device toolbar to set an exact viewport.
- Keep the dark theme (default) — it reads well in a portfolio.
- Optional: store full-page captures and crop to the main content area.
