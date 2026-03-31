import { useEffect, useState } from 'react'
import { api } from '../api/client'
import type { OverviewData, TradeRecord } from '../types'
import KPICards from '../components/overview/KPICards'
import EquityCurve from '../components/overview/EquityCurve'
import RecentTrades from '../components/overview/RecentTrades'
import BotSelector from '../components/bots/BotSelector'

interface Props {
  refreshTick: number
}

export default function Overview({ refreshTick }: Props) {
  const [overview, setOverview] = useState<OverviewData | null>(null)
  const [recentTrades, setRecentTrades] = useState<TradeRecord[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [botId, setBotId] = useState<string | undefined>()

  useEffect(() => {
    setLoading(true)
    Promise.all([api.overview(botId), api.trades({ limit: 10, offset: 0, botId })])
      .then(([ov, tr]) => {
        setOverview(ov)
        setRecentTrades(tr.trades)
        setError(null)
      })
      .catch(e => setError(e.message))
      .finally(() => setLoading(false))
  }, [refreshTick, botId])

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
        <p className="text-text-muted text-xs mt-2">Make sure the backend is running: <code className="font-mono">uvicorn app:app --port 8001</code></p>
      </div>
    )
  }

  if (!overview) return null

  return (
    <div className="space-y-6">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h1 className="text-text-primary text-lg font-semibold">Overview</h1>
          <p className="text-text-muted text-xs mt-0.5">P&amp;L values are estimated (55% TP assumption) until Deribit outcome tracker is live</p>
        </div>
        <BotSelector value={botId} onChange={setBotId} />
      </div>
      <KPICards data={overview} />
      <EquityCurve data={overview.equity_curve} />
      <RecentTrades trades={recentTrades} />
    </div>
  )
}
