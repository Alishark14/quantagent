import { useCallback, useEffect, useState } from 'react'
import { RefreshCw } from 'lucide-react'
import { api } from '../../api/client'
import type { LivePosition } from '../../types'

const AUTO_REFRESH_MS = 30_000

function PnlCell({ value }: { value: number }) {
  return (
    <span
      className={`font-mono tabular-nums font-semibold ${
        value > 0 ? 'text-profit' : value < 0 ? 'text-loss' : 'text-text-muted'
      }`}
    >
      {value >= 0 ? '+' : ''}
      {value.toFixed(4)}
    </span>
  )
}

function SideBadge({ side }: { side: string }) {
  const isLong = side.toLowerCase() === 'long'
  return (
    <span
      className={`px-1.5 py-0.5 rounded text-[10px] font-bold uppercase ${
        isLong ? 'bg-profit/15 text-profit' : 'bg-loss/15 text-loss'
      }`}
    >
      {side.toUpperCase()}
    </span>
  )
}

function NetworkBadge({ network }: { network: string }) {
  const isTestnet = network === 'testnet'
  return (
    <span
      className={`px-1.5 py-0.5 rounded text-[10px] font-medium ${
        isTestnet
          ? 'bg-yellow-500/15 text-yellow-400'
          : 'bg-[#22c55e]/15 text-[#22c55e]'
      }`}
    >
      {isTestnet ? 'testnet' : 'mainnet'}
    </span>
  )
}

export default function OpenPositions() {
  const [positions, setPositions] = useState<LivePosition[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [lastRefresh, setLastRefresh] = useState<Date | null>(null)
  const [refreshing, setRefreshing] = useState(false)

  const load = useCallback(async () => {
    setRefreshing(true)
    try {
      const data = await api.getPositions()
      setPositions(data)
      setLastRefresh(new Date())
      setError(null)
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Failed to load positions')
    } finally {
      setLoading(false)
      setRefreshing(false)
    }
  }, [])

  useEffect(() => {
    load()
    const id = setInterval(load, AUTO_REFRESH_MS)
    return () => clearInterval(id)
  }, [load])

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between gap-4">
        <div>
          <h2 className="text-text-primary text-base font-semibold">Open Positions</h2>
          <p className="text-text-muted text-xs mt-0.5">
            Live from exchange · auto-refreshes every 30s
          </p>
        </div>
        <div className="flex items-center gap-3">
          {lastRefresh && (
            <span className="text-text-muted text-xs">
              Updated {lastRefresh.toLocaleTimeString()}
            </span>
          )}
          <button
            onClick={load}
            disabled={refreshing}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded bg-bg-card border border-border text-text-secondary hover:text-text-primary text-xs transition-colors disabled:opacity-50"
          >
            <RefreshCw size={12} className={refreshing ? 'animate-spin' : ''} />
            Refresh
          </button>
        </div>
      </div>

      {error ? (
        <div className="bg-loss/10 border border-loss/30 rounded-lg p-4">
          <p className="text-loss text-sm">{error}</p>
        </div>
      ) : loading ? (
        <div className="text-text-muted text-sm animate-pulse py-12 text-center">
          Loading positions…
        </div>
      ) : positions.length === 0 ? (
        <div className="bg-bg-card border border-border rounded-lg p-12 text-center">
          <p className="text-text-muted text-sm">No open positions on exchange.</p>
        </div>
      ) : (
        <div className="bg-bg-card border border-border rounded-lg overflow-hidden">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-border">
                {['Symbol', 'Side', 'Size', 'Entry Price', 'Unrealized P&L', 'Exchange', 'Network'].map(
                  col => (
                    <th
                      key={col}
                      className="px-4 py-3 text-left text-text-muted text-xs uppercase tracking-wider font-medium"
                    >
                      {col}
                    </th>
                  )
                )}
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {positions.map((pos, i) => (
                <tr key={i} className="hover:bg-bg-elevated transition-colors">
                  <td className="px-4 py-3 font-mono text-text-primary text-xs font-semibold">
                    {pos.symbol}
                  </td>
                  <td className="px-4 py-3">
                    <SideBadge side={pos.side} />
                  </td>
                  <td className="px-4 py-3 font-mono text-text-secondary text-xs">
                    {pos.size}
                  </td>
                  <td className="px-4 py-3 font-mono text-text-secondary text-xs">
                    {pos.entry_price > 0 ? pos.entry_price.toFixed(4) : '—'}
                  </td>
                  <td className="px-4 py-3">
                    <PnlCell value={pos.unrealized_pnl} />
                  </td>
                  <td className="px-4 py-3 text-text-muted text-xs capitalize">
                    {pos.exchange}
                  </td>
                  <td className="px-4 py-3">
                    <NetworkBadge network={pos.network} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <div className="flex items-center justify-between text-xs text-text-muted">
        <span>{positions.length} position{positions.length !== 1 ? 's' : ''}</span>
        <span>Data from exchange — not from local DB</span>
      </div>
    </div>
  )
}
