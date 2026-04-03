import { useCallback, useEffect, useState } from 'react'
import { RefreshCw } from 'lucide-react'
import { api } from '../../api/client'
import type { LiveOrder } from '../../types'

const AUTO_REFRESH_MS = 30_000

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

function TypeBadge({ type }: { type: string | null }) {
  if (!type) return <span className="text-text-muted text-xs">—</span>
  const map: Record<string, string> = {
    limit: 'bg-blue-500/15 text-blue-400',
    stop: 'bg-[#ef4444]/15 text-[#ef4444]',
    stop_market: 'bg-[#ef4444]/15 text-[#ef4444]',
    take_profit: 'bg-profit/15 text-profit',
    take_profit_market: 'bg-profit/15 text-profit',
    trigger: 'bg-orange-500/15 text-orange-400',
  }
  const cls = map[type.toLowerCase()] || 'bg-bg-elevated text-text-muted'
  return (
    <span className={`px-1.5 py-0.5 rounded text-[10px] font-semibold uppercase ${cls}`}>
      {type}
    </span>
  )
}

function SideBadge({ side }: { side: string | null }) {
  if (!side) return <span className="text-text-muted text-xs">—</span>
  const isBuy = side.toLowerCase() === 'buy'
  return (
    <span
      className={`px-1.5 py-0.5 rounded text-[10px] font-bold uppercase ${
        isBuy ? 'bg-profit/15 text-profit' : 'bg-loss/15 text-loss'
      }`}
    >
      {side.toUpperCase()}
    </span>
  )
}

export default function OrderHistory() {
  const [orders, setOrders] = useState<LiveOrder[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [lastRefresh, setLastRefresh] = useState<Date | null>(null)
  const [refreshing, setRefreshing] = useState(false)

  const load = useCallback(async () => {
    setRefreshing(true)
    try {
      const data = await api.getOrders()
      setOrders(data)
      setLastRefresh(new Date())
      setError(null)
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Failed to load orders')
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
          <h2 className="text-text-primary text-base font-semibold">Order History</h2>
          <p className="text-text-muted text-xs mt-0.5">
            Open SL/TP orders on exchange · auto-refreshes every 30s
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
          Loading orders…
        </div>
      ) : orders.length === 0 ? (
        <div className="bg-bg-card border border-border rounded-lg p-12 text-center">
          <p className="text-text-muted text-sm">No open orders on exchange.</p>
        </div>
      ) : (
        <div className="bg-bg-card border border-border rounded-lg overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-border">
                  {[
                    'Symbol',
                    'Type',
                    'Side',
                    'Size',
                    'Price',
                    'Trigger',
                    'Reduce Only',
                    'Time',
                    'Network',
                  ].map(col => (
                    <th
                      key={col}
                      className="px-4 py-3 text-left text-text-muted text-xs uppercase tracking-wider font-medium"
                    >
                      {col}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody className="divide-y divide-border">
                {orders.map((order, i) => (
                  <tr key={i} className="hover:bg-bg-elevated transition-colors">
                    <td className="px-4 py-3 font-mono text-text-primary text-xs font-semibold">
                      {order.symbol ?? '—'}
                    </td>
                    <td className="px-4 py-3">
                      <TypeBadge type={order.type} />
                    </td>
                    <td className="px-4 py-3">
                      <SideBadge side={order.side} />
                    </td>
                    <td className="px-4 py-3 font-mono text-text-secondary text-xs">
                      {order.amount != null ? order.amount : '—'}
                    </td>
                    <td className="px-4 py-3 font-mono text-text-secondary text-xs">
                      {order.price != null ? order.price.toFixed(4) : '—'}
                    </td>
                    <td className="px-4 py-3 font-mono text-text-secondary text-xs">
                      {order.trigger != null ? order.trigger.toFixed(4) : '—'}
                    </td>
                    <td className="px-4 py-3 text-xs text-text-muted">
                      {order.reduce_only ? (
                        <span className="text-[#22c55e]">Yes</span>
                      ) : (
                        <span>No</span>
                      )}
                    </td>
                    <td className="px-4 py-3 text-text-muted text-xs font-mono">
                      {order.datetime
                        ? new Date(order.datetime).toLocaleTimeString([], {
                            hour: '2-digit',
                            minute: '2-digit',
                          })
                        : '—'}
                    </td>
                    <td className="px-4 py-3">
                      <NetworkBadge network={order.network} />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      <div className="text-xs text-text-muted">
        {orders.length} open order{orders.length !== 1 ? 's' : ''}
      </div>
    </div>
  )
}
