import type { OverviewData } from '../../types'

interface Props {
  data: OverviewData
}

function Card({
  label,
  value,
  sub,
  positive,
}: {
  label: string
  value: string
  sub?: string
  positive?: boolean | null
}) {
  const color =
    positive === true
      ? 'text-profit'
      : positive === false
      ? 'text-loss'
      : 'text-text-primary'

  return (
    <div className="bg-bg-card border border-border rounded-lg p-4">
      <p className="text-text-muted text-xs uppercase tracking-wider mb-2">{label}</p>
      <p className={`text-2xl font-bold font-mono tabular-nums ${color}`}>{value}</p>
      {sub && <p className="text-text-muted text-xs mt-1">{sub}</p>}
    </div>
  )
}

export default function KPICards({ data }: Props) {
  const pnlPositive = data.total_pnl > 0 ? true : data.total_pnl < 0 ? false : null

  return (
    <div className="grid grid-cols-3 xl:grid-cols-6 gap-4">
      <Card
        label="Total Trades"
        value={String(data.total_trades)}
        sub={`Today: ${data.trades_today}`}
      />
      <Card
        label="Win Rate"
        value={`${data.win_rate}%`}
        sub={`${data.wins}W / ${data.losses}L`}
        positive={data.win_rate >= 50 ? true : false}
      />
      <Card
        label="Total P&L"
        value={`${data.total_pnl >= 0 ? '+' : ''}${data.total_pnl.toFixed(2)}`}
        sub="estimated"
        positive={pnlPositive}
      />
      <Card
        label="Profit Factor"
        value={data.profit_factor === 0 ? 'N/A' : data.profit_factor.toFixed(2)}
        positive={data.profit_factor > 1 ? true : data.profit_factor < 1 ? false : null}
      />
      <Card
        label="Max Drawdown"
        value={data.max_drawdown.toFixed(2)}
        positive={data.max_drawdown === 0 ? null : false}
      />
      <Card
        label="Sharpe Ratio"
        value={data.sharpe_ratio.toFixed(2)}
        positive={data.sharpe_ratio > 0 ? true : data.sharpe_ratio < 0 ? false : null}
      />
    </div>
  )
}
