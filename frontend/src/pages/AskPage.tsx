import { useState, useRef, useCallback } from 'react'
import { Send, Zap, ZapOff, AlertTriangle, Clock, DollarSign, MessageSquare } from 'lucide-react'
import { useAsk, useStreamingAsk } from '../hooks'
import { ConfidenceGauge } from '../components/ConfidenceGauge'
import { Heatmap } from '../components/Heatmap'
import { SourceCard } from '../components/SourceCard'
import { StatusBadge } from '../components/StatusBadge'
import { Spinner } from '../components/Spinner'
import { EmptyState } from '../components/EmptyState'
import type { AskResponse } from '../lib/types'

// Demo-mode starter prompts. Click to populate the question box — useful for
// walkthroughs and screenshots when the corpus content is unknown to a viewer.
const SAMPLE_QUESTIONS = [
  'What is software engineering?',
  'What are the four process activities?',
  'What is the difference between software engineering and computer science?',
  'Summarize this document.',
  'What skills are listed in this resume?',
]

export function AskPage() {
  const [question, setQuestion] = useState('')
  const [streaming, setStreaming] = useState(true)
  const [activeMarker, setActiveMarker] = useState<number | null>(null)
  const sourceRefs = useRef<Record<number, HTMLDivElement | null>>({})

  const askMutation = useAsk()
  const streamState = useStreamingAsk()

  const isLoading = streaming ? streamState.streaming : askMutation.isPending
  const response: AskResponse | null = streaming
    ? streamState.response
    : (askMutation.data ?? null)
  const error = streaming ? streamState.error : askMutation.error

  const handleSubmit = useCallback(
    (e: React.FormEvent) => {
      e.preventDefault()
      if (!question.trim() || isLoading) return
      setActiveMarker(null)
      if (streaming) {
        streamState.submit({ question, include_trace: false })
      } else {
        askMutation.mutate({ question, include_trace: false })
      }
    },
    [question, isLoading, streaming, streamState, askMutation],
  )

  const handleCitationClick = useCallback((marker: number) => {
    setActiveMarker(marker)
    const el = sourceRefs.current[marker]
    if (el) {
      el.scrollIntoView({ behavior: 'smooth', block: 'center' })
    }
  }, [])

  const streamingText = streaming && streamState.streaming ? streamState.tokens : ''
  const unsupported = response?.verifications.filter((v) => v.status === 'unsupported') ?? []

  return (
    <div className="flex h-full flex-col">
      {/* Header */}
      <div className="border-b border-slate-700/50 px-6 py-4">
        <h1 className="text-lg font-semibold text-slate-100">Ask</h1>
        <p className="text-xs text-slate-500 mt-0.5">Query your document corpus with RAG</p>
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
              placeholder="Ask a question about your documents..."
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
              {isLoading ? 'Thinking...' : 'Ask'}
            </button>

            {/* Streaming toggle */}
            <button
              type="button"
              onClick={() => setStreaming((s) => !s)}
              className={`flex items-center gap-1.5 rounded-lg border px-3 py-2 text-xs font-medium transition-colors ${
                streaming
                  ? 'border-accent-500/40 bg-accent-500/10 text-accent-400'
                  : 'border-slate-700/50 bg-surface-850 text-slate-400 hover:text-slate-200'
              }`}
            >
              {streaming ? <Zap size={13} /> : <ZapOff size={13} />}
              {streaming ? 'Streaming ON' : 'Streaming OFF'}
            </button>
          </div>
        </form>

        {/* Sample questions (demo mode) — shown before the first answer */}
        {!response && !streamingText && (
          <div className="space-y-2">
            <p className="text-[10px] font-semibold uppercase tracking-wider text-slate-500">
              Sample questions
            </p>
            <div className="flex flex-wrap gap-2">
              {SAMPLE_QUESTIONS.map((q) => (
                <button
                  key={q}
                  type="button"
                  onClick={() => setQuestion(q)}
                  disabled={isLoading}
                  className="rounded-full border border-slate-700/60 bg-surface-850 px-3 py-1.5 text-xs text-slate-400 transition-colors hover:border-accent-500/50 hover:text-accent-300 disabled:opacity-50"
                >
                  {q}
                </button>
              ))}
            </div>
          </div>
        )}

        {/* Streaming tokens (while loading) */}
        {streamingText && !response && (
          <div className="rounded-xl border border-slate-700/50 bg-surface-850 p-5">
            <div className="flex items-center gap-2 mb-3">
              <Spinner size="sm" />
              <span className="text-xs text-slate-500">Generating answer...</span>
            </div>
            <p className="text-sm text-slate-300 leading-relaxed whitespace-pre-wrap">
              {streamingText}
              <span className="ml-0.5 inline-block h-4 w-0.5 animate-pulse bg-accent-400" />
            </p>
          </div>
        )}

        {/* Error */}
        {error && (
          <div className="rounded-xl border border-danger-400/30 bg-danger-900/30 px-4 py-3 text-sm text-danger-400">
            {error.message}
          </div>
        )}

        {/* Full response */}
        {response && (
          <div className="space-y-5 animate-fade-in">
            {/* Meta row */}
            <div className="flex items-center gap-4 text-xs text-slate-500">
              <span className="flex items-center gap-1">
                <Clock size={12} />
                {response.latency_ms.toFixed(0)} ms
              </span>
              <span className="flex items-center gap-1">
                <DollarSign size={12} />
                ${response.cost_usd.toFixed(5)}
              </span>
              <span className="text-slate-600">v{response.prompt_version}</span>
            </div>

            {/* Confidence gauge */}
            <ConfidenceGauge confidence={response.confidence} />

            {/* Answer heatmap */}
            <div className="rounded-xl border border-slate-700/50 bg-surface-850 p-5">
              <div className="mb-3 flex items-center justify-between">
                <h2 className="text-xs font-semibold uppercase tracking-wider text-slate-500">
                  Answer
                </h2>
                <div className="flex items-center gap-2 text-[10px]">
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
                onCitationClick={handleCitationClick}
                activeMarker={activeMarker}
              />
            </div>

            {/* Hallucination / unsupported claims */}
            {unsupported.length > 0 && (
              <div className="rounded-xl border border-danger-400/30 bg-danger-900/20 p-4">
                <div className="flex items-center gap-2 mb-3">
                  <AlertTriangle size={14} className="text-danger-400" />
                  <h3 className="text-xs font-semibold text-danger-400 uppercase tracking-wider">
                    Unsupported Claims ({unsupported.length})
                  </h3>
                </div>
                <ul className="space-y-2">
                  {unsupported.map((v, i) => (
                    <li key={i} className="text-xs text-slate-400">
                      <span className="font-medium text-danger-400">Claim:</span> {v.claim}
                      <br />
                      <span className="text-slate-500">{v.rationale}</span>
                    </li>
                  ))}
                </ul>
              </div>
            )}

            {/* Verifications summary */}
            {response.verifications.length > 0 && (
              <div className="rounded-xl border border-slate-700/50 bg-surface-850 p-4">
                <h3 className="text-xs font-semibold uppercase tracking-wider text-slate-500 mb-3">
                  Claim Verification
                </h3>
                <div className="space-y-2">
                  {response.verifications.map((v, i) => (
                    <div key={i} className="flex items-start gap-3">
                      <StatusBadge status={v.status} />
                      <div>
                        <p className="text-xs text-slate-300">{v.claim}</p>
                        <p className="text-[11px] text-slate-500 mt-0.5">{v.rationale}</p>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Citations / Sources */}
            {response.citations.length > 0 && (
              <div>
                <h3 className="text-xs font-semibold uppercase tracking-wider text-slate-500 mb-3">
                  Sources ({response.citations.length})
                </h3>
                <div className="space-y-3">
                  {response.citations.map((c) => (
                    <div
                      key={c.marker}
                      ref={(el) => {
                        sourceRefs.current[c.marker] = el
                      }}
                    >
                      <SourceCard
                        citation={c}
                        highlighted={activeMarker === c.marker}
                        id={`source-${c.marker}`}
                      />
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        )}

        {/* Empty state */}
        {!response && !streamingText && !isLoading && !error && (
          <EmptyState
            icon={<MessageSquare size={28} />}
            title="Ask anything"
            description="Type a question above to get a RAG-powered answer with citations and confidence scores."
          />
        )}
      </div>
    </div>
  )
}

