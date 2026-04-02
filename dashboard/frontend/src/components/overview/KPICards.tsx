import type { OverviewData } from '../../types'

interface Props {
  data: OverviewData
  dailyApiCost?: number
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

export default function KPICards({ data, dailyApiCost = 0 }: Props) {
  const pnlPositive = data.total_pnl > 0 ? true : data.total_pnl < 0 ? false : null
  const dailyPnl = data.daily_pnl ?? 0
  const dailyPositive = dailyPnl > 0 ? true : dailyPnl < 0 ? false : null
  const openTrades = data.open_trades ?? 0
  const netPnl = dailyPnl - dailyApiCost
  const netPositive = netPnl > 0 ? true : netPnl < 0 ? false : null

  return (
    <div className="grid grid-cols-2 sm:grid-cols-4 xl:grid-cols-7 gap-4">
      <Card
        label="Total Trades"
        value={String(data.total_trades)}
        sub={`Today: ${data.trades_today}${openTrades > 0 ? ` · ${openTrades} open` : ''}`}
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
        sub="realized"
        positive={pnlPositive}
      />
      <Card
        label="Daily P&L"
        value={`${dailyPnl >= 0 ? '+' : ''}${dailyPnl.toFixed(2)}`}
        positive={dailyPositive}
      />
      <Card
        label="Daily API Cost"
        value={`$${dailyApiCost.toFixed(3)}`}
        positive={null}
      />
      <Card
        label="Net P&L"
        value={`${netPnl >= 0 ? '+' : ''}${netPnl.toFixed(2)}`}
        sub="P&L minus API cost"
        positive={netPositive}
      />
      <Card
        label="Sharpe Ratio"
        value={data.sharpe_ratio.toFixed(2)}
        positive={data.sharpe_ratio > 0 ? true : data.sharpe_ratio < 0 ? false : null}
      />
    </div>
  )
}
