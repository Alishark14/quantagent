import { PieChart, Pie, Cell, Tooltip, Legend, ResponsiveContainer } from 'recharts'
import type { ExitsData } from '../../types'

interface Props {
  data: ExitsData
}

const COLORS = {
  tp: '#22c55e',
  sl: '#ef4444',
  time: '#eab308',
  unknown: '#6b7280',
}

export default function ExitTypeRatio({ data }: Props) {
  const pieData = [
    { name: 'Take Profit', value: data.tp_count, pct: data.tp_pct, color: COLORS.tp },
    { name: 'Stop Loss', value: data.sl_count, pct: data.sl_pct, color: COLORS.sl },
    { name: 'Time Exit', value: data.time_count, pct: data.time_pct, color: COLORS.time },
    { name: 'Unknown', value: data.unknown_count, pct: 0, color: COLORS.unknown },
  ].filter(d => d.value > 0)

  if (pieData.length === 0) {
    return (
      <div className="bg-bg-card border border-border rounded-lg p-6 flex items-center justify-center h-48">
        <p className="text-text-muted text-sm">No exit data yet</p>
      </div>
    )
  }

  return (
    <div className="bg-bg-card border border-border rounded-lg p-5">
      <h3 className="text-text-primary text-sm font-semibold mb-4">Exit Type Distribution</h3>
      <ResponsiveContainer width="100%" height={200}>
        <PieChart>
          <Pie data={pieData} dataKey="value" innerRadius={50} outerRadius={80} stroke="none">
            {pieData.map((entry, i) => (
              <Cell key={i} fill={entry.color} />
            ))}
          </Pie>
          <Tooltip
            contentStyle={{ background: '#1a1d26', border: '1px solid #2d3039', borderRadius: 6, fontSize: 11 }}
            itemStyle={{ color: '#e5e7eb' }}
            formatter={(val: number, name: string) => [`${val} trades`, name]}
          />
          <Legend
            iconType="circle"
            iconSize={8}
            wrapperStyle={{ fontSize: 12, color: '#9ca3af' }}
          />
        </PieChart>
      </ResponsiveContainer>
    </div>
  )
}
