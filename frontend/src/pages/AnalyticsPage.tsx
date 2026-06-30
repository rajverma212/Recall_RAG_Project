import {
  Area,
  AreaChart,
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
import { EmptyState } from '../components/EmptyState'

const TOOLTIP_STYLE = {
  background: '#181510',
  border: '1px solid #252119',
  borderRadius: 10,
  fontSize: 11,
  color: '#ede8df',
} as const

// Split a fixed-decimal percentage into integer + fractional-with-unit parts,
// so the big serif number reads "77" with a smaller gray ".3%" suffix.
function splitPct(n: number): { value: string; unit: string } {
  const [int, dec] = n.toFixed(1).split('.')
  return { value: int, unit: `.${dec}%` }
}

export function AnalyticsPage() {
  const { data, isLoading, error } = useAnalytics()

  if (isLoading) {
    return (
      <div className="flex h-full flex-1 items-center justify-center">
        <Spinner size="lg" />
      </div>
    )
  }
  if (error) {
    return <div className="p-8 text-[13px] text-danger-400">{error.message}</div>
  }
  if (!data) {
    return (
      <EmptyState
        icon={<span className="font-serif text-[34px] italic">∿</span>}
        title="No analytics"
        description="Analytics will appear once queries are run."
      />
    )
  }

  const perQueryCost =
    data.total_queries > 0 ? (data.total_cost_usd / data.total_queries).toFixed(3) : '0.000'
  const conf = splitPct(data.avg_confidence)
  const cite = splitPct(data.avg_citation_accuracy * 100)
  const lowRate = data.low_confidence_rate
  const lowPillCls =
    lowRate > 0.3
      ? 'bg-danger-400/15 text-danger-400'
      : lowRate > 0.1
        ? 'bg-warning-400/15 text-warning-400'
        : 'bg-success-400/15 text-success-400'
  const lowBannerCls =
    lowRate > 0.3
      ? 'border-danger-400/30 bg-danger-400/[0.07]'
      : lowRate > 0.1
        ? 'border-warning-400/30 bg-warning-400/[0.07]'
        : 'border-success-400/30 bg-success-400/[0.07]'

  return (
    <div className="h-full overflow-y-auto px-8 py-7">
      <h1 className="text-[26px] font-bold leading-tight tracking-tight text-slate-100">Analytics</h1>
      <p className="mt-0.5 text-[13px] text-slate-400">Query performance and cost telemetry</p>

      {/* Summary stat cards */}
      <div className="mt-6 grid grid-cols-2 gap-3.5 md:grid-cols-5">
        <MetricCard label="Total Queries" value={data.total_queries.toLocaleString()} accent />
        <MetricCard label="Avg Confidence" value={conf.value} unit={conf.unit} />
        <MetricCard label="Avg Citation Acc." value={cite.value} unit={cite.unit} />
        <MetricCard
          label="Avg Latency"
          value={data.avg_latency_ms.toLocaleString(undefined, { maximumFractionDigits: 0 })}
          unit="ms"
          size="md"
        />
        <MetricCard
          label="Total Cost"
          value={`$${data.total_cost_usd.toFixed(4)}`}
          sub={`$${perQueryCost} / query`}
          size="md"
        />
      </div>

      {/* Low confidence alert banner */}
      <div className={`mt-3.5 flex items-center gap-3 rounded-[14px] border px-5 py-3 ${lowBannerCls}`}>
        <span className={`rounded-full px-2.5 py-0.5 text-[13px] font-semibold tabular-nums ${lowPillCls}`}>
          {(lowRate * 100).toFixed(1)}%
        </span>
        <p className="text-[13px] text-slate-300">
          <span className="font-medium text-slate-100">Low Confidence Rate</span>
          <span className="text-slate-600"> — Queries scoring below threshold</span>
        </p>
      </div>

      {/* Queries per day */}
      {data.queries_by_day.length > 0 && (
        <div className="mt-3.5 rounded-[14px] border border-surface-200 bg-surface-800 p-5">
          <h2 className="section-label mb-4">Queries Per Day</h2>
          <ResponsiveContainer width="100%" height={220}>
            <AreaChart data={data.queries_by_day} margin={{ left: -20, right: 4, top: 4 }}>
              <defs>
                <linearGradient id="qpd" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor="#d97a3a" stopOpacity={0.35} />
                  <stop offset="100%" stopColor="#d97a3a" stopOpacity={0} />
                </linearGradient>
              </defs>
              <CartesianGrid strokeDasharray="3 3" stroke="#1e1b15" vertical={false} />
              <XAxis
                dataKey="date"
                tick={{ fontSize: 9, fill: '#5c5448' }}
                tickFormatter={(v: string) => v.slice(5)}
                axisLine={{ stroke: '#1e1b15' }}
                tickLine={false}
              />
              <YAxis
                tick={{ fontSize: 9, fill: '#5c5448' }}
                axisLine={false}
                tickLine={false}
              />
              <Tooltip contentStyle={TOOLTIP_STYLE} cursor={{ stroke: '#252119' }} />
              <Area
                type="monotone"
                dataKey="count"
                stroke="#d97a3a"
                strokeWidth={2.5}
                fill="url(#qpd)"
                dot={false}
                activeDot={{ r: 4, fill: '#d97a3a', stroke: '#181510', strokeWidth: 2 }}
                name="Queries"
              />
            </AreaChart>
          </ResponsiveContainer>
        </div>
      )}

      {/* Confidence distribution */}
      {data.confidence_histogram.length > 0 && (
        <div className="mt-3.5 rounded-[14px] border border-surface-200 bg-surface-800 p-5">
          <h2 className="section-label mb-4">Confidence Distribution</h2>
          <ResponsiveContainer width="100%" height={180}>
            <BarChart data={data.confidence_histogram} margin={{ left: -20, right: 4 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#1e1b15" vertical={false} />
              <XAxis
                dataKey="bucket"
                tick={{ fontSize: 9, fill: '#5c5448' }}
                axisLine={{ stroke: '#1e1b15' }}
                tickLine={false}
              />
              <YAxis tick={{ fontSize: 9, fill: '#5c5448' }} axisLine={false} tickLine={false} />
              <Tooltip contentStyle={TOOLTIP_STYLE} cursor={{ fill: 'rgba(217,122,58,.06)' }} />
              <Bar dataKey="count" fill="#d97a3a" radius={[3, 3, 0, 0]} name="Count" />
            </BarChart>
          </ResponsiveContainer>
        </div>
      )}
    </div>
  )
}
