import { useEffect, useState } from 'react'
import { useAsk } from '../hooks'
import { Spinner } from '../components/Spinner'
import { EmptyState } from '../components/EmptyState'
import type { Trace, TraceResult } from '../lib/types'

const STAGES = ['dense', 'bm25', 'rrf', 'reranked'] as const
type StageName = (typeof STAGES)[number]

const STAGE_LABELS: Record<StageName, string> = {
  dense: 'Dense',
  bm25: 'BM25',
  rrf: 'RRF Fusion',
  reranked: 'Reranked',
}

const STAGE_SUBTITLES: Record<StageName, string> = {
  dense: 'meaning · embeddings',
  bm25: 'exact keywords',
  rrf: 'merged ranking',
  reranked: 'final · cross-encoder',
}

// Queries chosen to contrast the stages: keyword-heavy favors BM25,
// paraphrase favors dense, mixed shows RRF reconciling both.
const SAMPLE_QUERIES: { label: string; query: string }[] = [
  { label: 'keyword-heavy · BM25 shines', query: 'SEV-1 incident response and resolution targets' },
  { label: 'semantic · Dense shines', query: 'Who can I turn to for help during my first week?' },
  { label: 'mixed · hybrid wins', query: 'What is the 401(k) employer match?' },
]

function ScoreCell({ score }: { score: number }) {
  const pct = Math.min(100, score * 100)
  return (
    <div className="flex items-center gap-2">
      <div className="h-1 w-16 rounded-full bg-surface-200">
        <div className="h-1 origin-left rounded-full bg-accent-500" style={{ width: `${pct}%` }} />
      </div>
      <span className="tabular-nums text-[11px] text-slate-400">{score.toFixed(4)}</span>
    </div>
  )
}

/** Per-stage rank lookup: chunk_id → 1-based rank. */
function rankMap(results: TraceResult[]): Map<string, number> {
  return new Map(results.map((r, i) => [r.chunk_id, i + 1]))
}

function RankDelta({ from, to }: { from: number | undefined; to: number }) {
  if (from == null) {
    return <span className="text-[10px] font-medium text-accent-500/70">new</span>
  }
  const delta = from - to
  if (delta === 0) return <span className="text-[10px] text-slate-600">=</span>
  return delta > 0 ? (
    <span className="text-[10px] font-medium text-success-400">↑{delta}</span>
  ) : (
    <span className="text-[10px] font-medium text-slate-500">↓{-delta}</span>
  )
}

function ChunkRow({
  result,
  index,
  survived,
  annotation,
}: {
  result: TraceResult
  index: number
  survived: boolean
  annotation?: React.ReactNode
}) {
  const [expanded, setExpanded] = useState(false)
  return (
    <div
      className={`cursor-pointer border-b border-surface-50 p-3 transition-colors hover:bg-surface-850 ${
        survived ? 'border-l-2 border-l-success-400' : ''
      }`}
      onClick={() => setExpanded((e) => !e)}
    >
      <div className="flex items-start gap-2">
        <span
          className={`mt-0.5 flex h-5 w-5 flex-shrink-0 items-center justify-center rounded font-serif text-[12px] italic ${
            survived ? 'text-success-400' : 'text-accent-500/60'
          }`}
        >
          {index + 1}
        </span>
        <div className="min-w-0 flex-1">
          <div className="flex items-center justify-between gap-2">
            <p className="truncate text-[12px] font-medium text-slate-100">{result.source_file}</p>
            {annotation}
          </div>
          <div className="mt-0.5 flex items-center gap-2">
            {result.page_number != null && (
              <span className="text-[10px] text-slate-600">p.{result.page_number}</span>
            )}
            {result.section_title && (
              <span className="truncate text-[10px] text-slate-600">· {result.section_title}</span>
            )}
          </div>
          <div className="mt-1.5">
            <ScoreCell score={result.score} />
          </div>
          {expanded && (
            <p className="mt-2 text-[11px] leading-relaxed text-slate-500">{result.text}</p>
          )}
        </div>
      </div>
    </div>
  )
}

/** Shown only when a query has been pending a while (cold reranker load). */
function SlowQueryHint() {
  const [slow, setSlow] = useState(false)
  useEffect(() => {
    const t = setTimeout(() => setSlow(true), 6000)
    return () => clearTimeout(t)
  }, [])
  if (!slow) return null
  return (
    <p className="max-w-md text-center text-[12px] leading-relaxed text-slate-500">
      Still working — the first query after a backend restart loads the reranker model into
      memory, which can take a minute. Warm queries finish in a few seconds.
    </p>
  )
}

