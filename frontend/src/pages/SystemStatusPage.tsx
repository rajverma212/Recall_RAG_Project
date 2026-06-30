import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  CartesianGrid,
} from 'recharts'
import { useProviders, useHealth, useMetrics } from '../hooks'
import { MetricCard } from '../components/MetricCard'
import { Spinner } from '../components/Spinner'
import type { ReactNode } from 'react'

const TOOLTIP_STYLE = {
  background: '#181510',
  border: '1px solid #252119',
  borderRadius: 10,
  fontSize: 11,
  color: '#ede8df',
} as const

type HealthState = 'healthy' | 'degraded' | 'offline'

const STATE_STYLES: Record<HealthState, string> = {
  healthy: 'bg-success-400/10 text-success-400',
  degraded: 'bg-warning-400/10 text-warning-400',
  offline: 'bg-danger-400/10 text-danger-400',
}

const STATE_DOT: Record<HealthState, string> = {
  healthy: 'bg-success-400',
  degraded: 'bg-warning-400',
  offline: 'bg-danger-400',
}

const STATE_LABEL: Record<HealthState, string> = {
  healthy: 'Healthy',
  degraded: 'Degraded',
  offline: 'Offline',
}

function StatusPill({ state }: { state: HealthState }) {
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-[11px] font-semibold ${STATE_STYLES[state]}`}
    >
      <span className={`h-1.5 w-1.5 rounded-full ${STATE_DOT[state]} ${state === 'healthy' ? 'animate-pulse-dot' : ''}`} />
      {STATE_LABEL[state]}
    </span>
  )
}

function ServiceCard({ name, state, children }: { name: string; state: HealthState; children?: ReactNode }) {
  return (
    <div className="rounded-[14px] border border-surface-200 bg-surface-800 p-4">
      <div className="flex items-center justify-between gap-2">
        <span className="text-[14px] font-medium text-slate-100">{name}</span>
        <StatusPill state={state} />
      </div>
      {children && <div className="mt-2.5 space-y-0.5 text-[12px] text-slate-500">{children}</div>}
    </div>
  )
}

function KeyChip({ label, present }: { label: string; present: boolean }) {
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-[12px] font-medium ${
        present ? 'bg-success-400/10 text-success-400' : 'bg-surface-850 text-slate-500'
      }`}
    >
      <span className={`h-1.5 w-1.5 rounded-full ${present ? 'bg-success-400' : 'bg-slate-600'}`} />
      {label}
    </span>
  )
}

function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div>
      <p className="text-[10px] uppercase tracking-label text-slate-600">{label}</p>
      <p className="text-[13px] font-medium text-slate-100">{children}</p>
    </div>
  )
}

function ProviderChips({ available, active }: { available: string[]; active: string }) {
  if (available.length <= 1) return null
  return (
    <div className="mt-3">
      <p className="section-label mb-1.5">Available providers</p>
      <div className="flex flex-wrap gap-1.5">
        {available.map((p) => (
          <span
            key={p}
            className={`rounded-md px-2 py-0.5 text-[11px] font-medium ${
              p === active ? 'bg-accent-500/15 text-accent-500' : 'bg-surface-850 text-slate-500'
            }`}
          >
            {p}
          </span>
        ))}
      </div>
    </div>
  )
}

function formatUptime(seconds: number): string {
  const d = Math.floor(seconds / 86400)
  const h = Math.floor((seconds % 86400) / 3600)
  const m = Math.floor((seconds % 3600) / 60)
  const s = Math.floor(seconds % 60)
  if (d > 0) return `${d}d ${h}h ${m}m`
  if (h > 0) return `${h}h ${m}m ${s}s`
  if (m > 0) return `${m}m ${s}s`
  return `${s}s`
}

