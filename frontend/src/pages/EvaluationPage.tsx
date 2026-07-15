import { useState } from 'react'
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  CartesianGrid,
  Legend,
} from 'recharts'
import {
  useEvaluations,
  useEvaluation,
  useEvaluationJob,
  useStartEvaluation,
} from '../hooks'
import { MetricCard } from '../components/MetricCard'
import { StatusBadge } from '../components/StatusBadge'
import { Spinner } from '../components/Spinner'
import { EmptyState } from '../components/EmptyState'
import type { EvaluationRun } from '../lib/types'

const TOOLTIP_STYLE = {
  background: '#181510',
  border: '1px solid #252119',
  borderRadius: 10,
  fontSize: 11,
  color: '#ede8df',
} as const

function pct(v: number | null): string {
  if (v == null) return '—'
  return `${(v * 100).toFixed(1)}%`
}

const CATEGORIES = ['direct', 'multi_hop', 'ambiguous', 'no_answer'] as const

// Metric definitions — power the hover hints on each MetricCard and keep the
// UI self-documenting (mirrors evaluation/README.md).
const METRIC_HINTS: Record<string, string> = {
  retrieval_recall:
    'Of the source documents needed to answer each question, the fraction the retriever actually surfaced. Low → tune chunking or dense/sparse weights.',
  answer_correctness:
    "How closely answers match ground truth: must-include facts (60%) + word overlap (40%). Low → improve the prompt or generation model.",
  faithfulness:
    "Fraction of the answer's claims that are backed by the cited context. Low → the model is hallucinating beyond its sources.",
  citation_accuracy:
    'Stricter faithfulness — only fully-supported claims count. Measures how precise the citations are.',
  confidence_calibration:
    '1 − Expected Calibration Error: how well the confidence score tracks actual correctness. Low → the model is over- or under-confident.',
}

const CATEGORY_LABELS: Record<string, string> = {
  direct: 'Single-hop factual questions with a clear answer.',
  multi_hop: 'Questions that need facts stitched from multiple sections or docs.',
  ambiguous: 'Broad-scope questions that require synthesis.',
  no_answer: 'Questions the corpus cannot answer — the system should abstain.',
}