/** Derived, human-readable takeaways from the trace — the "so what" strip. */
function SummaryStrip({ trace }: { trace: Trace }) {
  const denseIds = new Set(trace.dense.results.map((r) => r.chunk_id))
  const bm25Ids = new Set(trace.bm25.results.map((r) => r.chunk_id))
  const overlap = [...denseIds].filter((id) => bm25Ids.has(id)).length

  const rrfRanks = rankMap(trace.rrf.results)
  const bestPromo = trace.reranked.results.reduce<{ from: number; to: number } | null>(
    (best, r, i) => {
      const from = rrfRanks.get(r.chunk_id)
      if (from != null && from - (i + 1) > (best ? best.from - best.to : 0)) {
        return { from, to: i + 1 }
      }
      return best
    },
    null,
  )

  const totalMs = STAGES.reduce((sum, s) => sum + trace[s].elapsed_ms, 0)
  const scores = trace.reranked.results.map((r) => r.score)
  const top = scores[0]
  const spread = scores.length > 1 ? top - scores[scores.length - 1] : 0

  const items: { label: string; value: string }[] = [
    {
      label: 'Retriever agreement',
      value: `${overlap} of ${Math.min(denseIds.size, bm25Ids.size)} chunks found by both`,
    },
    {
      label: 'Biggest rerank move',
      value: bestPromo ? `#${bestPromo.from} → #${bestPromo.to}` : 'no promotions',
    },
    {
      label: 'Top score / spread',
      value: top != null ? `${top.toFixed(2)} / ${spread.toFixed(2)}` : '—',
    },
    { label: 'Pipeline latency', value: `${totalMs}ms` },
  ]

  return (
    <div className="mt-5 grid grid-cols-2 gap-2 md:grid-cols-4">
      {items.map((it) => (
        <div
          key={it.label}
          className="rounded-xl border border-surface-200 bg-surface-800 px-3.5 py-2.5"
        >
          <p className="text-[10px] uppercase tracking-wide text-slate-600">{it.label}</p>
          <p className="mt-0.5 truncate text-[13px] font-medium text-slate-100">{it.value}</p>
        </div>
      ))}
    </div>
  )
}

