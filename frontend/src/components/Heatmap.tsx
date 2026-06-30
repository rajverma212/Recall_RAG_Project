import type { Verification } from '../lib/types'
import { CitationChip } from './CitationChip'

interface HeatmapProps {
  answer: string
  verifications: Verification[]
  onCitationClick?: (marker: number) => void
  activeMarker?: number | null
}

const STATUS_STYLE: Record<string, string> = {
  supported: 'bg-success-400/10 text-slate-100 font-medium',
  partially_supported: 'bg-warning-400/10 text-slate-100',
  unsupported: 'bg-danger-400/10 text-slate-100',
}

/**
 * Sentence-level citation heatmap.
 * Splits the answer into sentences, then for each sentence finds the best-matching
 * verification by naive substring overlap and applies a tint.
 */
function matchSentence(sentence: string, verifications: Verification[]): Verification | undefined {
  // Find the verification whose claim best overlaps with this sentence
  let best: Verification | undefined
  let bestOverlap = 0
  for (const v of verifications) {
    // Count shared words
    const sWords = new Set(sentence.toLowerCase().split(/\W+/).filter(Boolean))
    const cWords = v.claim.toLowerCase().split(/\W+/).filter(Boolean)
    const overlap = cWords.filter((w) => sWords.has(w)).length
    if (overlap > bestOverlap) {
      bestOverlap = overlap
      best = v
    }
  }
  // Require at least 3 shared words to match
  return bestOverlap >= 3 ? best : undefined
}

function splitSentences(text: string): string[] {
  // Split on sentence-ending punctuation, keep the delimiter attached
  return text.match(/[^.!?]+[.!?]*/g) ?? [text]
}

export function Heatmap({ answer, verifications, onCitationClick, activeMarker }: HeatmapProps) {
  const sentences = splitSentences(answer)

  return (
    <div className="answer-text">
      {sentences.map((sentence, i) => {
        const match = matchSentence(sentence, verifications)
        const cls = match ? STATUS_STYLE[match.status] ?? '' : ''
        return (
          <span key={i} className={`${cls} rounded px-0.5 py-0.5`}>
            {sentence}
            {match &&
              match.cited_markers.map((m) => (
                <CitationChip
                  key={m}
                  marker={m}
                  onClick={() => onCitationClick?.(m)}
                  active={activeMarker === m}
                />
              ))}
            {' '}
          </span>
        )
      })}
    </div>
  )
}
