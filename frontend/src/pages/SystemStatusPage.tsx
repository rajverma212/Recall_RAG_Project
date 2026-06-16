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
import { Server, Cpu, CheckCircle, XCircle, Key, Database, Zap } from 'lucide-react'

function StatusDot({ ok }: { ok: boolean }) {
  return ok ? (
    <CheckCircle size={14} className="text-success-400 flex-shrink-0" />
  ) : (
    <XCircle size={14} className="text-danger-400 flex-shrink-0" />
  )
}

function KeyChip({ label, present }: { label: string; present: boolean }) {
  return (
    <span
      className={`inline-flex items-center gap-1 rounded-full px-2.5 py-0.5 text-xs font-medium ${
        present
          ? 'bg-success-900 text-success-400 ring-1 ring-success-400/20'
          : 'bg-surface-900 text-slate-500 ring-1 ring-slate-700/50'
      }`}
    >
      <Key size={10} />
      {label}
    </span>
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

  // Build stage rows for the table
  const stageOrder = ['retrieval', 'generation', 'verification', 'total']
  const stageRows = metrics
    ? stageOrder
        .filter((s) => s in metrics.stages)
        .map((s) => ({ name: s, ...metrics.stages[s] }))
        .concat(
          // include any stages not in the preset order
          Object.entries(metrics.stages)
            .filter(([k]) => !stageOrder.includes(k))
            .map(([k, v]) => ({ name: k, ...v })),
        )
    : []

  // Bar chart data for latency
  const latencyChartData = stageRows.map((r) => ({
    stage: r.name,
    avg_ms: Math.round(r.avg_ms),
    p95_ms: Math.round(r.p95_ms),
  }))

  return (
    <div className="flex h-full flex-col">
      {/* Header */}
      <div className="border-b border-slate-700/50 px-6 py-4">
        <div className="flex items-center gap-2">
          <Server size={18} className="text-accent-400" />
          <h1 className="text-lg font-semibold text-slate-100">System Status</h1>
        </div>
        <p className="text-xs text-slate-500 mt-0.5">
          Provider configuration, dependency health, and pipeline latency — auto-refreshes every 10s
        </p>
      </div>

      <div className="flex-1 overflow-y-auto px-6 py-6 space-y-6">
        {anyLoading && !providers && !health && !metrics && (
          <div className="flex justify-center py-12">
            <Spinner size="lg" />
          </div>
        )}

        {anyError && (
          <div className="rounded-xl border border-danger-400/30 bg-danger-900/30 px-4 py-3 text-sm text-danger-400">
            {(anyError as Error).message}
          </div>
        )}

        {/* Health + Uptime */}
        {(health || metrics) && (
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
            <MetricCard
              label="System Status"
              value={health?.status ?? '—'}
              sub={health?.environment ?? ''}
              accent={health?.status === 'ok' || health?.status === 'healthy'}
            />
            <MetricCard
              label="Uptime"
              value={metrics ? formatUptime(metrics.uptime_seconds) : '—'}
              sub="since last restart"
            />
            <MetricCard
              label="Total Queries"
              value={metrics?.queries.total_queries.toLocaleString() ?? '—'}
              sub={
                metrics
                  ? `avg ${metrics.queries.avg_latency_ms.toFixed(0)} ms · ${(metrics.queries.avg_confidence * 100).toFixed(1)}% conf`
                  : ''
              }
            />
          </div>
        )}

        {/* Dependency Health */}
        {health && (
          <div className="rounded-xl border border-slate-700/50 bg-surface-850 p-5">
            <div className="flex items-center gap-2 mb-4">
              <Database size={14} className="text-slate-500" />
              <h2 className="text-xs font-semibold uppercase tracking-wider text-slate-500">
                Dependencies
              </h2>
            </div>
            <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
              {Object.entries(health.dependencies).map(([dep, ok]) => (
                <div
                  key={dep}
                  className={`flex items-center gap-2.5 rounded-lg px-3 py-2.5 border ${
                    ok
                      ? 'border-success-400/20 bg-success-900/20'
                      : 'border-danger-400/20 bg-danger-900/20'
                  }`}
                >
                  <StatusDot ok={ok} />
                  <span className="text-xs font-medium text-slate-300 capitalize">{dep}</span>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* LLM Provider */}
        {providers && (
          <div className="rounded-xl border border-slate-700/50 bg-surface-850 p-5">
            <div className="flex items-center gap-2 mb-4">
              <Cpu size={14} className="text-slate-500" />
              <h2 className="text-xs font-semibold uppercase tracking-wider text-slate-500">
                LLM Provider
              </h2>
              <span
                className={`ml-auto rounded-full px-2 py-0.5 text-[10px] font-medium ${
                  providers.llm.configured
                    ? 'bg-success-900 text-success-400'
                    : 'bg-danger-900 text-danger-400'
                }`}
              >
                {providers.llm.configured ? 'Configured' : 'Not configured'}
              </span>
            </div>

            <div className="grid grid-cols-2 gap-x-8 gap-y-3 text-sm sm:grid-cols-4">
              <div>
                <p className="text-[10px] uppercase tracking-wider text-slate-500">Active</p>
                <p className="text-slate-200 font-medium">{providers.llm.active}</p>
              </div>
              <div>
                <p className="text-[10px] uppercase tracking-wider text-slate-500">Model</p>
                <p className="text-slate-200 font-mono text-xs">{providers.llm.model}</p>
              </div>
              <div>
                <p className="text-[10px] uppercase tracking-wider text-slate-500">Input / 1M tokens</p>
                <p className="text-slate-200 font-medium tabular-nums">
                  ${providers.llm.input_price_per_1m.toFixed(2)}
                </p>
              </div>
              <div>
                <p className="text-[10px] uppercase tracking-wider text-slate-500">Output / 1M tokens</p>
                <p className="text-slate-200 font-medium tabular-nums">
                  ${providers.llm.output_price_per_1m.toFixed(2)}
                </p>
              </div>
            </div>

            <div className="mt-4 flex flex-wrap gap-2 items-center">
              <span className="text-[10px] uppercase tracking-wider text-slate-500 mr-1">
                API Keys:
              </span>
              <KeyChip label="Anthropic" present={providers.llm.keys_present.anthropic} />
              <KeyChip label="OpenAI" present={providers.llm.keys_present.openai} />
            </div>

            {providers.llm.available.length > 1 && (
              <div className="mt-3">
                <p className="text-[10px] uppercase tracking-wider text-slate-500 mb-1.5">
                  Available providers
                </p>
                <div className="flex flex-wrap gap-1.5">
                  {providers.llm.available.map((p) => (
                    <span
                      key={p}
                      className={`rounded-md px-2 py-0.5 text-[11px] font-medium ${
                        p === providers.llm.active
                          ? 'bg-accent-500/20 text-accent-400'
                          : 'bg-surface-900 text-slate-500'
                      }`}
                    >
                      {p}
                    </span>
                  ))}
                </div>
              </div>
            )}
          </div>
        )}

        {/* Embedding Provider */}
        {providers && (
          <div className="rounded-xl border border-slate-700/50 bg-surface-850 p-5">
            <div className="flex items-center gap-2 mb-4">
              <Zap size={14} className="text-slate-500" />
              <h2 className="text-xs font-semibold uppercase tracking-wider text-slate-500">
                Embedding Provider
              </h2>
              <span
                className={`ml-auto rounded-full px-2 py-0.5 text-[10px] font-medium ${
                  providers.embedding.configured
                    ? 'bg-success-900 text-success-400'
                    : 'bg-danger-900 text-danger-400'
                }`}
              >
                {providers.embedding.configured ? 'Configured' : 'Not configured'}
              </span>
            </div>

            <div className="grid grid-cols-2 gap-x-8 gap-y-3 text-sm sm:grid-cols-3">
              <div>
                <p className="text-[10px] uppercase tracking-wider text-slate-500">Active</p>
                <p className="text-slate-200 font-medium">{providers.embedding.active}</p>
              </div>
              <div>
                <p className="text-[10px] uppercase tracking-wider text-slate-500">Model</p>
                <p className="text-slate-200 font-mono text-xs">{providers.embedding.model}</p>
              </div>
              <div>
                <p className="text-[10px] uppercase tracking-wider text-slate-500">Dimensions</p>
                <p className="text-slate-200 font-medium tabular-nums">{providers.embedding.dim}</p>
              </div>
            </div>

            {providers.embedding.available.length > 1 && (
              <div className="mt-3">
                <p className="text-[10px] uppercase tracking-wider text-slate-500 mb-1.5">
                  Available providers
                </p>
                <div className="flex flex-wrap gap-1.5">
                  {providers.embedding.available.map((p) => (
                    <span
                      key={p}
                      className={`rounded-md px-2 py-0.5 text-[11px] font-medium ${
                        p === providers.embedding.active
                          ? 'bg-accent-500/20 text-accent-400'
                          : 'bg-surface-900 text-slate-500'
                      }`}
                    >
                      {p}
                    </span>
                  ))}
                </div>
              </div>
            )}
          </div>
        )}

        {/* Pipeline Stage Latency */}
        {metrics && stageRows.length > 0 && (
          <div className="rounded-xl border border-slate-700/50 bg-surface-850 p-5">
            <h2 className="text-xs font-semibold uppercase tracking-wider text-slate-500 mb-4">
              Pipeline Stage Latency
            </h2>

            {/* Latency bar chart */}
            {latencyChartData.length > 0 && (
              <div className="mb-5">
                <ResponsiveContainer width="100%" height={160}>
                  <BarChart data={latencyChartData} margin={{ left: -20, right: 0 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" />
                    <XAxis
                      dataKey="stage"
                      tick={{ fontSize: 10, fill: '#64748b' }}
                      tickFormatter={(v: string) =>
                        v.charAt(0).toUpperCase() + v.slice(1)
                      }
                    />
                    <YAxis tick={{ fontSize: 10, fill: '#64748b' }} unit=" ms" />
                    <Tooltip
                      contentStyle={{
                        background: '#0f172a',
                        border: '1px solid #334155',
                        borderRadius: 8,
                        fontSize: 11,
                      }}
                      formatter={(value: number, name: string) => [
                        `${value} ms`,
                        name === 'avg_ms' ? 'Avg' : 'P95',
                      ]}
                    />
                    <Bar dataKey="avg_ms" fill="#6366f1" radius={[4, 4, 0, 0]} name="avg_ms" />
                    <Bar dataKey="p95_ms" fill="#818cf8" radius={[4, 4, 0, 0]} name="p95_ms" opacity={0.5} />
                  </BarChart>
                </ResponsiveContainer>
                <p className="text-[10px] text-slate-600 text-center mt-1">
                  Indigo = avg · Light = P95
                </p>
              </div>
            )}

            {/* Stage table */}
            <div className="overflow-x-auto">
              <table className="w-full text-xs">
                <thead>
                  <tr className="border-b border-slate-800">
                    <th className="pb-2 text-left font-medium text-slate-500 uppercase tracking-wider">
                      Stage
                    </th>
                    <th className="pb-2 text-right font-medium text-slate-500 uppercase tracking-wider">
                      Count
                    </th>
                    <th className="pb-2 text-right font-medium text-slate-500 uppercase tracking-wider">
                      Errors
                    </th>
                    <th className="pb-2 text-right font-medium text-slate-500 uppercase tracking-wider">
                      Avg ms
                    </th>
                    <th className="pb-2 text-right font-medium text-slate-500 uppercase tracking-wider">
                      P95 ms
                    </th>
                    <th className="pb-2 text-right font-medium text-slate-500 uppercase tracking-wider">
                      Last ms
                    </th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-800">
                  {stageRows.map((row) => (
                    <tr key={row.name} className="hover:bg-surface-800/50 transition-colors">
                      <td className="py-2.5 pr-4 text-slate-300 font-medium capitalize">
                        {row.name}
                      </td>
                      <td className="py-2.5 text-right tabular-nums text-slate-400">
                        {row.count.toLocaleString()}
                      </td>
                      <td
                        className={`py-2.5 text-right tabular-nums ${
                          row.errors > 0 ? 'text-danger-400' : 'text-slate-600'
                        }`}
                      >
                        {row.errors}
                      </td>
                      <td className="py-2.5 text-right tabular-nums text-slate-400">
                        {row.avg_ms.toFixed(1)}
                      </td>
                      <td className="py-2.5 text-right tabular-nums text-slate-400">
                        {row.p95_ms.toFixed(1)}
                      </td>
                      <td className="py-2.5 text-right tabular-nums text-slate-500">
                        {row.last_ms.toFixed(1)}
                      </td>
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
