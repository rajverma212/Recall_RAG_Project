import { FileText } from 'lucide-react'
import type { Citation } from '../lib/types'

interface SourceCardProps {
  citation: Citation
  highlighted?: boolean
  id?: string
}

export function SourceCard({ citation, highlighted, id }: SourceCardProps) {
  return (
    <div
      id={id}
      className={`rounded-xl border p-4 transition-all duration-300 ${
        highlighted
          ? 'border-accent-500/60 bg-accent-500/10 ring-1 ring-accent-500/40 shadow-lg shadow-accent-500/10'
          : 'border-slate-700/50 bg-surface-850'
      }`}
    >
      <div className="flex items-start gap-3">
        <div className="flex-shrink-0 mt-0.5">
          <span
            className={`inline-flex h-5 w-5 items-center justify-center rounded text-xs font-bold
              ${highlighted ? 'bg-accent-500 text-white' : 'bg-accent-500/20 text-accent-400'}`}
          >
            {citation.marker}
          </span>
        </div>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <FileText size={13} className="text-slate-500 flex-shrink-0" />
            <span className="text-sm font-medium text-slate-300 truncate">{citation.source_file}</span>
            {citation.page_number != null && (
              <span className="text-xs text-slate-500">p.{citation.page_number}</span>
            )}
            {citation.section_title && (
              <span className="text-xs text-slate-500 truncate">· {citation.section_title}</span>
            )}
          </div>
          {citation.quote && (
            <blockquote className="mt-2 border-l-2 border-accent-500/40 pl-3 text-xs italic text-slate-400 leading-relaxed">
              "{citation.quote}"
            </blockquote>
          )}
          <p className="mt-2 text-xs text-slate-500 leading-relaxed line-clamp-3">{citation.text}</p>
        </div>
      </div>
    </div>
  )
}
