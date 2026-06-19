import {
  LineChart,
  Line,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  CartesianGrid,
} from 'recharts'
import { useAnalytics } from '../hooks'
import { MetricCard } from '../components/MetricCard'
import { Spinner } from '../components/Spinner'
import { Activity } from 'lucide-react'
import { EmptyState } from '../components/EmptyState'

export function AnalyticsPage() {
  const { data, isLoading, error } = useAnalytics()

  if (isLoading) {
    return (
      <div className="flex flex-1 items-center justify-center h-full">
        <Spinner size="lg" />
      </div>
    )
  }
  if (error) {
    return (
      <div className="p-6 text-sm text-danger-400">{error.message}</div>
    )
  }
  if (!data) {
    return (
      <EmptyState
        icon={<Activity size={28} />}
        title="No analytics"
        description="Analytics will appear once queries are run."
      />
    )
  }

  const perQueryCost =
    data.total_queries > 0
      ? (data.total_cost_usd / data.total_queries).toFixed(6)
      : '0.000000'

  return (
    <div className="flex h-full flex-col">
      <div className="border-b border-slate-700/50 px-6 py-4">
        <h1 className="text-lg font-semibold text-slate-100">Analytics</h1>
        <p className="text-xs text-slate-500 mt-0.5">Query performance and cost telemetry</p>
      </div>

      <div className="flex-1 overflow-y-auto px-6 py-6 space-y-6">
        {/* Summary cards */}
        <div className="grid grid-cols-2 gap-3 md:grid-cols-5">
          <MetricCard
            label="Total Queries"
            value={data.total_queries.toLocaleString()}
            accent
          />
          <MetricCard
            label="Avg Confidence"
            value={`${data.avg_confidence.toFixed(1)}%`}
          />
          <MetricCard
            label="Avg Citation Acc."
            value={`${(data.avg_citation_accuracy * 100).toFixed(1)}%`}
          />
          <MetricCard
            label="Avg Latency"
            value={`${data.avg_latency_ms.toFixed(0)} ms`}
          />
          <MetricCard
            label="Total Cost"
            value={`$${data.total_cost_usd.toFixed(4)}`}
            sub={`$${perQueryCost} / query`}
          />
        </div>

        {/* Low confidence rate */}
        <div className="flex items-center gap-3 rounded-xl border border-slate-700/50 bg-surface-850 px-5 py-3">
          <div
            className={`text-sm font-bold tabular-nums ${
              data.low_confidence_rate > 0.3
                ? 'text-danger-400'
                : data.low_confidence_rate > 0.1
                ? 'text-warning-400'
                : 'text-success-400'
            }`}
          >
            {(data.low_confidence_rate * 100).toFixed(1)}%
          </div>
          <div>
            <p className="text-xs font-medium text-slate-300">Low Confidence Rate</p>
            <p className="text-[10px] text-slate-500">Queries scoring below threshold</p>
          </div>
        </div>

        {/* Queries by day */}
        {data.queries_by_day.length > 0 && (
          <div className="rounded-xl border border-slate-700/50 bg-surface-850 p-5">
            <h2 className="text-xs font-semibold uppercase tracking-wider text-slate-500 mb-4">
              Queries Per Day
            </h2>
            <ResponsiveContainer width="100%" height={200}>
              <LineChart data={data.queries_by_day} margin={{ left: -20, right: 0 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" />
                <XAxis
                  dataKey="date"
                  tick={{ fontSize: 10, fill: '#64748b' }}
                  tickFormatter={(v: string) => v.slice(5)}
                />
                <YAxis tick={{ fontSize: 10, fill: '#64748b' }} />
                <Tooltip
                  contentStyle={{
                    background: '#0f172a',
                    border: '1px solid #334155',
                    borderRadius: 8,
                    fontSize: 11,
                  }}
                />
                <Line
                  type="monotone"
                  dataKey="count"
                  stroke="#6366f1"
                  strokeWidth={2}
                  dot={{ r: 3, fill: '#6366f1' }}
                  name="Queries"
                />
              </LineChart>
            </ResponsiveContainer>
          </div>
        )}

        {/* Confidence histogram */}
        {data.confidence_histogram.length > 0 && (
          <div className="rounded-xl border border-slate-700/50 bg-surface-850 p-5">
            <h2 className="text-xs font-semibold uppercase tracking-wider text-slate-500 mb-4">
              Confidence Distribution
            </h2>
            <ResponsiveContainer width="100%" height={180}>
              <BarChart data={data.confidence_histogram} margin={{ left: -20, right: 0 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" />
                <XAxis dataKey="bucket" tick={{ fontSize: 10, fill: '#64748b' }} />
                <YAxis tick={{ fontSize: 10, fill: '#64748b' }} />
                <Tooltip
                  contentStyle={{
                    background: '#0f172a',
                    border: '1px solid #334155',
                    borderRadius: 8,
                    fontSize: 11,
                  }}
                />
                <Bar
                  dataKey="count"
                  fill="#6366f1"
                  radius={[4, 4, 0, 0]}
                  name="Count"
                />
              </BarChart>
            </ResponsiveContainer>
          </div>
        )}
      </div>
    </div>
  )
}
