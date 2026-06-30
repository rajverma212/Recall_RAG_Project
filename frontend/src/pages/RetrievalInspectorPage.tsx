import { useState } from 'react'
import { useAsk } from '../hooks'
import { Spinner } from '../components/Spinner'
import { EmptyState } from '../components/EmptyState'
import type { TraceResult } from '../lib/types'

const STAGES = ['dense', 'bm25', 'rrf', 'reranked'] as const
type StageName = (typeof STAGES)[number]

const STAGE_LABELS: Record<StageName, string> = {
  dense: 'Dense',
  bm25: 'BM25',
  rrf: 'RRF Fusion',
  reranked: 'Reranked',
}

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

function ChunkRow({
  result,
  index,
  survived,
}: {
  result: TraceResult
  index: number
  survived: boolean
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
          <p className="truncate text-[12px] font-medium text-slate-100">{result.source_file}</p>
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

export function RetrievalInspectorPage() {
  const [question, setQuestion] = useState('')
  const [activeStage, setActiveStage] = useState<StageName>('reranked')
  const askMutation = useAsk()

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    if (!question.trim() || askMutation.isPending) return
    askMutation.mutate({ question, include_trace: true })
  }

  const trace = askMutation.data?.trace
  const rerankedIds = new Set(trace?.reranked.results.slice(0, 5).map((r) => r.chunk_id) ?? [])

  return (
    <div className="flex h-full flex-col px-8 py-7">
      <h1 className="text-[26px] font-bold leading-tight tracking-tight text-slate-100">
        Retrieval Inspector
      </h1>
      <p className="mt-0.5 text-[13px] text-slate-400">Inspect the full retrieval pipeline per-stage</p>

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
            description="Submit a query above to inspect all retrieval stages."
          />
        </div>
      )}

      {askMutation.isPending && (
        <div className="flex flex-1 items-center justify-center">
          <Spinner size="lg" />
        </div>
      )}

      {trace && (
        <div className="mt-5 flex min-h-0 flex-1 flex-col overflow-hidden rounded-[14px] border border-surface-200 bg-surface-800">
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
                <div className="flex items-center justify-between border-b border-surface-50 bg-surface-850 px-3 py-2.5">
                  <span className="section-label">{STAGE_LABELS[s]}</span>
                  <div className="flex items-center gap-2 text-[10px] text-slate-600">
                    <span>{trace[s].results.length} results</span>
                    <span className="tabular-nums">{trace[s].elapsed_ms.toFixed(0)}ms</span>
                  </div>
                </div>
                <div className="flex-1 overflow-y-auto">
                  {trace[s].results.map((r, i) => (
                    <ChunkRow
                      key={r.chunk_id}
                      result={r}
                      index={i}
                      survived={s !== 'reranked' && rerankedIds.has(r.chunk_id)}
                    />
                  ))}
                </div>
              </div>
            ))}
          </div>

          {/* Mobile: active tab */}
          <div className="min-h-0 flex-1 overflow-y-auto md:hidden">
            {trace[activeStage].results.map((r, i) => (
              <ChunkRow
                key={r.chunk_id}
                result={r}
                index={i}
                survived={activeStage !== 'reranked' && rerankedIds.has(r.chunk_id)}
              />
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