export function RetrievalInspectorPage() {
  const [question, setQuestion] = useState('')
  const [activeStage, setActiveStage] = useState<StageName>('reranked')
  const askMutation = useAsk()

  const submitQuery = (q: string) => {
    if (!q.trim() || askMutation.isPending) return
    askMutation.mutate({ question: q, include_trace: true })
  }

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    submitQuery(question)
  }

  const trace = askMutation.data?.trace
  const rerankedIds = new Set(trace?.reranked.results.slice(0, 5).map((r) => r.chunk_id) ?? [])
  const denseRanks = trace ? rankMap(trace.dense.results) : new Map<string, number>()
  const bm25Ranks = trace ? rankMap(trace.bm25.results) : new Map<string, number>()
  const rrfRanks = trace ? rankMap(trace.rrf.results) : new Map<string, number>()

  // Per-stage row annotation: provenance for RRF, rank delta for reranked,
  // "missed by the other retriever" badge for dense/bm25 survivors.
  const annotationFor = (stage: StageName, r: TraceResult, index: number): React.ReactNode => {
    if (stage === 'rrf') {
      const d = denseRanks.get(r.chunk_id)
      const b = bm25Ranks.get(r.chunk_id)
      return (
        <span className="flex flex-shrink-0 gap-1 text-[10px] tabular-nums">
          <span className={d != null ? 'text-slate-500' : 'text-slate-700'}>
            {d != null ? `D#${d}` : 'D–'}
          </span>
          <span className={b != null ? 'text-slate-500' : 'text-slate-700'}>
            {b != null ? `B#${b}` : 'B–'}
          </span>
        </span>
      )
    }
    if (stage === 'reranked') {
      return <RankDelta from={rrfRanks.get(r.chunk_id)} to={index + 1} />
    }
    // dense / bm25: flag survivors the *other* retriever missed entirely.
    if (rerankedIds.has(r.chunk_id)) {
      const other = stage === 'dense' ? bm25Ranks : denseRanks
      if (!other.has(r.chunk_id)) {
        return (
          <span className="flex-shrink-0 rounded bg-success-400/10 px-1.5 py-0.5 text-[9px] font-medium text-success-400">
            only found here
          </span>
        )
      }
    }
    return null
  }

  return (
    <div className="flex h-full flex-col px-8 py-7">
      <h1 className="text-[26px] font-bold leading-tight tracking-tight text-slate-100">
        Retrieval Inspector
      </h1>
      <p className="mt-0.5 text-[13px] text-slate-400">
        Watch a query flow through all four retrieval stages, left to right. A{' '}
        <span className="text-success-400">green edge</span> means the chunk survived into the
        final answer context; arrows show how the reranker moved it.
      </p>

      <form onSubmit={handleSubmit} className="mt-6 flex gap-3">
        <input
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          placeholder="Enter a query to inspect retrieval..."
          className="flex-1 rounded-xl border border-surface-200 bg-surface-800 px-4 py-2.5 text-[14px] text-slate-100 placeholder-slate-600 outline-none focus:border-accent-500/60"
        />
        <button
          type="submit"
          disabled={askMutation.isPending || !question.trim()}
          className="rounded-[10px] bg-accent-500 px-5 py-2 text-[14px] font-semibold text-surface-900 transition-colors hover:bg-accent-400 disabled:opacity-50"
        >
          {askMutation.isPending ? 'Inspecting…' : 'Inspect'}
        </button>
      </form>

      {!askMutation.isPending && (
        <div className="mt-3 flex flex-wrap items-center gap-2">
          <span className="text-[11px] text-slate-600">Try:</span>
          {SAMPLE_QUERIES.map((s) => (
            <button
              key={s.query}
              type="button"
              onClick={() => {
                setQuestion(s.query)
                submitQuery(s.query)
              }}
              className="group rounded-full border border-surface-200 bg-surface-800 px-3 py-1 text-[11px] text-slate-400 transition-colors hover:border-accent-500/60 hover:text-slate-100"
              title={s.query}
            >
              {s.query.length > 44 ? `${s.query.slice(0, 44)}…` : s.query}
              <span className="ml-1.5 text-[9px] uppercase tracking-wide text-slate-600 group-hover:text-accent-500/80">
                {s.label}
              </span>
            </button>
          ))}
        </div>
      )}

      {askMutation.error && (
        <div className="mt-4 rounded-xl border border-danger-400/30 bg-danger-900/30 px-4 py-3 text-[13px] text-danger-400">
          {(askMutation.error as Error).message}
        </div>
      )}

      {!trace && !askMutation.isPending && !askMutation.error && (
        <div className="mt-8">
          <EmptyState
            icon={<span className="font-serif text-[42px] italic">⌕</span>}
            title="No trace yet"
            description="Submit a query above — or click a sample — to see how dense and keyword retrieval disagree, how RRF merges them, and what the reranker keeps."
          />
        </div>
      )}

      {askMutation.isPending && (
        <div className="flex flex-1 flex-col items-center justify-center gap-4">
          <Spinner size="lg" />
          <SlowQueryHint />
        </div>
      )}

      {trace && (
        <>
          <SummaryStrip trace={trace} />

          <div className="mt-3 flex min-h-0 flex-1 flex-col overflow-hidden rounded-[14px] border border-surface-200 bg-surface-800">
            {/* Mobile stage selector */}
            <div className="flex gap-1 border-b border-surface-50 px-4 pt-3 md:hidden">
              {STAGES.map((s) => (
                <button
                  key={s}
                  onClick={() => setActiveStage(s)}
                  className={`rounded-t-lg px-3 py-1.5 text-[12px] font-medium transition-colors ${
                    activeStage === s ? 'text-accent-500' : 'text-slate-500 hover:text-slate-100'
                  }`}
                >
                  {STAGE_LABELS[s]}
                  <span className="ml-1.5 tabular-nums text-[10px] text-slate-600">
                    ({trace[s].results.length})
                  </span>
                </button>
              ))}
            </div>

            {/* Desktop: 4 columns */}
            <div className="hidden min-h-0 flex-1 divide-x divide-surface-50 overflow-hidden md:grid md:grid-cols-4">
              {STAGES.map((s) => (
                <div key={s} className="flex min-h-0 flex-col overflow-hidden">
                  <div className="border-b border-surface-50 bg-surface-850 px-3 py-2">
                    <div className="flex items-center justify-between">
                      <span className="section-label">{STAGE_LABELS[s]}</span>
                      <div className="flex items-center gap-2 text-[10px] text-slate-600">
                        <span>{trace[s].results.length} results</span>
                        <span className="tabular-nums">{trace[s].elapsed_ms.toFixed(0)}ms</span>
                      </div>
                    </div>
                    <p className="mt-0.5 text-[10px] text-slate-600">{STAGE_SUBTITLES[s]}</p>
                  </div>
                  <div className="flex-1 overflow-y-auto">
                    {trace[s].results.map((r, i) => (
                      <ChunkRow
                        key={r.chunk_id}
                        result={r}
                        index={i}
                        survived={s !== 'reranked' && rerankedIds.has(r.chunk_id)}
                        annotation={annotationFor(s, r, i)}
                      />
                    ))}
                  </div>
                </div>
              ))}
            </div>

            {/* Mobile: active tab */}
            <div className="min-h-0 flex-1 overflow-y-auto md:hidden">
              <p className="border-b border-surface-50 px-4 py-2 text-[10px] text-slate-600">
                {STAGE_SUBTITLES[activeStage]}
              </p>
              {trace[activeStage].results.map((r, i) => (
                <ChunkRow
                  key={r.chunk_id}
                  result={r}
                  index={i}
                  survived={activeStage !== 'reranked' && rerankedIds.has(r.chunk_id)}
                  annotation={annotationFor(activeStage, r, i)}
                />
              ))}
            </div>
          </div>
        </>
      )}
    </div>
  )
}
