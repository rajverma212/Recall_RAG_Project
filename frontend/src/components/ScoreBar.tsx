interface ScoreBarProps {
  label: string
  value: number // 0-1
  max?: number
}

function colorFor(v: number) {
  if (v >= 0.7) return 'bg-success-500'
  if (v >= 0.4) return 'bg-warning-500'
  return 'bg-danger-500'
}

export function ScoreBar({ label, value, max = 1 }: ScoreBarProps) {
  const pct = Math.min(100, (value / max) * 100)
  return (
    <div className="space-y-1">
      <div className="flex justify-between text-xs">
        <span className="text-slate-400">{label}</span>
        <span className="tabular-nums text-slate-300">{(value * 100).toFixed(1)}%</span>
      </div>
      <div className="h-1.5 w-full rounded-full bg-surface-800">
        <div
          className={`h-1.5 rounded-full transition-all duration-500 ${colorFor(value)}`}
          style={{ width: `${pct}%` }}
        />
      </div>
    </div>
  )
}
