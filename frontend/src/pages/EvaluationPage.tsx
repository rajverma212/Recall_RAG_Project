import { useState } from 'react'
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  CartesianGrid,
} from 'recharts'
import { useEvaluations, useEvaluation } from '../hooks'
import { MetricCard } from '../components/MetricCard'
import { StatusBadge } from '../components/StatusBadge'
import { Spinner } from '../components/Spinner'
import { EmptyState } from '../components/EmptyState'
import { BarChart2 } from 'lucide-react'
import type { EvaluationRun } from '../lib/types'

function pct(v: number | null): string {
  if (v == null) return '—'
  return `${(v * 100).toFixed(1)}%`
}

const CATEGORIES = ['direct', 'multi_hop', 'ambiguous', 'no_answer'] as const

export function EvaluationPage() {
  const { data: runs, isLoading, error } = useEvaluations()
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const { data: detail, isLoading: detailLoading } = useEvaluation(selectedId)

  const selected = runs?.find((r) => r.id === selectedId) ?? null

  // Build chart data from all runs
  const chartData = (runs ?? []).map((r: EvaluationRun) => ({
    name: r.name.length > 20 ? r.name.slice(0, 18) + '…' : r.name,
    retrieval: r.retrieval_recall != null ? +(r.retrieval_recall * 100).toFixed(1) : null,
    correctness: r.answer_correctness != null ? +(r.answer_correctness * 100).toFixed(1) : null,
    faithfulness: r.faithfulness != null ? +(r.faithfulness * 100).toFixed(1) : null,
    citation: r.citation_accuracy != null ? +(r.citation_accuracy * 100).toFixed(1) : null,
  }))

  // Group results by category
  type ExRes = NonNullable<typeof detail>['results'][number]
  const grouped: Record<string, ExRes[]> = {}
  if (detail) {
    for (const r of detail.results) {
      ;(grouped[r.category] ??= []).push(r)
    }
  }

  return (
    <div className="flex h-full flex-col">
      <div className="border-b border-slate-700/50 px-6 py-4">
        <h1 className="text-lg font-semibold text-slate-100">Evaluations</h1>
        <p className="text-xs text-slate-500 mt-0.5">Compare evaluation runs and per-example results</p>
      </div>

      <div className="flex flex-1 overflow-hidden">
        {/* Run list */}
        <aside className="w-64 flex-shrink-0 border-r border-slate-700/50 overflow-y-auto">
          {isLoading && (
            <div className="flex justify-center py-8">
              <Spinner />
            </div>
          )}
          {error && <p className="p-4 text-xs text-danger-400">{error.message}</p>}
          {runs && runs.length === 0 && (
            <EmptyState
              icon={<BarChart2 size={24} />}
              title="No runs"
              description="Run an evaluation first."
            />
          )}
          {runs &&
            runs.map((run) => (
              <button
                key={run.id}
                onClick={() => setSelectedId(run.id)}
                className={`w-full border-b border-slate-800 px-4 py-3 text-left transition-colors hover:bg-surface-800 ${
                  selectedId === run.id ? 'bg-surface-800 border-l-2 border-l-accent-500' : ''
                }`}
              >
                <p className="text-xs font-medium text-slate-200 truncate">{run.name}</p>
                <p className="mt-0.5 text-[10px] text-slate-500 truncate">{run.dataset}</p>
                <p className="mt-1 text-[10px] text-slate-600">
                  {new Date(run.created_at).toLocaleDateString()}
                </p>
              </button>
            ))}
        </aside>

        {/* Detail panel */}
        <div className="flex-1 overflow-y-auto px-6 py-6 space-y-6">
          {!selectedId && runs && runs.length > 0 && (
            <>
              {/* Cross-run bar chart */}
              {chartData.length > 0 && (
                <div className="rounded-xl border border-slate-700/50 bg-surface-850 p-5">
                  <h2 className="text-xs font-semibold uppercase tracking-wider text-slate-500 mb-4">
                    Run Comparison
                  </h2>
                  <ResponsiveContainer width="100%" height={220}>
                    <BarChart data={chartData} margin={{ top: 0, right: 0, left: -20, bottom: 0 }}>
                      <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" />
                      <XAxis dataKey="name" tick={{ fontSize: 10, fill: '#64748b' }} />
                      <YAxis tick={{ fontSize: 10, fill: '#64748b' }} unit="%" />
                      <Tooltip
                        contentStyle={{ background: '#0f172a', border: '1px solid #334155', borderRadius: 8, fontSize: 11 }}
                        formatter={(v: number) => `${v}%`}
                      />
                      <Bar dataKey="retrieval" name="Retrieval Recall" fill="#6366f1" radius={[3, 3, 0, 0]} />
                      <Bar dataKey="correctness" name="Correctness" fill="#22c55e" radius={[3, 3, 0, 0]} />
                      <Bar dataKey="faithfulness" name="Faithfulness" fill="#f59e0b" radius={[3, 3, 0, 0]} />
                      <Bar dataKey="citation" name="Citation Acc." fill="#818cf8" radius={[3, 3, 0, 0]} />
                    </BarChart>
                  </ResponsiveContainer>
                </div>
              )}
              <EmptyState
                icon={<BarChart2 size={28} />}
                title="Select a run"
                description="Click a run on the left to see per-example results."
              />
            </>
          )}

          {selectedId && selected && (
            <>
              {/* Metric cards */}
              <div className="grid grid-cols-2 gap-3 md:grid-cols-5">
                <MetricCard label="Retrieval Recall" value={pct(selected.retrieval_recall)} />
                <MetricCard label="Correctness" value={pct(selected.answer_correctness)} />
                <MetricCard label="Faithfulness" value={pct(selected.faithfulness)} />
                <MetricCard label="Citation Acc." value={pct(selected.citation_accuracy)} />
                <MetricCard label="Conf. Calibration" value={pct(selected.confidence_calibration)} />
              </div>

              {detailLoading && (
                <div className="flex justify-center py-8">
                  <Spinner />
                </div>
              )}

              {detail && (
                <>
                  {/* Per-category tables */}
                  {CATEGORIES.map((cat) => {
                    const rows = grouped[cat]
                    if (!rows || rows.length === 0) return null
                    const passed = rows.filter((r) => r.passed).length
                    return (
                      <div key={cat} className="rounded-xl border border-slate-700/50 overflow-hidden">
                        <div className="flex items-center justify-between px-4 py-2.5 bg-surface-900 border-b border-slate-700/50">
                          <span className="text-xs font-semibold capitalize text-slate-300">
                            {cat.replace('_', ' ')}
                          </span>
                          <span className="text-xs text-slate-500">
                            {passed}/{rows.length} passed
                          </span>
                        </div>
                        <table className="w-full text-xs">
                          <thead>
                            <tr className="border-b border-slate-800">
                              {['Question', 'Predicted', 'Pass'].map((h) => (
                                <th
                                  key={h}
                                  className="px-3 py-2 text-left font-medium text-slate-500 text-[10px] uppercase"
                                >
                                  {h}
                                </th>
                              ))}
                            </tr>
                          </thead>
                          <tbody className="divide-y divide-slate-800">
                            {rows.map((r) => (
                              <tr key={r.example_id} className="hover:bg-surface-800/30">
                                <td className="px-3 py-2.5 text-slate-300 max-w-xs">
                                  <p className="line-clamp-2">{r.question}</p>
                                </td>
                                <td className="px-3 py-2.5 text-slate-400 max-w-xs">
                                  <p className="line-clamp-2">{r.predicted_answer}</p>
                                </td>
                                <td className="px-3 py-2.5">
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
            </>
          )}

          {!selectedId && (!runs || runs.length === 0) && !isLoading && (
            <EmptyState
              icon={<BarChart2 size={28} />}
              title="No evaluation runs"
              description="Run an evaluation to see results here."
            />
          )}
        </div>
      </div>
    </div>
  )
}