export function EvaluationPage() {
  const { data: runs, isLoading, error } = useEvaluations()
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const { data: detail, isLoading: detailLoading } = useEvaluation(selectedId)
  const { data: job } = useEvaluationJob()
  const startEval = useStartEvaluation()

  const [showHelp, setShowHelp] = useState(false)

  const running = job?.status === 'running' || startEval.isPending
  const jobError = job?.status === 'error' ? job.error : null

  const selected = runs?.find((r) => r.id === selectedId) ?? null

  const chartData = (runs ?? []).map((r: EvaluationRun) => ({
    name: r.name.length > 20 ? r.name.slice(0, 18) + '…' : r.name,
    retrieval: r.retrieval_recall != null ? +(r.retrieval_recall * 100).toFixed(1) : null,
    correctness: r.answer_correctness != null ? +(r.answer_correctness * 100).toFixed(1) : null,
    faithfulness: r.faithfulness != null ? +(r.faithfulness * 100).toFixed(1) : null,
    citation: r.citation_accuracy != null ? +(r.citation_accuracy * 100).toFixed(1) : null,
  }))

  type ExRes = NonNullable<typeof detail>['results'][number]
  const grouped: Record<string, ExRes[]> = {}
  if (detail) {
    for (const r of detail.results) {
      ;(grouped[r.category] ??= []).push(r)
    }
  }

  return (
    <div className="flex h-full flex-col">
      <div className="flex items-start justify-between gap-4 px-8 pb-5 pt-7">
        <div>
          <h1 className="text-[26px] font-bold leading-tight tracking-tight text-slate-100">
            Evaluations
          </h1>
          <p className="mt-0.5 text-[13px] text-slate-400">
            Compare evaluation runs and per-example results
          </p>
        </div>
        <div className="flex flex-shrink-0 items-center gap-2">
          <button
            onClick={() => setShowHelp((v) => !v)}
            className="rounded-lg border border-surface-200 px-3 py-2 text-[12px] font-medium text-slate-400 transition-colors hover:border-surface-100 hover:text-slate-200"
          >
            {showHelp ? 'Hide guide' : 'How it works'}
          </button>
          <button
            onClick={() => startEval.mutate(undefined)}
            disabled={running}
            className="flex items-center gap-2 rounded-lg bg-accent-500 px-4 py-2 text-[12px] font-semibold text-surface-900 transition-opacity hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-60"
          >
            {running && <Spinner />}
            {running ? 'Running…' : 'Run evaluation'}
          </button>
        </div>
      </div>

      {(showHelp || (runs && runs.length === 0 && !isLoading)) && (
        <div className="mx-8 mb-4 rounded-[14px] border border-surface-200 bg-surface-800 p-5">
          <h2 className="section-label mb-2">What this is</h2>
          <p className="text-[13px] leading-relaxed text-slate-300">
            Each <span className="text-slate-100">run</span> replays a fixed set of{' '}
            <span className="text-slate-100">70 labeled questions</span> through the RAG pipeline and
            scores the answers on five metrics. Use it to <span className="text-slate-100">prove a
            change</span> — a new chunking strategy, retrieval weights, or prompt — actually improved
            answer quality before shipping, and to see which question types are weakest.
          </p>
          <div className="mt-4 grid gap-x-6 gap-y-2 text-[12px] sm:grid-cols-2">
            {Object.entries(METRIC_HINTS).map(([key, hint]) => (
              <div key={key} className="flex gap-2">
                <span className="mt-1.5 h-1.5 w-1.5 flex-shrink-0 rounded-full bg-accent-500" />
                <p className="text-slate-400">
                  <span className="font-medium capitalize text-slate-200">
                    {key.replace(/_/g, ' ')}
                  </span>{' '}
                  — {hint}
                </p>
              </div>
            ))}
          </div>
          <p className="mt-4 border-t border-surface-100 pt-3 text-[12px] text-slate-500">
            <span className="font-medium text-slate-400">When to run:</span> after any change to
            retrieval, chunking, or prompts. Then compare runs side-by-side in the chart, and click a
            run to see which questions passed or failed. An example passes when recall ≥ 0.5,
            correctness ≥ 0.4, and faithfulness ≥ 0.5.
          </p>
        </div>
      )}

      {(running || jobError) && (
        <div
          className={`mx-8 mb-4 flex items-center gap-3 rounded-[12px] border px-4 py-3 text-[12px] ${
            jobError
              ? 'border-danger-400/40 bg-danger-400/5 text-danger-400'
              : 'border-accent-500/40 bg-accent-500/5 text-slate-300'
          }`}
        >
          {running && <Spinner />}
          {running ? (
            <span>
              Running <span className="text-slate-100">{job?.name ?? 'evaluation'}</span> across 70
              examples — this can take a minute. Results appear automatically when done.
            </span>
          ) : (
            <span>Evaluation failed: {jobError}</span>
          )}
        </div>
      )}

      <div className="flex min-h-0 flex-1 overflow-hidden">
        {/* Run list */}
        <aside className="w-64 flex-shrink-0 overflow-y-auto border-r border-surface-200">
          {isLoading && (
            <div className="flex justify-center py-8">
              <Spinner />
            </div>
          )}
          {error && <p className="p-4 text-[12px] text-danger-400">{error.message}</p>}
          {runs && runs.length === 0 && (
            <EmptyState
              icon={<span className="font-serif text-[34px] italic">∅</span>}
              title="No runs"
              description="Click “Run evaluation” to create one."
            />
          )}
          {runs &&
            runs.map((run) => (
              <button
                key={run.id}
                onClick={() => setSelectedId(run.id)}
                className={`w-full border-b border-surface-50 px-4 py-3 text-left transition-colors hover:bg-surface-850 ${
                  selectedId === run.id ? 'border-l-2 border-l-accent-500 bg-surface-850' : ''
                }`}
              >
                <p className="truncate text-[13px] font-medium text-slate-100">{run.name}</p>
                <p className="mt-0.5 truncate text-[10px] text-slate-500">{run.dataset}</p>
                <p className="mt-1 text-[10px] text-slate-600">
                  {new Date(run.created_at).toLocaleDateString()}
                </p>
              </button>
            ))}
        </aside>

        {/* Detail panel */}
        <div className="flex-1 space-y-3.5 overflow-y-auto px-8 py-6">
          {!selectedId && runs && runs.length > 0 && (
            <>
              {chartData.length > 0 && (
                <div className="rounded-[14px] border border-surface-200 bg-surface-800 p-5">
                  <h2 className="section-label mb-4">Run Comparison</h2>
                  <ResponsiveContainer width="100%" height={220}>
                    <BarChart data={chartData} margin={{ top: 0, right: 4, left: -20, bottom: 0 }}>
                      <CartesianGrid strokeDasharray="3 3" stroke="#1e1b15" vertical={false} />
                      <XAxis dataKey="name" tick={{ fontSize: 9, fill: '#5c5448' }} axisLine={{ stroke: '#1e1b15' }} tickLine={false} />
                      <YAxis tick={{ fontSize: 9, fill: '#5c5448' }} unit="%" axisLine={false} tickLine={false} />
                      <Tooltip contentStyle={TOOLTIP_STYLE} cursor={{ fill: 'rgba(217,122,58,.06)' }} formatter={(v: number) => `${v}%`} />
                      <Legend wrapperStyle={{ fontSize: 11, color: '#9b9280' }} />
                      <Bar dataKey="retrieval" name="Retrieval Recall" fill="#d97a3a" radius={[3, 3, 0, 0]} />
                      <Bar dataKey="correctness" name="Correctness" fill="#6dd49a" radius={[3, 3, 0, 0]} />
                      <Bar dataKey="faithfulness" name="Faithfulness" fill="#e8be52" radius={[3, 3, 0, 0]} />
                      <Bar dataKey="citation" name="Citation Acc." fill="#f0a877" radius={[3, 3, 0, 0]} />
                    </BarChart>
                  </ResponsiveContainer>
                </div>
              )}
              <EmptyState
                icon={<span className="font-serif text-[34px] italic">→</span>}
                title="Select a run"
                description="Click a run on the left to see per-example results."
              />
            </>
          )}

          {selectedId && selected && (
            <>
              <div className="grid grid-cols-2 gap-3.5 md:grid-cols-5">
                <MetricCard label="Retrieval Recall" value={pct(selected.retrieval_recall)} size="md" hint={METRIC_HINTS.retrieval_recall} />
                <MetricCard label="Correctness" value={pct(selected.answer_correctness)} size="md" hint={METRIC_HINTS.answer_correctness} />
                <MetricCard label="Faithfulness" value={pct(selected.faithfulness)} size="md" hint={METRIC_HINTS.faithfulness} />
                <MetricCard label="Citation Acc." value={pct(selected.citation_accuracy)} size="md" hint={METRIC_HINTS.citation_accuracy} />
                <MetricCard label="Conf. Calibration" value={pct(selected.confidence_calibration)} size="md" hint={METRIC_HINTS.confidence_calibration} />
              </div>

              {detailLoading && (
                <div className="flex justify-center py-8">
                  <Spinner />
                </div>
              )}

              {detail &&
                CATEGORIES.map((cat) => {
                  const rows = grouped[cat]
                  if (!rows || rows.length === 0) return null
                  const passed = rows.filter((r) => r.passed).length
                  return (
                    <div key={cat} className="overflow-hidden rounded-[14px] border border-surface-200 bg-surface-800">
                      <div className="flex items-center justify-between border-b border-surface-50 px-5 py-3">
                        <span className="section-label" title={CATEGORY_LABELS[cat]}>{cat.replace('_', ' ')}</span>
                        <span className="text-[12px] text-slate-500">
                          {passed}/{rows.length} passed
                        </span>
                      </div>
                      <table className="w-full text-[12px]">
                        <thead>
                          <tr className="border-b border-surface-50">
                            {['Question', 'Predicted', 'Pass'].map((h) => (
                              <th
                                key={h}
                                className="px-4 py-2.5 text-left text-[10px] font-medium uppercase tracking-label text-slate-600"
                              >
                                {h}
                              </th>
                            ))}
                          </tr>
                        </thead>
                        <tbody>
                          {rows.map((r) => (
                            <tr key={r.example_id} className="border-b border-surface-50 last:border-0 hover:bg-surface-850">
                              <td className="max-w-xs px-4 py-3 text-slate-100">
                                <p className="line-clamp-2">{r.question}</p>
                              </td>
                              <td className="max-w-xs px-4 py-3 text-slate-400">
                                <p className="line-clamp-2">{r.predicted_answer}</p>
                              </td>
                              <td className="px-4 py-3">
                                <StatusBadge status={r.passed ? 'ready' : 'error'} />
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  )
                })}
            </>
          )}

          {!selectedId && (!runs || runs.length === 0) && !isLoading && (
            <EmptyState
              icon={<span className="font-serif text-[34px] italic">∅</span>}
              title="No evaluation runs yet"
              description="Click “Run evaluation” above to score the pipeline against 70 labeled questions."
            />
          )}
        </div>
      </div>
    </div>
  )
}
