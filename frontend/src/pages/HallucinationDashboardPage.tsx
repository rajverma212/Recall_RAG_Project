import { useState, useCallback } from 'react'
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
    response.confidence.citation_accuracy ?? (supportedCount + 0.5 * partialCount) / total

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

function getEvidenceForClaim(markers: number[], citations: Citation[]): Citation[] {
  return citations.filter((c) => markers.includes(c.marker))
}

function LegendDot({ className, label }: { className: string; label: string }) {
  return (
    <span className="flex items-center gap-1 text-slate-400">
      <span className={`h-1.5 w-1.5 rounded-full ${className}`} />
      {label}
    </span>
  )
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
    <div className="h-full overflow-y-auto px-8 py-7">
      <h1 className="text-[26px] font-bold leading-tight tracking-tight text-slate-100">
        Hallucination
      </h1>
      <p className="mt-0.5 text-[13px] text-slate-400">
        Verify claims against cited sources and detect unsupported statements
      </p>

      {/* Query form */}
      <form onSubmit={handleSubmit} className="mt-6 space-y-3">
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
          className="min-h-[88px] w-full resize-none rounded-xl border border-surface-200 bg-surface-800 px-4 py-3 text-[14px] text-slate-100 placeholder-slate-600 outline-none transition-colors focus:border-accent-500/60"
        />
        <button
          type="submit"
          disabled={isLoading || !question.trim()}
          className="rounded-[10px] bg-accent-500 px-5 py-2 text-[14px] font-semibold text-surface-900 transition-colors hover:bg-accent-400 disabled:cursor-not-allowed disabled:opacity-50"
        >
          {isLoading ? 'Analyzing…' : 'Analyze'}
        </button>
      </form>

      {error && (
        <div className="mt-6 rounded-xl border border-danger-400/30 bg-danger-900/30 px-4 py-3 text-[13px] text-danger-400">
          {error.message}
        </div>
      )}

      {response && metrics && (
        <div className="mt-6 animate-fade-in space-y-3.5">
          {/* Trust metric cards */}
          <div className="grid grid-cols-1 gap-3.5 sm:grid-cols-3">
            <MetricCard
              label="Citation Accuracy"
              value={`${(metrics.citationAccuracy * 100).toFixed(1)}%`}
              sub={`${metrics.supportedCount} supported · ${metrics.partialCount} partial`}
              accent
              size="md"
            />
            <MetricCard
              label="Unsupported Claim Rate"
              value={`${(metrics.unsupportedRate * 100).toFixed(1)}%`}
              sub={`${metrics.unsupportedCount} of ${metrics.total} claims`}
              size="md"
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
              size="md"
            />
          </div>

          {/* Answer heatmap */}
          <div className="rounded-[14px] border border-surface-200 bg-surface-800 p-5">
            <div className="mb-3 flex items-center justify-between">
              <h2 className="section-label">Answer — Claim Coverage</h2>
              <div className="flex items-center gap-3 text-[11px]">
                <LegendDot className="bg-success-400" label="Supported" />
                <LegendDot className="bg-warning-400" label="Partial" />
                <LegendDot className="bg-danger-400" label="Unsupported" />
              </div>
            </div>
            <Heatmap answer={response.answer} verifications={response.verifications} />
          </div>

          {/* Claim verification table */}
          {response.verifications.length > 0 && (
            <div className="overflow-hidden rounded-[14px] border border-surface-200 bg-surface-800">
              <div className="border-b border-surface-50 px-5 py-4">
                <h2 className="section-label">Claim Verification ({metrics.total} claims)</h2>
              </div>
              <div className="overflow-x-auto">
                <table className="w-full text-[12px]">
                  <thead>
                    <tr className="border-b border-surface-50">
                      {['Claim', 'Markers', 'Status', 'Supporting Evidence', 'Rationale'].map((h) => (
                        <th
                          key={h}
                          className="px-4 py-3 text-left text-[10px] font-medium uppercase tracking-label text-slate-600"
                        >
                          {h}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {response.verifications.map((v, i) => {
                      const evidence = getEvidenceForClaim(v.cited_markers, response.citations)
                      return (
                        <tr
                          key={i}
                          className={`border-b border-surface-50 align-top transition-colors last:border-0 ${
                            v.status === 'unsupported'
                              ? 'bg-danger-400/[0.05]'
                              : v.status === 'partially_supported'
                                ? 'bg-warning-400/[0.05]'
                                : 'hover:bg-surface-850'
                          }`}
                        >
                          <td className="px-4 py-3 leading-relaxed text-slate-100">{v.claim}</td>
                          <td className="px-4 py-3">
                            {v.cited_markers.length > 0 ? (
                              <div className="flex flex-wrap gap-1">
                                {v.cited_markers.map((m) => (
                                  <span
                                    key={m}
                                    className="inline-flex h-4 w-4 items-center justify-center rounded-sm bg-accent-500/15 text-[10px] font-bold text-accent-500"
                                  >
                                    {m}
                                  </span>
                                ))}
                              </div>
                            ) : (
                              <span className="text-slate-600">—</span>
                            )}
                          </td>
                          <td className="px-4 py-3">
                            <StatusBadge status={v.status} />
                          </td>
                          <td className="px-4 py-3">
                            {evidence.length > 0 ? (
                              <div className="space-y-1.5">
                                {evidence.slice(0, 2).map((c) => (
                                  <div key={c.marker}>
                                    <p className="mb-0.5 text-[10px] text-slate-600">
                                      [{c.marker}] {c.source_file}
                                      {c.page_number != null ? ` p.${c.page_number}` : ''}
                                    </p>
                                    <p className="line-clamp-3 italic leading-relaxed text-slate-400">
                                      &ldquo;{c.quote ?? c.text}&rdquo;
                                    </p>
                                  </div>
                                ))}
                                {evidence.length > 2 && (
                                  <p className="text-slate-600">+{evidence.length - 2} more</p>
                                )}
                              </div>
                            ) : (
                              <span className="italic text-slate-600">No citations</span>
                            )}
                          </td>
                          <td className="px-4 py-3 leading-relaxed text-slate-600">{v.rationale}</td>
                        </tr>
                      )
                    })}
                  </tbody>
                </table>
              </div>
            </div>
          )}

          {response.verifications.length === 0 && (
            <div className="rounded-[14px] border border-surface-200 bg-surface-800 px-5 py-8 text-center">
              <p className="text-[13px] text-slate-400">
                No claim verifications were produced for this response.
              </p>
            </div>
          )}
        </div>
      )}

      {!response && !isLoading && !error && (
        <div className="mt-10">
          <EmptyState
            icon={<span className="font-serif text-[42px] italic">!</span>}
            title="Hallucination Analysis"
            description="Submit a question to see per-claim verification status, citation accuracy, and hallucination risk metrics."
          />
        </div>
      )}
    </div>
  )
}
