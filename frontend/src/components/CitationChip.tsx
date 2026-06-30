interface CitationChipProps {
  marker: number
  onClick?: () => void
  active?: boolean
}

export function CitationChip({ marker, onClick, active }: CitationChipProps) {
  return (
    <sup
      onClick={onClick}
      role="button"
      aria-label={`Citation ${marker}`}
      className={`ml-0.5 cursor-pointer text-[10px] font-bold transition-colors ${
        active ? 'text-accent-400 underline' : 'text-accent-500 hover:text-accent-400'
      }`}
    >
      {marker}
    </sup>
  )
}
