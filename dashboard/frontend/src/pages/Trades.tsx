import { useEffect, useState } from 'react'
import { api } from '../api/client'
import type { TradeRecord } from '../types'
import TradeLogTable from '../components/trades/TradeLogTable'
import BotSelector from '../components/bots/BotSelector'

interface Props {
  refreshTick: number
}

export default function Trades({ refreshTick }: Props) {
  const [trades, setTrades] = useState<TradeRecord[]>([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(0)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [expandedRow, setExpandedRow] = useState<number | null>(null)
  const [filters, setFilters] = useState({ symbol: '', direction: '', exit_type: '' })
  const [botId, setBotId] = useState<string | undefined>()
  const LIMIT = 50

  useEffect(() => {
    setLoading(true)
    api.trades({ limit: LIMIT, offset: page * LIMIT, ...filters, botId })
      .then(res => { setTrades(res.trades); setTotal(res.total); setError(null) })
      .catch(e => setError(e.message))
      .finally(() => setLoading(false))
  }, [refreshTick, page, filters, botId])

  function updateFilter(f: Partial<typeof filters>) {
    setFilters(prev => ({ ...prev, ...f }))
    setPage(0)
  }

  return (
    <div className="space-y-4">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h1 className="text-text-primary text-lg font-semibold">Trade Log</h1>
          <p className="text-text-muted text-xs mt-0.5">Executed trades only · P&amp;L estimated</p>
        </div>
        <BotSelector value={botId} onChange={setBotId} />
      </div>

      {error ? (
        <div className="bg-loss/10 border border-loss/30 rounded-lg p-4">
          <p className="text-loss text-sm">{error}</p>
        </div>
      ) : loading ? (
        <div className="text-text-muted text-sm animate-pulse py-12 text-center">Loading…</div>
      ) : (
        <TradeLogTable
          trades={trades}
          total={total}
          page={page}
          onPageChange={setPage}
          limit={LIMIT}
          filters={filters}
          onFilterChange={updateFilter}
          expandedRow={expandedRow}
          onExpandRow={setExpandedRow}
        />
      )}
    </div>
  )
}