export function SystemStatusPage() {
  const { data: providers, isLoading: pvLoading, error: pvError } = useProviders()
  const { data: health, isLoading: hlLoading, error: hlError } = useHealth()
  const { data: metrics, isLoading: mtLoading, error: mtError } = useMetrics()

  const anyLoading = pvLoading || hlLoading || mtLoading
  const anyError = pvError ?? hlError ?? mtError

  const stageOrder = ['retrieval', 'generation', 'verification', 'total']
  const stageRows = metrics
    ? stageOrder
        .filter((s) => s in metrics.stages)
        .map((s) => ({ name: s, ...metrics.stages[s] }))
        .concat(
          Object.entries(metrics.stages)
            .filter(([k]) => !stageOrder.includes(k))
            .map(([k, v]) => ({ name: k, ...v })),
        )
    : []

  const latencyChartData = stageRows.map((r) => ({
    stage: r.name,
    avg_ms: Math.round(r.avg_ms),
    p95_ms: Math.round(r.p95_ms),
  }))

  const checks = health?.checks ?? {}
  const overallState: HealthState = health ? (health.status === 'ok' ? 'healthy' : 'degraded') : 'offline'
  const dbState: HealthState = checks.database?.ok ? 'healthy' : 'offline'
  const vs = checks.vector_store
  const qdrantState: HealthState = vs?.ok ? (vs.backend === 'qdrant' ? 'healthy' : 'degraded') : 'offline'
  const retrievalState: HealthState = checks.retrieval?.ok ? 'healthy' : 'offline'
  const llmStatus = providers?.llm.status
  const llmState: HealthState = llmStatus ? (llmStatus.healthy ? 'healthy' : 'degraded') : 'offline'
  const embStatus = providers?.embedding.status
  const embState: HealthState = embStatus ? (embStatus.healthy ? 'healthy' : 'degraded') : 'offline'

  return (
    <div className="h-full overflow-y-auto px-8 py-7">
      <h1 className="text-[26px] font-bold leading-tight tracking-tight text-slate-100">System</h1>
      <p className="mt-0.5 text-[13px] text-slate-400">
        Live service health, provider configuration, and pipeline latency — auto-refreshes every 10s
      </p>

      <div className="mt-6 space-y-3.5">
        {anyLoading && !providers && !health && !metrics && (
          <div className="flex justify-center py-12">
            <Spinner size="lg" />
          </div>
        )}

        {anyError && (
          <div className="rounded-xl border border-danger-400/30 bg-danger-900/30 px-4 py-3 text-[13px] text-danger-400">
            {(anyError as Error).message}
          </div>
        )}

        {/* Summary cards */}
        {(health || metrics) && (
          <div className="grid grid-cols-2 gap-3.5 lg:grid-cols-4">
            <MetricCard
              label="System Status"
              value={STATE_LABEL[overallState]}
              sub={health?.environment ? `env: ${health.environment}` : ''}
              accent={overallState === 'healthy'}
              size="md"
            />
            <MetricCard label="Version" value={health?.version ?? '—'} sub={health?.app ?? ''} size="md" />
            <MetricCard
              label="Uptime"
              value={metrics ? formatUptime(metrics.uptime_seconds) : '—'}
              sub="since last restart"
              size="md"
            />
            <MetricCard
              label="Total Queries"
              value={metrics?.queries.total_queries.toLocaleString() ?? '—'}
              sub={
                metrics
                  ? `avg ${metrics.queries.avg_latency_ms.toFixed(0)} ms · ${metrics.queries.avg_confidence.toFixed(1)}% conf`
                  : ''
              }
            />
          </div>
        )}

        {/* Services */}
        {(health || providers) && (
          <div>
            <h2 className="section-label mb-3 mt-2">Services</h2>
            <div className="grid grid-cols-1 gap-3.5 sm:grid-cols-2 lg:grid-cols-3">
              <ServiceCard name="Backend (API)" state={overallState}>
                <p>Version {health?.version ?? '—'}</p>
                <p>Environment: {health?.environment ?? '—'}</p>
              </ServiceCard>

              <ServiceCard name="PostgreSQL" state={dbState}>
                <p>{dbState === 'healthy' ? 'Connection OK' : 'Unreachable'}</p>
                {checks.database?.detail && <p className="truncate text-danger-400/80">{checks.database.detail}</p>}
              </ServiceCard>

              <ServiceCard name="Qdrant (vectors)" state={qdrantState}>
                <p>
                  Backend: {vs?.backend ?? '—'}
                  {qdrantState === 'degraded' ? ' (fallback)' : ''}
                </p>
                <p>
                  Vectors indexed:{' '}
                  <span className="tabular-nums text-slate-300">
                    {vs?.vectors != null ? vs.vectors.toLocaleString() : '—'}
                  </span>
                </p>
              </ServiceCard>

              <ServiceCard name="LLM" state={llmState}>
                <p>
                  Provider: <span className="text-slate-300">{providers?.llm.active ?? '—'}</span>
                  {llmState === 'degraded' ? ' (fallback)' : ''}
                </p>
                <p className="font-mono text-[11px]">{providers?.llm.model ?? '—'}</p>
              </ServiceCard>

              <ServiceCard name="Embeddings" state={embState}>
                <p>
                  Provider: <span className="text-slate-300">{providers?.embedding.active ?? '—'}</span>
                  {embState === 'degraded' ? ' (fallback)' : ''}
                </p>
                <p>
                  Dimension:{' '}
                  <span className="tabular-nums text-slate-300">{providers?.embedding.dim ?? '—'}</span>
                </p>
              </ServiceCard>

              <ServiceCard name="Retrieval" state={retrievalState}>
                <p>{retrievalState === 'healthy' ? 'Hybrid pipeline ready' : 'Unavailable'}</p>
                <p>Embeddings: {checks.retrieval?.embedding_provider ?? '—'}</p>
              </ServiceCard>
            </div>
          </div>
        )}

        {/* LLM Provider detail */}
        {providers && (
          <div className="rounded-[14px] border border-surface-200 bg-surface-800 p-5">
            <div className="mb-4 flex items-center gap-2">
              <h2 className="section-label">LLM Provider</h2>
              <span className="ml-auto">
                <StatusPill state={llmState} />
              </span>
            </div>
            <div className="grid grid-cols-2 gap-x-8 gap-y-3 sm:grid-cols-4">
              <Field label="Configured">{providers.llm.configured}</Field>
              <Field label="Active">{providers.llm.active}</Field>
              <Field label="Model">
                <span className="font-mono text-[12px]">{providers.llm.model}</span>
              </Field>
              <Field label="Price /1M (in/out)">
                <span className="tabular-nums">
                  ${providers.llm.input_price_per_1m.toFixed(2)} / ${providers.llm.output_price_per_1m.toFixed(2)}
                </span>
              </Field>
            </div>
            <div className="mt-4 flex flex-wrap items-center gap-2">
              <span className="section-label mr-1">API Keys</span>
              <KeyChip label="Anthropic" present={providers.llm.keys_present.anthropic} />
              <KeyChip label="OpenAI" present={providers.llm.keys_present.openai} />
            </div>
            <ProviderChips available={providers.llm.available} active={providers.llm.active} />
          </div>
        )}

        {/* Embedding Provider detail */}
        {providers && (
          <div className="rounded-[14px] border border-surface-200 bg-surface-800 p-5">
            <div className="mb-4 flex items-center gap-2">
              <h2 className="section-label">Embedding Provider</h2>
              <span className="ml-auto">
                <StatusPill state={embState} />
              </span>
            </div>
            <div className="grid grid-cols-2 gap-x-8 gap-y-3 sm:grid-cols-4">
              <Field label="Configured">{providers.embedding.configured}</Field>
              <Field label="Active">{providers.embedding.active}</Field>
              <Field label="Model">
                <span className="font-mono text-[12px]">{providers.embedding.model}</span>
              </Field>
              <Field label="Dimensions">
                <span className="tabular-nums">{providers.embedding.dim}</span>
              </Field>
            </div>
            <ProviderChips available={providers.embedding.available} active={providers.embedding.active} />
          </div>
        )}

        {/* Pipeline Stage Latency */}
        {metrics && stageRows.length > 0 && (
          <div className="rounded-[14px] border border-surface-200 bg-surface-800 p-5">
            <h2 className="section-label mb-4">Pipeline Stage Latency</h2>

            {latencyChartData.length > 0 && (
              <div className="mb-5">
                <ResponsiveContainer width="100%" height={160}>
                  <BarChart data={latencyChartData} margin={{ left: -20, right: 4 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#1e1b15" vertical={false} />
                    <XAxis
                      dataKey="stage"
                      tick={{ fontSize: 9, fill: '#5c5448' }}
                      tickFormatter={(v: string) => v.charAt(0).toUpperCase() + v.slice(1)}
                      axisLine={{ stroke: '#1e1b15' }}
                      tickLine={false}
                    />
                    <YAxis tick={{ fontSize: 9, fill: '#5c5448' }} unit=" ms" axisLine={false} tickLine={false} />
                    <Tooltip
                      contentStyle={TOOLTIP_STYLE}
                      cursor={{ fill: 'rgba(217,122,58,.06)' }}
                      formatter={(value: number, name: string) => [`${value} ms`, name === 'avg_ms' ? 'Avg' : 'P95']}
                    />
                    <Bar dataKey="avg_ms" fill="#d97a3a" radius={[3, 3, 0, 0]} name="avg_ms" />
                    <Bar dataKey="p95_ms" fill="#d97a3a" radius={[3, 3, 0, 0]} name="p95_ms" opacity={0.4} />
                  </BarChart>
                </ResponsiveContainer>
                <p className="mt-1 text-center text-[10px] text-slate-600">Amber = avg · Faded = P95</p>
              </div>
            )}

            <div className="overflow-x-auto">
              <table className="w-full text-[12px]">
                <thead>
                  <tr className="border-b border-surface-50">
                    {['Stage', 'Count', 'Errors', 'Avg ms', 'P95 ms', 'Last ms'].map((h, i) => (
                      <th
                        key={h}
                        className={`pb-2 text-[10px] font-medium uppercase tracking-label text-slate-600 ${
                          i === 0 ? 'text-left' : 'text-right'
                        }`}
                      >
                        {h}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {stageRows.map((row) => (
                    <tr key={row.name} className="border-b border-surface-50 last:border-0 hover:bg-surface-850">
                      <td className="py-2.5 pr-4 font-medium capitalize text-slate-100">{row.name}</td>
                      <td className="py-2.5 text-right tabular-nums text-slate-400">{row.count.toLocaleString()}</td>
                      <td className={`py-2.5 text-right tabular-nums ${row.errors > 0 ? 'text-danger-400' : 'text-slate-600'}`}>
                        {row.errors}
                      </td>
                      <td className="py-2.5 text-right tabular-nums text-slate-400">{row.avg_ms.toFixed(1)}</td>
                      <td className="py-2.5 text-right tabular-nums text-slate-400">{row.p95_ms.toFixed(1)}</td>
                      <td className="py-2.5 text-right tabular-nums text-slate-500">{row.last_ms.toFixed(1)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
