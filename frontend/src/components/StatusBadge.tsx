type Status = 'ready' | 'processing' | 'error' | 'supported' | 'partially_supported' | 'unsupported' | string

const MAP: Record<string, string> = {
  ready: 'bg-success-400/10 text-success-400',
  processing: 'bg-warning-400/10 text-warning-400',
  error: 'bg-danger-400/10 text-danger-400',
  supported: 'bg-success-400/10 text-success-400',
  partially_supported: 'bg-warning-400/10 text-warning-400',
  unsupported: 'bg-danger-400/10 text-danger-400',
}

const LABELS: Record<string, string> = {
  partially_supported: 'partial',
}

export function StatusBadge({ status }: { status: Status }) {
  const cls = MAP[status] ?? 'bg-surface-200 text-slate-400'
  return (
    <span
      className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-[11px] font-medium ${cls}`}
    >
      {LABELS[status] ?? status}
    </span>
  )
}
