interface MetricCardProps {
  label: string
  value: string | number
  unit?: string
  sub?: string
  accent?: boolean
  size?: 'lg' | 'md'
  hint?: string
}

export function MetricCard({ label, value, unit, sub, accent, size = 'lg', hint }: MetricCardProps) {
  const big = size === 'lg' ? 'text-[42px]' : 'text-[34px]'
  const small = size === 'lg' ? 'text-[22px]' : 'text-[18px]'
  return (
    <div className="rounded-[14px] border border-surface-200 bg-surface-800 p-5">
      <div className="flex items-center gap-1.5">
        <p className="section-label">{label}</p>
        {hint && (
          <span className="group relative inline-flex">
            <span
              className="flex h-3.5 w-3.5 cursor-help items-center justify-center rounded-full border border-surface-100 text-[9px] font-medium text-slate-500 transition-colors hover:border-accent-500 hover:text-accent-500"
              aria-label={hint}
            >
              i
            </span>
            <span className="pointer-events-none absolute bottom-full left-1/2 z-20 mb-2 hidden w-56 -translate-x-1/2 rounded-lg border border-surface-200 bg-surface-900 px-3 py-2 text-[11px] font-normal normal-case leading-snug tracking-normal text-slate-300 shadow-xl group-hover:block">
              {hint}
            </span>
          </span>
        )}
      </div>
      <p
        className={`mt-2 font-serif leading-none tabular-nums ${big} ${
          accent ? 'text-accent-500' : 'text-slate-100'
        }`}
      >
        {value}
        {unit && <span className={`${small} text-slate-400`}>{unit}</span>}
      </p>
      {sub && <p className="mt-1.5 text-[11px] text-slate-600">{sub}</p>}
    </div>
  )
}
