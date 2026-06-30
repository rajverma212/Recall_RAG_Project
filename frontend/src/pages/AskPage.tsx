import { useRef, useCallback } from 'react'
import { useAskContext } from '../context/AskContext'
import { ConfidenceGauge } from '../components/ConfidenceGauge'
import { Heatmap } from '../components/Heatmap'
import { SourceCard } from '../components/SourceCard'
import { StatusBadge } from '../components/StatusBadge'
import type { AskRequest, AskResponse } from '../lib/types'

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
  // Query state lives in AskContext (above the router) so a completed answer
  // survives navigating to other tabs and back. sourceRefs are DOM refs, so
  // they stay local — they are repopulated on each mount.
  const {
    question,
    setQuestion,
    streaming,
    setStreaming,
    activeMarker,
    setActiveMarker,
    askMutation,
    streamState,
  } = useAskContext()
  const sourceRefs = useRef<Record<number, HTMLDivElement | null>>({})

  const isLoading = streaming ? streamState.streaming : askMutation.isPending
  const response: AskResponse | null = streaming
    ? streamState.response
    : (askMutation.data ?? null)
  const error = streaming ? streamState.error : askMutation.error

  const runQuery = useCallback(
    (q: string) => {
      if (!q.trim() || isLoading) return
      setActiveMarker(null)
      const req: AskRequest = { question: q, include_trace: false }
      if (streaming) {
        streamState.submit(req)
      } else {
        askMutation.mutate(req)
      }
    },
    [isLoading, streaming, streamState, askMutation, setActiveMarker],
  )

  const handleSubmit = useCallback(
    (e: React.FormEvent) => {
      e.preventDefault()
      runQuery(question)
    },
    [question, runQuery],
  )

  const handleReset = useCallback(() => {
    setQuestion('')
    setActiveMarker(null)
    streamState.reset()
    askMutation.reset()
  }, [setQuestion, setActiveMarker, streamState, askMutation])

  const handleCitationClick = useCallback((marker: number) => {
    setActiveMarker(marker)
    sourceRefs.current[marker]?.scrollIntoView({ behavior: 'smooth', block: 'center' })
  }, [setActiveMarker])

  const handleAskNext = useCallback(
    (q: string) => {
      setQuestion(q)
      runQuery(q)
    },
    [setQuestion, runQuery],
  )

  const streamingText = streaming && streamState.streaming ? streamState.tokens : ''
  const answered = !!response
  const busy = isLoading || !!streamingText
  const askedQuestion = response?.question ?? question

  // Follow-up suggestions for the answered state. We don't get these from the
  // API, so surface a few sample questions other than the one just asked.
  const followUps = SAMPLE_QUESTIONS.filter((q) => q !== askedQuestion).slice(0, 3)

  return (
    <div className="h-full overflow-y-auto px-8 py-7">
      {/* ─── Answered / busy: query bar ─────────────────────────────── */}
      {(answered || busy) && (
        <div className="mb-4 flex items-start gap-4">
          <div className="flex-1 rounded-xl bg-surface-800 p-3.5">
            <p className="text-[15px] font-medium text-slate-100">{askedQuestion}</p>
            <div className="mt-1.5 text-[12px] text-slate-600">
              {response ? (
                <>
                  {response.latency_ms.toFixed(0)} ms <span className="px-1">·</span>$
                  {response.cost_usd.toFixed(5)} <span className="px-1">·</span>v
                  {response.prompt_version}
                </>
              ) : (
                <span className="inline-flex items-center gap-1.5">
                  <span className="h-1.5 w-1.5 animate-pulse-dot rounded-full bg-accent-500" />
                  Generating…
                </span>
              )}
            </div>
          </div>
          <button
            type="button"
            onClick={handleReset}
            className="rounded-[10px] border border-accent-500/40 bg-accent-500/10 px-3.5 py-2 text-[12px] font-medium text-accent-500 transition-colors hover:bg-accent-500/20"
          >
            New query
          </button>
        </div>
      )}

      {/* ─── Idle: title + ask form ─────────────────────────────────── */}
      {!answered && !busy && (
        <>
          <h1 className="text-[26px] font-bold leading-tight tracking-tight text-slate-100">Ask</h1>
          <p className="mt-0.5 text-[13px] text-slate-400">Query your document corpus with RAG</p>

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
              placeholder="Ask a question about your documents..."
              rows={3}
              className="min-h-[88px] w-full resize-none rounded-xl border border-surface-200 bg-surface-800 px-4 py-3 text-[14px] text-slate-100 placeholder-slate-600 outline-none transition-colors focus:border-accent-500/60"
            />
            <div className="flex items-center gap-3">
              <button
                type="submit"
                disabled={!question.trim()}
                className="rounded-[10px] bg-accent-500 px-5 py-2 text-[14px] font-semibold text-surface-900 transition-colors hover:bg-accent-400 disabled:cursor-not-allowed disabled:opacity-50"
              >
                Ask
              </button>
              <button
                type="button"
                onClick={() => setStreaming((s) => !s)}
                className={`rounded-[10px] border px-3.5 py-2 text-[13px] font-medium transition-colors ${
                  streaming
                    ? 'border-accent-500/40 bg-accent-500/10 text-accent-500'
                    : 'border-surface-200 bg-surface-800 text-slate-400 hover:text-slate-100'
                }`}
              >
                ⚡ Streaming {streaming ? 'ON' : 'OFF'}
              </button>
            </div>
          </form>

          {/* Sample questions (demo mode) */}
          <div className="mt-7 space-y-2.5">
            <p className="section-label">Sample questions</p>
            <div className="flex flex-wrap gap-2">
              {SAMPLE_QUESTIONS.map((q) => (
                <button
                  key={q}
                  type="button"
                  onClick={() => setQuestion(q)}
                  className="rounded-[20px] border border-surface-200 bg-surface-800 px-3.5 py-1.5 text-[13px] text-slate-400 transition-colors hover:border-accent-500/50 hover:text-accent-300"
                >
                  {q}
                </button>
              ))}
            </div>
          </div>

          {error && (
            <div className="mt-6 rounded-xl border border-danger-400/30 bg-danger-900/30 px-4 py-3 text-[13px] text-danger-400">
              {error.message}
            </div>
          )}

          {/* Empty hero */}
          {!error && (
            <div className="mt-20 flex flex-col items-center text-center">
              <div className="relative mb-5 flex h-[76px] w-[76px] items-center justify-center overflow-hidden rounded-[20px] border border-surface-200 bg-surface-800">
                <span className="font-serif text-[42px] italic leading-none text-accent-500">?</span>
                <span className="pointer-events-none absolute inset-y-0 -left-1/2 w-1/2 -skew-x-12 animate-shimmer bg-gradient-to-r from-transparent via-white/[0.04] to-transparent" />
              </div>
              <h3 className="text-base font-semibold text-slate-100">Ask anything</h3>
              <p className="mt-1.5 max-w-sm text-[13px] leading-relaxed text-slate-400">
                Type a question above to get a RAG-powered answer with citations and confidence
                scores.
              </p>
            </div>
          )}
        </>
      )}

      {/* ─── Streaming tokens (before full response) ────────────────── */}
      {streamingText && !response && (
        <div className="rounded-[14px] border border-surface-200 bg-surface-800 p-5">
          <p className="answer-text whitespace-pre-wrap">
            {streamingText}
            <span className="ml-0.5 inline-block h-4 w-0.5 animate-blink bg-accent-500 align-middle" />
          </p>
        </div>
      )}

      {error && (answered || busy) && (
        <div className="rounded-xl border border-danger-400/30 bg-danger-900/30 px-4 py-3 text-[13px] text-danger-400">
          {error.message}
        </div>
      )}

      {/* ─── Answered: two-column results ───────────────────────────── */}
      {response && (
        <div className="flex animate-fade-in gap-3.5">
          {/* Left column */}
          <div className="min-w-0 flex-1 space-y-3.5">
            <ConfidenceGauge confidence={response.confidence} />

            {/* Claim coverage */}
            <div className="rounded-[14px] border border-surface-200 bg-surface-800 p-5">
              <div className="mb-3 flex items-center justify-between">
                <h2 className="section-label">Answer — Claim Coverage</h2>
                <div className="flex items-center gap-3 text-[11px]">
                  <LegendDot className="bg-success-400" label="Supported" />
                  <LegendDot className="bg-warning-400" label="Partial" />
                  <LegendDot className="bg-danger-400" label="Unsupported" />
                </div>
              </div>
              <Heatmap
                answer={response.answer}
                verifications={response.verifications}
                onCitationClick={handleCitationClick}
                activeMarker={activeMarker}
              />
            </div>

            {/* Claim verification */}
            {response.verifications.length > 0 && (
              <div className="rounded-[14px] border border-surface-200 bg-surface-800 p-5">
                <h3 className="section-label mb-3">
                  Claim Verification ({response.verifications.length}{' '}
                  {response.verifications.length === 1 ? 'Claim' : 'Claims'})
                </h3>
                <div className="space-y-2.5">
                  {response.verifications.map((v, i) => (
                    <div key={i} className="flex items-start gap-3 rounded-[10px] bg-surface-850 p-3">
                      <div className="pt-0.5">
                        <StatusBadge status={v.status} />
                      </div>
                      <div className="min-w-0">
                        <p className="text-[13px] text-slate-100">{v.claim}</p>
                        {v.rationale && (
                          <p className="mt-1 text-[11.5px] text-slate-600">{v.rationale}</p>
                        )}
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>

          {/* Right column */}
          <div className="w-[268px] flex-shrink-0 space-y-3.5">
            {response.citations.length > 0 && (
              <div className="space-y-2.5">
                <p className="section-label">Sources ({response.citations.length})</p>
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
            )}

            {followUps.length > 0 && (
              <div className="rounded-[14px] border border-surface-200 bg-surface-800 p-5">
                <p className="section-label mb-3">Ask Next</p>
                <div className="space-y-2">
                  {followUps.map((q) => (
                    <button
                      key={q}
                      type="button"
                      onClick={() => handleAskNext(q)}
                      className="flex w-full items-start gap-2.5 rounded-[9px] border border-surface-100 bg-surface-850 px-3 py-2.5 text-left transition-colors hover:border-accent-500"
                    >
                      <span className="font-serif text-[17px] italic leading-none text-accent-500">
                        →
                      </span>
                      <span className="text-[12.5px] text-slate-400">{q}</span>
                    </button>
                  ))}
                </div>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  )
}

function LegendDot({ className, label }: { className: string; label: string }) {
  return (
    <span className="flex items-center gap-1 text-slate-400">
      <span className={`h-1.5 w-1.5 rounded-full ${className}`} />
      {label}
    </span>
  )
}
