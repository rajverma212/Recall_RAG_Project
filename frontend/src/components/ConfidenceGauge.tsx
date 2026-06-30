import type { ConfidenceScore } from '../lib/types'
import { ScoreBar } from './ScoreBar'

interface ConfidenceGaugeProps {
  confidence: ConfidenceScore
}

export function ConfidenceGauge({ confidence }: ConfidenceGaugeProps) {
  // Backend `confidence.score` is already on a 0–100 scale (see
  // compute_confidence: `score = 100 * weighted_sum`). Do NOT multiply again.
  const score = Math.round(confidence.score)
  const deg = score * 3.6

  return (
    <div className="rounded-[14px] border border-surface-200 bg-surface-800 p-5">
      <h3 className="section-label mb-4">Confidence Score</h3>
      <div className="flex items-center gap-6">
        {/* Donut ring — conic-gradient drives the amber stop at score*3.6deg */}
        <div
          className="relative flex h-[88px] w-[88px] flex-shrink-0 items-center justify-center rounded-full"
          style={{
            background: `conic-gradient(from -90deg, #d97a3a 0 ${deg}deg, #252119 ${deg}deg 360deg)`,
            boxShadow: '0 0 26px rgba(217,122,58,.22)',
          }}
        >
          <div className="flex h-[66px] w-[66px] flex-col items-center justify-center rounded-full bg-surface-800">
            <span className="font-serif text-3xl leading-none text-slate-100">{score}</span>
            <span className="text-[10px] text-slate-400">/ 100</span>
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
