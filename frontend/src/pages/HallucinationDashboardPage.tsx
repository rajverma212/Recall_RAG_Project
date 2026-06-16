import { useState, useCallback } from 'react'
import { Send, ShieldAlert, MessageSquare } from 'lucide-react'
import { useAsk } from '../hooks'
import { Heatmap } from '../components/Heatmap'
import { StatusBadge } from '../components/StatusBadge'
import { MetricCard } from '../components/MetricCard'
import { Spinner } from '../components/Spinner'
import { EmptyState } from '../components/EmptyState'
import type { AskResponse, Citation } from '../lib/types'

function computeMetrics(response: AskResponse) {
  const verifications = response.verifications
  const total = verifications.length
  if (total === 0) {
    return {
      citationAccuracy: response.confidence.citation_accuracy,
      unsupportedRate: 0,
      hallucinationRate: 0,
      supportedCount: 0,
      partialCount: 0,
      unsupportedCount: 0,
      total: 0,
    }
  }

  const supportedCount = verifications.filter((v) => v.status === 'supported').length
  const partialCount = verifications.filter((v) => v.status === 'partially_supported').length
  const unsupportedCount = verifications.filter((v) => v.status === 'unsupported').length

  // Citation accuracy: prefer backend value, fall back to (supported + 0.5*partial) / total
  const citationAccuracy =
    response.confidence.citation_accuracy ??
    (supportedCount + 0.5 * partialCount) / total

  const unsupportedRate = unsupportedCount / total
  const hallucinationRate = unsupportedRate

  return {
    citationAccuracy,
    unsupportedRate,
    hallucinationRate,
    supportedCount,
    partialCount,
    unsupportedCount,
    total,
  }
}

function getEvidenceForClaim(
  markers: number[],
  citations: Citation[],
): Citation[] {
  return citations.filter((c) => markers.includes(c.marker))
}

