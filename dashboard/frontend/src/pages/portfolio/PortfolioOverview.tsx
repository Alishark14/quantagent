import { useEffect, useState } from 'react'
import { api } from '../../api/client'
import type { OverviewData, TradeRecord } from '../../types'
import EquityCurve from '../../components/overview/EquityCurve'
import RecentTrades from '../../components/overview/RecentTrades'
import BotSelector from '../../components/bots/BotSelector'
import { useGlobalFilter } from '../../context/GlobalFilterContext'

interface Props {
  refreshTick: number
}

function KPICard({
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

export default function PortfolioOverview({ refreshTick }: Props) {
  const [overview, setOverview] = useState<OverviewData | null>(null)
  const [recentTrades, setRecentTrades] = useState<TradeRecord[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [botId, setBotId] = useState<string | undefined>()
  const [dailyApiCost, setDailyApiCost] = useState(0)
  const { mode } = useGlobalFilter()

  useEffect(() => {
    setLoading(true)
    Promise.all([
      api.overview(botId, mode),
      api.trades({ limit: 10, offset: 0, status: 'closed', botId, mode }),
      api.apiCosts(botId, undefined, mode).catch(() => null),
    ])
      .then(([ov, tr, costs]) => {
        setOverview(ov)
        setRecentTrades(tr.trades)
        setDailyApiCost(costs?.daily_cost ?? 0)
        setError(null)
      })
      .catch(e => setError(e.message))
      .finally(() => setLoading(false))
  }, [refreshTick, botId, mode])

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="text-text-muted text-sm animate-pulse">Loading…</div>
      </div>
    )
  }

  if (error) {
    return (
      <div className="bg-loss/10 border border-loss/30 rounded-lg p-6">
        <p className="text-loss text-sm font-medium">Failed to load data</p>
        <p className="text-text-muted text-xs mt-1">{error}</p>
      </div>
    )
  }

  if (!overview) return null

  const realized = overview.total_pnl - (overview.unrealized_pnl ?? 0)
  const unrealized = overview.unrealized_pnl ?? 0
  const totalPnl = overview.total_pnl
  const dailyPnl = overview.daily_pnl ?? 0
  const netPnl = dailyPnl - dailyApiCost
  const openTrades = overview.open_trades ?? 0

  return (
    <div className="space-y-6">
      <div className="flex items-start justify-between gap-4">
        <h2 className="text-text-primary text-base font-semibold">Overview</h2>
        <BotSelector value={botId} onChange={setBotId} />
      </div>

      {/* KPI grid */}
      <div className="grid grid-cols-2 sm:grid-cols-4 xl:grid-cols-8 gap-4">
        <KPICard
          label="Total Trades"
          value={String(overview.total_trades)}
          sub={`Today: ${overview.trades_today}${openTrades > 0 ? ` · ${openTrades} open` : ''}`}
        />
        <KPICard
          label="Win Rate"
          value={`${overview.win_rate}%`}
          sub={`${overview.wins}W / ${overview.losses}L`}
          positive={overview.win_rate >= 50}
        />
        <KPICard
          label="Realized P&L"
          value={`${realized >= 0 ? '+' : ''}${realized.toFixed(2)}`}
          sub="closed trades"
          positive={realized > 0 ? true : realized < 0 ? false : null}
        />
        <KPICard
          label="Unrealized P&L"
          value={`${unrealized >= 0 ? '+' : ''}${unrealized.toFixed(2)}`}
          sub="open positions"
          positive={unrealized > 0 ? true : unrealized < 0 ? false : null}
        />
        <KPICard
          label="Total P&L"
          value={`${totalPnl >= 0 ? '+' : ''}${totalPnl.toFixed(2)}`}
          sub="realized + unrealized"
          positive={totalPnl > 0 ? true : totalPnl < 0 ? false : null}
        />
        <KPICard
          label="Daily P&L"
          value={`${dailyPnl >= 0 ? '+' : ''}${dailyPnl.toFixed(2)}`}
          positive={dailyPnl > 0 ? true : dailyPnl < 0 ? false : null}
        />
        <KPICard
          label="API Cost"
          value={`$${dailyApiCost.toFixed(3)}`}
          positive={null}
        />
        <KPICard
          label="Net P&L"
          value={`${netPnl >= 0 ? '+' : ''}${netPnl.toFixed(2)}`}
          sub="P&L minus API cost"
          positive={netPnl > 0 ? true : netPnl < 0 ? false : null}
        />
      </div>

      {/* Secondary stats */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
        <KPICard
          label="Sharpe Ratio"
          value={overview.sharpe_ratio.toFixed(2)}
          positive={overview.sharpe_ratio > 0 ? true : overview.sharpe_ratio < 0 ? false : null}
        />
        <KPICard
          label="Max Drawdown"
          value={`$${overview.max_drawdown.toFixed(2)}`}
          positive={null}
        />
        <KPICard
          label="Profit Factor"
          value={overview.profit_factor.toFixed(2)}
          positive={overview.profit_factor >= 1 ? true : overview.profit_factor < 1 ? false : null}
        />
        <KPICard
          label="Expectancy"
          value={`${overview.expectancy >= 0 ? '+' : ''}${overview.expectancy.toFixed(4)}`}
          positive={overview.expectancy > 0 ? true : overview.expectancy < 0 ? false : null}
        />
      </div>

      <EquityCurve data={overview.equity_curve} />
      <RecentTrades trades={recentTrades} />
    </div>
  )
}
