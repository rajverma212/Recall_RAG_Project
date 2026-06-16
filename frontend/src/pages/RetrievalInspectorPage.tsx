import { useState } from 'react'
import { Search, Clock } from 'lucide-react'
import { useAsk } from '../hooks'
import { Spinner } from '../components/Spinner'
import { EmptyState } from '../components/EmptyState'
import type { TraceResult, TraceStage } from '../lib/types'

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
      <div className="w-16 h-1.5 rounded-full bg-surface-800">
        <div
          className="h-1.5 rounded-full bg-accent-500"
          style={{ width: `${pct}%` }}
        />
      </div>
      <span className="tabular-nums text-xs text-slate-400">{score.toFixed(4)}</span>
    </div>
  )
}

function StagePanel({
  stage,
  rerankedIds,
}: {
  stage: TraceStage
  rerankedIds: Set<string>
}) {
  return (
    <div className="flex flex-col h-full">
      <div className="flex items-center justify-between px-3 py-2 border-b border-slate-700/50">
        <span className="text-xs font-semibold text-slate-300">{stage.name}</span>
        <span className="flex items-center gap-1 text-[10px] text-slate-500">
          <Clock size={10} />
          {stage.elapsed_ms.toFixed(0)} ms
        </span>
      </div>
      <div className="flex-1 overflow-y-auto">
        {stage.results.length === 0 ? (
          <p className="p-4 text-xs text-slate-600">No results</p>
        ) : (
          stage.results.map((r, i) => (
            <ChunkRow key={r.chunk_id} result={r} index={i} survived={rerankedIds.has(r.chunk_id)} />
          ))
        )}
      </div>
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
      className={`border-b border-slate-800 p-3 cursor-pointer hover:bg-surface-800/50 transition-colors ${
        survived ? 'border-l-2 border-l-success-500' : ''
      }`}
      onClick={() => setExpanded((e) => !e)}
    >
      <div className="flex items-start gap-2">
        <span
          className={`flex-shrink-0 mt-0.5 h-5 w-5 rounded text-[10px] font-bold flex items-center justify-center
            ${survived ? 'bg-success-500/20 text-success-400' : 'bg-surface-800 text-slate-500'}`}
        >
          {index + 1}
        </span>
        <div className="flex-1 min-w-0">
          <p className="text-xs font-medium text-slate-300 truncate">{result.source_file}</p>
          <div className="flex items-center gap-2 mt-0.5">
            {result.page_number != null && (
              <span className="text-[10px] text-slate-500">p.{result.page_number}</span>
            )}
            {result.section_title && (
              <span className="text-[10px] text-slate-500 truncate">· {result.section_title}</span>
            )}
          </div>
          <div className="mt-1">
            <ScoreCell score={result.score} />
          </div>
          {expanded && (
            <p className="mt-2 text-[11px] text-slate-500 leading-relaxed">{result.text}</p>
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
    <div className="flex h-full flex-col">
      <div className="border-b border-slate-700/50 px-6 py-4">
        <h1 className="text-lg font-semibold text-slate-100">Retrieval Inspector</h1>
        <p className="text-xs text-slate-500 mt-0.5">Inspect the full retrieval pipeline per-stage</p>
      </div>

      <div className="border-b border-slate-700/50 px-6 py-4">
        <form onSubmit={handleSubmit} className="flex gap-3">
          <input
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
            placeholder="Enter a query to inspect retrieval..."
            className="flex-1 rounded-lg border border-slate-700/60 bg-surface-850 px-3 py-2 text-sm text-slate-200 placeholder-slate-600 outline-none focus:border-accent-500/60 focus:ring-1 focus:ring-accent-500/30"
          />
          <button
            type="submit"
            disabled={askMutation.isPending || !question.trim()}
            className="flex items-center gap-2 rounded-lg bg-accent-500 px-4 py-2 text-sm font-semibold text-white transition-colors hover:bg-accent-600 disabled:opacity-50"
          >
            {askMutation.isPending ? <Spinner size="sm" /> : <Search size={15} />}
            Inspect
          </button>
        </form>
      </div>

      {!trace && !askMutation.isPending && (
        <EmptyState
          icon={<Search size={28} />}
          title="No trace yet"
          description="Submit a query above to inspect all retrieval stages."
        />
      )}

      {askMutation.isPending && (
        <div className="flex flex-1 items-center justify-center">
          <Spinner size="lg" />
        </div>
      )}

      {trace && (
        <div className="flex flex-1 overflow-hidden">
          {/* Stage tabs (mobile) / columns (desktop) */}
          <div className="flex flex-1 flex-col overflow-hidden">
            {/* Stage selector */}
            <div className="flex gap-1 border-b border-slate-700/50 px-4 pt-3 pb-0 md:hidden">
              {STAGES.map((s) => (
                <button
                  key={s}
                  onClick={() => setActiveStage(s)}
                  className={`rounded-t-lg px-3 py-1.5 text-xs font-medium transition-colors ${
                    activeStage === s
                      ? 'bg-surface-850 text-slate-200 border border-b-0 border-slate-700/50'
                      : 'text-slate-500 hover:text-slate-300'
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
            <div className="hidden md:grid md:grid-cols-4 flex-1 overflow-hidden divide-x divide-slate-700/50">
              {STAGES.map((s) => (
                <div key={s} className="flex flex-col overflow-hidden">
                  <div className="flex items-center justify-between px-3 py-2 border-b border-slate-700/50 bg-surface-900">
                    <span className="text-xs font-semibold text-slate-200">{STAGE_LABELS[s]}</span>
                    <div className="flex items-center gap-2">
                      <span className="text-[10px] text-slate-500">{trace[s].results.length} results</span>
                      <span className="flex items-center gap-0.5 text-[10px] text-slate-600">
                        <Clock size={9} />
                        {trace[s].elapsed_ms.toFixed(0)}ms
                      </span>
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

            {/* Mobile: active tab content */}
            <div className="md:hidden flex-1 overflow-y-auto bg-surface-900">
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
        </div>
      )}
    </div>
  )
}
