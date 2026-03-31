import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
} from 'recharts'
import type { BreakdownRow } from '../../types'

interface Props {
  data: BreakdownRow[]
}

export default function BreakdownView({ data }: Props) {
  if (data.length === 0) {
    return <p className="text-text-muted text-sm py-8 text-center">No data</p>
  }

  return (
    <div className="space-y-6">
      <div className="bg-bg-card border border-border rounded-lg p-5">
        <ResponsiveContainer width="100%" height={220}>
          <BarChart data={data} margin={{ top: 4, right: 4, left: 0, bottom: 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#2d3039" vertical={false} />
            <XAxis dataKey="group" tick={{ fill: '#6b7280', fontSize: 11 }} axisLine={false} tickLine={false} />
            <YAxis tick={{ fill: '#6b7280', fontSize: 11 }} axisLine={false} tickLine={false} domain={[0, 100]} unit="%" />
            <Tooltip
              contentStyle={{ background: '#1a1d26', border: '1px solid #2d3039', borderRadius: 6 }}
              labelStyle={{ color: '#9ca3af', fontSize: 11 }}
              itemStyle={{ color: '#e5e7eb', fontFamily: 'monospace' }}
              formatter={(val: number) => [`${val}%`, 'Win Rate']}
            />
            <Bar dataKey="win_rate" fill="#3b82f6" radius={[4, 4, 0, 0]} />
          </BarChart>
        </ResponsiveContainer>
      </div>

      <div className="bg-bg-card border border-border rounded-lg overflow-hidden">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-border text-text-muted text-xs uppercase">
              <th className="px-4 py-3 text-left font-medium">Group</th>
              <th className="px-4 py-3 text-right font-medium">Trades</th>
              <th className="px-4 py-3 text-right font-medium">Wins</th>
              <th className="px-4 py-3 text-right font-medium">Losses</th>
              <th className="px-4 py-3 text-right font-medium">Win Rate</th>
              <th className="px-4 py-3 text-right font-medium">Avg P&L</th>
              <th className="px-4 py-3 text-right font-medium">Total P&L</th>
            </tr>
          </thead>
          <tbody>
            {data.map((row, i) => {
              const pnlColor = row.total_pnl > 0 ? 'text-profit' : row.total_pnl < 0 ? 'text-loss' : 'text-text-secondary'
              const wrColor = row.win_rate >= 50 ? 'text-profit' : 'text-loss'
              return (
                <tr key={i} className="border-b border-border/50 hover:bg-bg-elevated/50 transition-colors">
                  <td className="px-4 py-2.5 font-mono text-xs text-text-primary">{row.group}</td>
                  <td className="px-4 py-2.5 text-right font-mono tabular-nums text-xs">{row.trades}</td>
                  <td className="px-4 py-2.5 text-right font-mono tabular-nums text-xs text-profit">{row.wins}</td>
                  <td className="px-4 py-2.5 text-right font-mono tabular-nums text-xs text-loss">{row.losses}</td>
                  <td className={`px-4 py-2.5 text-right font-mono tabular-nums text-xs font-semibold ${wrColor}`}>{row.win_rate}%</td>
                  <td className={`px-4 py-2.5 text-right font-mono tabular-nums text-xs ${row.avg_pnl >= 0 ? 'text-profit' : 'text-loss'}`}>
                    {row.avg_pnl >= 0 ? '+' : ''}{row.avg_pnl.toFixed(4)}
                  </td>
                  <td className={`px-4 py-2.5 text-right font-mono tabular-nums text-xs font-semibold ${pnlColor}`}>
                    {row.total_pnl >= 0 ? '+' : ''}{row.total_pnl.toFixed(4)}
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
    </div>
  )
}
