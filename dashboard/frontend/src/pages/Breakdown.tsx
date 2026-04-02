import { useEffect, useState } from 'react'
import { api } from '../api/client'
import type { BreakdownRow } from '../types'
import BreakdownView from '../components/breakdown/BreakdownView'
import ExitTypeRatio from '../components/exits/ExitTypeRatio'
import type { ExitsData } from '../types'
import BotSelector from '../components/bots/BotSelector'
import { useGlobalFilter } from '../context/GlobalFilterContext'

interface Props {
  refreshTick: number
}

const TABS: { key: string; label: string }[] = [
  { key: 'asset', label: 'By Asset' },
  { key: 'timeframe', label: 'By Timeframe' },
  { key: 'direction', label: 'By Direction' },
  { key: 'exchange', label: 'By Exchange' },
  { key: 'bot', label: 'By Bot' },
]

export default function Breakdown({ refreshTick }: Props) {
  const [dim, setDim] = useState('asset')
  const [data, setData] = useState<BreakdownRow[]>([])
  const [exits, setExits] = useState<ExitsData | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [botId, setBotId] = useState<string | undefined>()
  const { mode } = useGlobalFilter()

  useEffect(() => {
    setLoading(true)
    Promise.all([api.breakdown(dim, botId, mode), api.exits(botId, mode)])
      .then(([bd, ex]) => {
        setData(bd.data)
        setExits(ex)
        setError(null)
      })
      .catch(e => setError(e.message))
      .finally(() => setLoading(false))
  }, [refreshTick, dim, botId, mode])

  return (
    <div className="space-y-6">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h1 className="text-text-primary text-lg font-semibold">Performance Breakdown</h1>
          <p className="text-text-muted text-xs mt-0.5">Slice performance by asset, timeframe, direction, exchange, or bot</p>
        </div>
        <BotSelector value={botId} onChange={setBotId} />
      </div>

      {/* Tabs */}
      <div className="flex gap-1 border-b border-border overflow-x-auto">
        {TABS.map(tab => (
          <button
            key={tab.key}
            onClick={() => setDim(tab.key)}
            className={`px-4 py-2 text-sm font-medium transition-colors border-b-2 -mb-px whitespace-nowrap ${
              dim === tab.key
                ? 'border-accent text-accent'
                : 'border-transparent text-text-muted hover:text-text-secondary'
            }`}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {error ? (
        <div className="bg-loss/10 border border-loss/30 rounded-lg p-4">
          <p className="text-loss text-sm">{error}</p>
        </div>
      ) : loading ? (
        <div className="text-text-muted text-sm animate-pulse py-12 text-center">Loading…</div>
      ) : (
        <div className="space-y-6">
          <BreakdownView data={data} />
          {exits && (
            <div className="max-w-sm">
              <ExitTypeRatio data={exits} />
            </div>
          )}
        </div>
      )}
    </div>
  )
}
