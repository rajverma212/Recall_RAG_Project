type Status = 'ready' | 'processing' | 'error' | 'supported' | 'partially_supported' | 'unsupported' | string

const MAP: Record<string, string> = {
  ready: 'bg-success-900 text-success-400 ring-success-400/20',
  processing: 'bg-warning-900 text-warning-400 ring-warning-400/20',
  error: 'bg-danger-900 text-danger-400 ring-danger-400/20',
  supported: 'bg-success-900 text-success-400 ring-success-400/20',
  partially_supported: 'bg-warning-900 text-warning-400 ring-warning-400/20',
  unsupported: 'bg-danger-900 text-danger-400 ring-danger-400/20',
}

const LABELS: Record<string, string> = {
  partially_supported: 'partial',
}

export function StatusBadge({ status }: { status: Status }) {
  const cls = MAP[status] ?? 'bg-surface-800 text-slate-400 ring-slate-400/20'
  return (
    <span
      className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ring-1 ring-inset ${cls}`}
    >
      {LABELS[status] ?? status}
    </span>
  )
}
