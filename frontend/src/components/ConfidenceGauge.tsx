import type { ConfidenceScore } from '../lib/types'
import { ScoreBar } from './ScoreBar'

interface ConfidenceGaugeProps {
  confidence: ConfidenceScore
}

function ringColor(score: number): { ring: string; text: string; glow: string } {
  if (score >= 70) return { ring: '#22c55e', text: 'text-success-400', glow: 'shadow-success-500/30' }
  if (score >= 40) return { ring: '#f59e0b', text: 'text-warning-400', glow: 'shadow-warning-500/30' }
  return { ring: '#ef4444', text: 'text-danger-400', glow: 'shadow-danger-500/30' }
}

export function ConfidenceGauge({ confidence }: ConfidenceGaugeProps) {
  const score = Math.round(confidence.score * 100)
  const { ring, text, glow } = ringColor(score)

  // SVG ring
  const r = 44
  const circ = 2 * Math.PI * r
  const dash = (score / 100) * circ

  return (
    <div className="rounded-xl border border-slate-700/50 bg-surface-850 p-5">
      <h3 className="text-xs font-semibold uppercase tracking-wider text-slate-500 mb-4">
        Confidence Score
      </h3>
      <div className="flex items-center gap-6">
        {/* Ring gauge */}
        <div className={`relative flex-shrink-0 rounded-full shadow-lg ${glow}`}>
          <svg width={108} height={108} viewBox="0 0 108 108">
            {/* Background track */}
            <circle
              cx={54}
              cy={54}
              r={r}
              fill="none"
              stroke="#1e293b"
              strokeWidth={10}
            />
            {/* Progress arc — starts at top (rotate -90deg) */}
            <circle
              cx={54}
              cy={54}
              r={r}
              fill="none"
              stroke={ring}
              strokeWidth={10}
              strokeLinecap="round"
              strokeDasharray={`${dash} ${circ}`}
              transform="rotate(-90 54 54)"
              style={{ transition: 'stroke-dasharray 0.8s ease' }}
            />
          </svg>
          <div className="absolute inset-0 flex flex-col items-center justify-center">
            <span className={`text-2xl font-bold tabular-nums ${text}`}>{score}</span>
            <span className="text-[10px] text-slate-500 uppercase tracking-wider">/ 100</span>
          </div>
        </div>

        {/* Breakdown bars */}
        <div className="flex-1 space-y-3">
          <ScoreBar label="Retrieval" value={confidence.retrieval_confidence} />
          <ScoreBar label="Reranker" value={confidence.reranker_confidence} />
          <ScoreBar label="Citation Coverage" value={confidence.citation_coverage} />
          <ScoreBar label="Citation Accuracy" value={confidence.citation_accuracy} />
        </div>
      </div>
    </div>
  )
}
