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
      className={`rounded-[14px] border p-4 transition-all duration-300 ${
        highlighted
          ? 'border-accent-500/60 bg-accent-500/[0.06]'
          : 'border-surface-200 bg-surface-850 hover:border-accent-500/40 hover:bg-accent-500/[0.06]'
      }`}
    >
      <div className="flex items-start gap-3">
        {/* Marker ring */}
        <div className="flex h-10 w-10 flex-shrink-0 items-center justify-center rounded-full border-2 border-accent-500 text-[13px] font-semibold text-slate-100">
          {citation.marker}
        </div>
        <div className="min-w-0 flex-1">
          <div className="truncate text-[13px] font-semibold text-slate-100">
            {citation.source_file}
          </div>
          {(citation.page_number != null || citation.section_title) && (
            <div className="mt-0.5 truncate text-[11px] text-slate-600">
              {citation.page_number != null && <>p.{citation.page_number}</>}
              {citation.page_number != null && citation.section_title && ' · '}
              {citation.section_title}
            </div>
          )}
          {citation.quote && (
            <blockquote className="mt-2 border-l-2 border-accent-500 pl-3 text-[12px] italic leading-relaxed text-slate-400">
              "{citation.quote}"
            </blockquote>
          )}
        </div>
      </div>
    </div>
  )
}
