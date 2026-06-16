interface CitationChipProps {
  marker: number
  onClick?: () => void
  active?: boolean
}

export function CitationChip({ marker, onClick, active }: CitationChipProps) {
  return (
    <button
      onClick={onClick}
      className={`inline-flex items-center justify-center rounded px-1.5 py-0.5 text-xs font-bold leading-none transition-colors cursor-pointer
        ${active
          ? 'bg-accent-500 text-white ring-1 ring-accent-400'
          : 'bg-accent-500/20 text-accent-400 hover:bg-accent-500/40'
        }`}
      aria-label={`Citation ${marker}`}
    >
      {marker}
    </button>
  )
}
