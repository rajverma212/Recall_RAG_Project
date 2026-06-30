interface ScoreBarProps {
  label: string
  value: number // 0-1
  max?: number
}

function colorFor(v: number) {
  if (v >= 0.7) return { bar: 'bg-success-400', text: 'text-success-400' }
  if (v >= 0.4) return { bar: 'bg-warning-400', text: 'text-warning-400' }
  return { bar: 'bg-danger-400', text: 'text-danger-400' }
}

export function ScoreBar({ label, value, max = 1 }: ScoreBarProps) {
  const pct = Math.min(100, (value / max) * 100)
  const c = colorFor(value)
  return (
    <div className="space-y-1.5">
      <div className="flex justify-between text-[13px]">
        <span className="text-slate-300">{label}</span>
        <span className={`tabular-nums font-medium ${c.text}`}>{(value * 100).toFixed(1)}%</span>
      </div>
      <div className="h-1 w-full rounded-full bg-surface-200">
        <div
          className={`h-1 origin-left rounded-full animate-bar-grow ${c.bar}`}
          style={{ width: `${pct}%` }}
        />
      </div>
    </div>
  )
}
