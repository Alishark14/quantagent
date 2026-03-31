import {
  AreaChart,
  Area,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  ReferenceLine,
} from 'recharts'
import type { EquityPoint } from '../../types'

interface Props {
  data: EquityPoint[]
}

function formatTs(ts: string) {
  try {
    return new Date(ts).toLocaleDateString('en-US', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })
  } catch {
    return ts
  }
}

export default function EquityCurve({ data }: Props) {
  if (data.length === 0) {
    return (
      <div className="bg-bg-card border border-border rounded-lg p-6 flex items-center justify-center h-64">
        <p className="text-text-muted text-sm">No trade data yet</p>
      </div>
    )
  }

  const isPositive = (data[data.length - 1]?.cumulative_pnl ?? 0) >= 0

  return (
    <div className="bg-bg-card border border-border rounded-lg p-5">
      <h2 className="text-text-primary text-sm font-semibold mb-4">Equity Curve</h2>
      <ResponsiveContainer width="100%" height={260}>
        <AreaChart data={data} margin={{ top: 4, right: 4, left: 0, bottom: 0 }}>
          <defs>
            <linearGradient id="pnlGrad" x1="0" y1="0" x2="0" y2="1">
              <stop
                offset="5%"
                stopColor={isPositive ? '#22c55e' : '#ef4444'}
                stopOpacity={0.25}
              />
              <stop
                offset="95%"
                stopColor={isPositive ? '#22c55e' : '#ef4444'}
                stopOpacity={0}
              />
            </linearGradient>
          </defs>
          <CartesianGrid strokeDasharray="3 3" stroke="#2d3039" vertical={false} />
          <XAxis
            dataKey="timestamp"
            tickFormatter={formatTs}
            tick={{ fill: '#6b7280', fontSize: 11 }}
            axisLine={false}
            tickLine={false}
          />
          <YAxis
            tick={{ fill: '#6b7280', fontSize: 11 }}
            axisLine={false}
            tickLine={false}
            width={60}
            tickFormatter={(v: number) => v.toFixed(1)}
          />
          <Tooltip
            contentStyle={{ background: '#1a1d26', border: '1px solid #2d3039', borderRadius: 6 }}
            labelStyle={{ color: '#9ca3af', fontSize: 11 }}
            itemStyle={{ color: '#e5e7eb', fontFamily: 'monospace' }}
            labelFormatter={formatTs}
            formatter={(val: number) => [`${val.toFixed(4)}`, 'Cumulative P&L']}
          />
          <ReferenceLine y={0} stroke="#2d3039" strokeWidth={1} />
          <Area
            type="monotone"
            dataKey="cumulative_pnl"
            stroke={isPositive ? '#22c55e' : '#ef4444'}
            strokeWidth={2}
            fill="url(#pnlGrad)"
            dot={false}
            activeDot={{ r: 4, fill: isPositive ? '#22c55e' : '#ef4444' }}
          />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  )
}
