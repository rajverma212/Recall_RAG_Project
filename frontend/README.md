# RAG Platform Frontend

React + TypeScript + Vite + TailwindCSS SPA for the RAG Resume Platform.

## Prerequisites

- Node.js 18+

## Development

```bash
cd frontend
npm install
npm run dev
```

Opens at http://localhost:5173. Requests to `/v1/*` are proxied to the backend at `http://localhost:8000`.

## Production Build

```bash
npm run build
```

Output goes to `dist/`. The nginx reverse proxy (configured in `docker/nginx.conf`) serves the SPA and proxies `/v1/` to the backend container.

## Environment Variables

| Variable | Default | Description |
|---|---|---|
| `VITE_API_BASE` | `http://localhost:8000/v1` | Backend API base URL |

In production Docker, `VITE_API_BASE=/v1` (nginx handles the proxy).

## Pages

| Route | Page | Description |
|---|---|---|
| `/` | Ask | RAG query with streaming, confidence gauge, citation heatmap |
| `/retrieval` | Retrieval Inspector | 4-stage pipeline view (Dense / BM25 / RRF / Reranked) |
| `/documents` | Documents | Drag-drop ingest, strategy selector, document table |
| `/evaluations` | Evaluations | Run comparison bar chart, per-example results by category |
| `/analytics` | Analytics | Queries-by-day, confidence histogram, cost tracking |
| `/experiments` | Experiments & Prompts | Experiment configs, prompt version viewer |
