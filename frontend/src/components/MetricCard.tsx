interface MetricCardProps {
  label: string
  value: string | number
  unit?: string
  sub?: string
  accent?: boolean
  size?: 'lg' | 'md'
}

export function MetricCard({ label, value, unit, sub, accent, size = 'lg' }: MetricCardProps) {
  const big = size === 'lg' ? 'text-[42px]' : 'text-[34px]'
  const small = size === 'lg' ? 'text-[22px]' : 'text-[18px]'
  return (
    <div className="rounded-[14px] border border-surface-200 bg-surface-800 p-5">
      <p className="section-label">{label}</p>
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
