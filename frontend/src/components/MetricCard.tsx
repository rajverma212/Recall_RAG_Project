interface MetricCardProps {
  label: string
  value: string | number
  sub?: string
  accent?: boolean
}

export function MetricCard({ label, value, sub, accent }: MetricCardProps) {
  return (
    <div className={`rounded-xl border p-4 ${accent ? 'border-accent-500/30 bg-accent-500/5' : 'border-slate-700/50 bg-surface-850'}`}>
      <p className="text-xs font-medium uppercase tracking-wider text-slate-500">{label}</p>
      <p className={`mt-1 text-2xl font-bold tabular-nums ${accent ? 'text-accent-400' : 'text-slate-100'}`}>
        {value}
      </p>
      {sub && <p className="mt-0.5 text-xs text-slate-500">{sub}</p>}
    </div>
  )
}