export function HallucinationDashboardPage() {
  const [question, setQuestion] = useState('')
  const askMutation = useAsk()
  const response: AskResponse | null = askMutation.data ?? null
  const isLoading = askMutation.isPending
  const error = askMutation.error

  const handleSubmit = useCallback(
    (e: React.FormEvent) => {
      e.preventDefault()
      if (!question.trim() || isLoading) return
      askMutation.mutate({ question, include_trace: false })
    },
    [question, isLoading, askMutation],
  )

  const metrics = response ? computeMetrics(response) : null

  return (
    <div className="flex h-full flex-col">
      {/* Header */}
      <div className="border-b border-slate-700/50 px-6 py-4">
        <div className="flex items-center gap-2">
          <ShieldAlert size={18} className="text-accent-400" />
          <h1 className="text-lg font-semibold text-slate-100">Hallucination Dashboard</h1>
        </div>
        <p className="text-xs text-slate-500 mt-0.5">
          Verify claims against cited sources and detect unsupported statements
        </p>
      </div>

      <div className="flex-1 overflow-y-auto px-6 py-6 space-y-6">
        {/* Query form */}
        <form onSubmit={handleSubmit} className="space-y-3">
          <div className="relative">
            <textarea
              value={question}
              onChange={(e) => setQuestion(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter' && !e.shiftKey) {
                  e.preventDefault()
                  void handleSubmit(e)
                }
              }}
              placeholder="Ask a question to analyze claim verifications..."
              rows={3}
              className="w-full resize-none rounded-xl border border-slate-700/60 bg-surface-850 px-4 py-3 pr-12 text-sm text-slate-200 placeholder-slate-600 outline-none transition-colors focus:border-accent-500/60 focus:ring-1 focus:ring-accent-500/30"
            />
          </div>
          <div className="flex items-center gap-3">
            <button
              type="submit"
              disabled={isLoading || !question.trim()}
              className="flex items-center gap-2 rounded-lg bg-accent-500 px-4 py-2 text-sm font-semibold text-white transition-colors hover:bg-accent-600 disabled:cursor-not-allowed disabled:opacity-50"
            >
              {isLoading ? <Spinner size="sm" /> : <Send size={15} />}
              {isLoading ? 'Analyzing...' : 'Analyze'}
            </button>
          </div>
        </form>

        {/* Error */}
        {error && (
          <div className="rounded-xl border border-danger-400/30 bg-danger-900/30 px-4 py-3 text-sm text-danger-400">
            {error.message}
          </div>
        )}

        {/* Results */}
        {response && metrics && (
          <div className="space-y-6 animate-fade-in">
            {/* Trust Metric Cards */}
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
              <MetricCard
                label="Citation Accuracy"
                value={`${(metrics.citationAccuracy * 100).toFixed(1)}%`}
                sub={`${metrics.supportedCount} supported · ${metrics.partialCount} partial`}
                accent
              />
              <MetricCard
                label="Unsupported Claim Rate"
                value={`${(metrics.unsupportedRate * 100).toFixed(1)}%`}
                sub={`${metrics.unsupportedCount} of ${metrics.total} claims`}
              />
              <MetricCard
                label="Hallucination Risk"
                value={`${(metrics.hallucinationRate * 100).toFixed(1)}%`}
                sub={
                  metrics.hallucinationRate === 0
                    ? 'No unsupported claims'
                    : metrics.hallucinationRate < 0.2
                    ? 'Low risk'
                    : metrics.hallucinationRate < 0.5
                    ? 'Moderate risk'
                    : 'High risk'
                }
              />
            </div>

            {/* Answer Heatmap */}
            <div className="rounded-xl border border-slate-700/50 bg-surface-850 p-5">
              <div className="mb-3 flex items-center justify-between">
                <h2 className="text-xs font-semibold uppercase tracking-wider text-slate-500">
                  Answer — Claim Coverage
                </h2>
                <div className="flex items-center gap-3 text-[10px]">
                  <span className="flex items-center gap-1">
                    <span className="h-2 w-2 rounded-sm bg-success-500/50" /> Supported
                  </span>
                  <span className="flex items-center gap-1">
                    <span className="h-2 w-2 rounded-sm bg-warning-400/50" /> Partial
                  </span>
                  <span className="flex items-center gap-1">
                    <span className="h-2 w-2 rounded-sm bg-danger-500/50" /> Unsupported
                  </span>
                </div>
              </div>
              <Heatmap
                answer={response.answer}
                verifications={response.verifications}
              />
            </div>

            {/* Claims Verification Table */}
            {response.verifications.length > 0 && (
              <div className="rounded-xl border border-slate-700/50 bg-surface-850 overflow-hidden">
                <div className="px-5 py-4 border-b border-slate-700/50">
                  <h2 className="text-xs font-semibold uppercase tracking-wider text-slate-500">
                    Claim Verification ({metrics.total} claims)
                  </h2>
                </div>
                <div className="overflow-x-auto">
                  <table className="w-full text-xs">
                    <thead>
                      <tr className="border-b border-slate-800 bg-surface-900/50">
                        <th className="px-4 py-3 text-left font-medium text-slate-500 uppercase tracking-wider w-1/3">
                          Claim
                        </th>
                        <th className="px-4 py-3 text-left font-medium text-slate-500 uppercase tracking-wider w-16">
                          Markers
                        </th>
                        <th className="px-4 py-3 text-left font-medium text-slate-500 uppercase tracking-wider w-28">
                          Status
                        </th>
                        <th className="px-4 py-3 text-left font-medium text-slate-500 uppercase tracking-wider w-1/4">
                          Supporting Evidence
                        </th>
                        <th className="px-4 py-3 text-left font-medium text-slate-500 uppercase tracking-wider">
                          Rationale
                        </th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-800">
                      {response.verifications.map((v, i) => {
                        const evidence = getEvidenceForClaim(
                          v.cited_markers,
                          response.citations,
                        )
                        return (
                          <tr
                            key={i}
                            className={`align-top transition-colors ${
                              v.status === 'unsupported'
                                ? 'bg-danger-900/10 hover:bg-danger-900/20'
                                : v.status === 'partially_supported'
                                ? 'bg-warning-900/10 hover:bg-warning-900/20'
                                : 'hover:bg-surface-800/50'
                            }`}
                          >
                            {/* Claim */}
                            <td className="px-4 py-3 text-slate-300 leading-relaxed">
                              {v.claim}
                            </td>

                            {/* Citation markers */}
                            <td className="px-4 py-3">
                              {v.cited_markers.length > 0 ? (
                                <div className="flex flex-wrap gap-1">
                                  {v.cited_markers.map((m) => (
                                    <span
                                      key={m}
                                      className="inline-flex items-center justify-center h-4 w-4 rounded-sm bg-accent-500/20 text-[10px] font-bold text-accent-400"
                                    >
                                      {m}
                                    </span>
                                  ))}
                                </div>
                              ) : (
                                <span className="text-slate-600">—</span>
                              )}
                            </td>

                            {/* Status */}
                            <td className="px-4 py-3">
                              <StatusBadge status={v.status} />
                            </td>

                            {/* Supporting evidence (quote or text from cited chunks) */}
                            <td className="px-4 py-3">
                              {evidence.length > 0 ? (
                                <div className="space-y-1.5">
                                  {evidence.slice(0, 2).map((c) => (
                                    <div key={c.marker}>
                                      <p className="text-[10px] text-slate-500 mb-0.5">
                                        [{c.marker}] {c.source_file}
                                        {c.page_number != null
                                          ? ` p.${c.page_number}`
                                          : ''}
                                      </p>
                                      <p className="text-slate-400 italic leading-relaxed line-clamp-3">
                                        &ldquo;{c.quote ?? c.text}&rdquo;
                                      </p>
                                    </div>
                                  ))}
                                  {evidence.length > 2 && (
                                    <p className="text-slate-600">
                                      +{evidence.length - 2} more
                                    </p>
                                  )}
                                </div>
                              ) : (
                                <span className="text-slate-600 italic">No citations</span>
                              )}
                            </td>

                            {/* Rationale */}
                            <td className="px-4 py-3 text-slate-500 leading-relaxed">
                              {v.rationale}
                            </td>
                          </tr>
                        )
                      })}
                    </tbody>
                  </table>
                </div>
              </div>
            )}

            {/* No verifications message */}
            {response.verifications.length === 0 && (
              <div className="rounded-xl border border-slate-700/50 bg-surface-850 px-5 py-8 text-center">
                <p className="text-sm text-slate-500">
                  No claim verifications were produced for this response.
                </p>
              </div>
            )}
          </div>
        )}

        {/* Empty state */}
        {!response && !isLoading && !error && (
          <EmptyState
            icon={<MessageSquare size={28} />}
            title="Hallucination Analysis"
            description="Submit a question to see per-claim verification status, citation accuracy, and hallucination risk metrics."
          />
        )}
      </div>
    </div>
  )
}
