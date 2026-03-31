import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Cell,
} from 'recharts'
import type { AgreementRow } from '../../types'

interface Props {
  data: AgreementRow[]
}

const GRADIENT_COLORS = ['#3b82f6', '#22c55e', '#ef4444', '#6b7280']

export default function AgentAgreement({ data }: Props) {
  const sorted = [...data].sort((a, b) => {
    const order = ['3/3', '2/3', '1/3', '0/3']
    return order.indexOf(a.agreement_level) - order.indexOf(b.agreement_level)
  })

  return (
    <div className="bg-bg-card border border-border rounded-lg p-5">
      <h3 className="text-text-primary text-sm font-semibold mb-1">Agent Agreement vs Win Rate</h3>
      <p className="text-text-muted text-xs mb-4">Higher agreement → higher win rate (hypothesis)</p>
      <ResponsiveContainer width="100%" height={200}>
        <BarChart data={sorted} margin={{ top: 4, right: 4, left: 0, bottom: 0 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#2d3039" vertical={false} />
          <XAxis dataKey="agreement_level" tick={{ fill: '#6b7280', fontSize: 11 }} axisLine={false} tickLine={false} />
          <YAxis tick={{ fill: '#6b7280', fontSize: 11 }} axisLine={false} tickLine={false} domain={[0, 100]} unit="%" />
          <Tooltip
            contentStyle={{ background: '#1a1d26', border: '1px solid #2d3039', borderRadius: 6 }}
            labelStyle={{ color: '#9ca3af', fontSize: 11 }}
            itemStyle={{ color: '#e5e7eb', fontFamily: 'monospace' }}
            formatter={(val: number, _name: string, props: any) => [
              `${val}% (${props.payload.count} trades)`,
              'Win Rate',
            ]}
          />
          <Bar dataKey="win_rate" radius={[4, 4, 0, 0]}>
            {sorted.map((_, i) => (
              <Cell key={i} fill={GRADIENT_COLORS[i] ?? '#6b7280'} />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  )
}
