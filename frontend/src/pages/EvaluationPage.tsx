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
import { useEvaluations, useEvaluation } from '../hooks'
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

export function EvaluationPage() {
  const { data: runs, isLoading, error } = useEvaluations()
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const { data: detail, isLoading: detailLoading } = useEvaluation(selectedId)

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
      <div className="px-8 pb-5 pt-7">
        <h1 className="text-[26px] font-bold leading-tight tracking-tight text-slate-100">
          Evaluations
        </h1>
        <p className="mt-0.5 text-[13px] text-slate-400">
          Compare evaluation runs and per-example results
        </p>
      </div>

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
              description="Run an evaluation first."
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
                <MetricCard label="Retrieval Recall" value={pct(selected.retrieval_recall)} size="md" />
                <MetricCard label="Correctness" value={pct(selected.answer_correctness)} size="md" />
                <MetricCard label="Faithfulness" value={pct(selected.faithfulness)} size="md" />
                <MetricCard label="Citation Acc." value={pct(selected.citation_accuracy)} size="md" />
                <MetricCard label="Conf. Calibration" value={pct(selected.confidence_calibration)} size="md" />
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
                        <span className="section-label">{cat.replace('_', ' ')}</span>
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
              title="No evaluation runs"
              description="Run an evaluation to see results here."
            />
          )}
        </div>
      </div>
    </div>
  )
}
