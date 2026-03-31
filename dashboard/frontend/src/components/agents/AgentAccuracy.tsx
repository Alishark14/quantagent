import { PieChart, Pie, Cell, Tooltip, ResponsiveContainer } from 'recharts'
import type { AgentStat } from '../../types'

interface Props {
  name: string
  stat: AgentStat
}

const COLORS = ['#22c55e', '#ef4444']

export default function AgentAccuracy({ name, stat }: Props) {
  const incorrect = stat.total_signals - stat.correct_signals
  const pieData = [
    { name: 'Correct', value: stat.correct_signals },
    { name: 'Incorrect', value: incorrect },
  ]

  const pct = stat.accuracy_pct
  const color = pct >= 60 ? 'text-profit' : pct >= 45 ? 'text-yellow-400' : 'text-loss'

  return (
    <div className="bg-bg-card border border-border rounded-lg p-5">
      <h3 className="text-text-secondary text-xs uppercase tracking-wider font-medium mb-4">
        {name} Agent
      </h3>
      <div className="flex items-center gap-4">
        <div className="flex-shrink-0">
          <ResponsiveContainer width={80} height={80}>
            <PieChart>
              <Pie data={pieData} innerRadius={28} outerRadius={38} dataKey="value" stroke="none">
                {pieData.map((_, i) => (
                  <Cell key={i} fill={COLORS[i]} />
                ))}
              </Pie>
              <Tooltip
                contentStyle={{ background: '#1a1d26', border: '1px solid #2d3039', borderRadius: 6, fontSize: 11 }}
                itemStyle={{ color: '#e5e7eb' }}
              />
            </PieChart>
          </ResponsiveContainer>
        </div>
        <div>
          <p className={`text-3xl font-bold font-mono tabular-nums ${color}`}>{pct.toFixed(1)}%</p>
          <p className="text-text-muted text-xs mt-1">
            {stat.correct_signals} / {stat.total_signals} signals correct
          </p>
        </div>
      </div>
    </div>
  )
}
