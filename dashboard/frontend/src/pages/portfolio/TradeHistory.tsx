import { useEffect, useMemo, useState } from 'react'
import { Download } from 'lucide-react'
import {
  useReactTable,
  getCoreRowModel,
  getSortedRowModel,
  flexRender,
  createColumnHelper,
  type SortingState,
} from '@tanstack/react-table'
import { ChevronUp, ChevronDown, ChevronsUpDown } from 'lucide-react'
import { api } from '../../api/client'
import type { TradeRecord } from '../../types'
import BotSelector from '../../components/bots/BotSelector'
import { useGlobalFilter } from '../../context/GlobalFilterContext'

interface Props {
  refreshTick: number
}

const helper = createColumnHelper<TradeRecord>()

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

function ExitBadge({ reason }: { reason: string }) {
  const map: Record<string, string> = {
    stop_loss: 'bg-loss/15 text-loss',
    take_profit: 'bg-profit/15 text-profit',
    time_exit: 'bg-yellow-500/15 text-yellow-400',
    manual: 'bg-bg-elevated text-text-secondary',
    guardian: 'bg-purple-500/15 text-purple-400',
  }
  const label: Record<string, string> = {
    stop_loss: 'SL',
    take_profit: 'TP',
    time_exit: 'Time',
    manual: 'Manual',
    guardian: 'Guardian',
  }
  const cls = map[reason] || 'bg-bg-elevated text-text-muted'
  return (
    <span className={`px-1.5 py-0.5 rounded text-[10px] font-semibold ${cls}`}>
      {label[reason] || reason || '—'}
    </span>
  )
}

function duration(entry: string, exit: string | null | undefined): string {
  if (!entry || !exit) return '—'
  try {
    const ms = new Date(exit).getTime() - new Date(entry).getTime()
    if (ms < 0) return '—'
    const h = Math.floor(ms / 3600000)
    const m = Math.floor((ms % 3600000) / 60000)
    return h > 0 ? `${h}h ${m}m` : `${m}m`
  } catch {
    return '—'
  }
}

function SortIcon({ sorted }: { sorted: false | 'asc' | 'desc' }) {
  if (sorted === 'asc') return <ChevronUp size={12} />
  if (sorted === 'desc') return <ChevronDown size={12} />
  return <ChevronsUpDown size={12} className="opacity-30" />
}

const LIMIT = 50

export default function TradeHistory({ refreshTick }: Props) {
  const [trades, setTrades] = useState<TradeRecord[]>([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(0)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [botId, setBotId] = useState<string | undefined>()
  const [sorting, setSorting] = useState<SortingState>([{ id: 'timestamp', desc: true }])
  const [filterSym, setFilterSym] = useState('')
  const [filterDir, setFilterDir] = useState('')
  const { mode } = useGlobalFilter()

  useEffect(() => {
    setLoading(true)
    api
      .trades({
        limit: LIMIT,
        offset: page * LIMIT,
        symbol: filterSym,
        direction: filterDir,
        botId,
        mode,
        status: 'closed',
      })
      .then(res => {
        setTrades(res.trades)
        setTotal(res.total)
        setError(null)
      })
      .catch(e => setError(e.message))
      .finally(() => setLoading(false))
  }, [refreshTick, page, filterSym, filterDir, botId, mode])

  // Export CSV
  function exportCsv() {
    const headers = [
      'Date',
      'Symbol',
      'Bot',
      'Direction',
      'Size (USD)',
      'Entry',
      'Exit',
      'P&L',
      'P&L%',
      'Exit Reason',
      'Duration',
      'RR',
    ]
    const rows = trades.map(t => [
      t.timestamp,
      t.symbol,
      t.bot_name,
      t.direction,
      t.position_size_usd?.toFixed(2) ?? '',
      t.entry_price.toFixed(4),
      t.exit_price?.toFixed(4) ?? '',
      t.pnl.toFixed(4),
      t.pnl_pct.toFixed(2),
      t.exit_reason || t.exit_type,
      duration(t.entry_time || t.timestamp, t.exit_time),
      t.rr_ratio?.toFixed(2) ?? '',
    ])
    const csv = [headers, ...rows].map(r => r.join(',')).join('\n')
    const blob = new Blob([csv], { type: 'text/csv' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `trade_history_${new Date().toISOString().slice(0, 10)}.csv`
    a.click()
    URL.revokeObjectURL(url)
  }

  const columns = useMemo(
    () => [
      helper.accessor('timestamp', {
        header: 'Date',
        cell: info => (
          <span className="text-text-secondary text-xs font-mono">
            {new Date(info.getValue()).toLocaleString([], {
              month: 'short',
              day: 'numeric',
              hour: '2-digit',
              minute: '2-digit',
            })}
          </span>
        ),
      }),
      helper.accessor('symbol', {
        header: 'Symbol',
        cell: info => (
          <span className="font-mono text-text-primary text-xs font-semibold">
            {info.getValue()}
          </span>
        ),
      }),
      helper.accessor('bot_name', {
        header: 'Bot',
        cell: info => (
          <span className="text-text-muted text-xs">{info.getValue() || '—'}</span>
        ),
      }),
      helper.accessor('direction', {
        header: 'Dir',
        cell: info => (
          <span
            className={`text-xs font-bold ${
              info.getValue() === 'LONG' ? 'text-profit' : 'text-loss'
            }`}
          >
            {info.getValue()}
          </span>
        ),
      }),
      helper.accessor('position_size_usd', {
        header: 'Size',
        cell: info => (
          <span className="font-mono text-text-secondary text-xs">
            ${(info.getValue() ?? 0).toFixed(0)}
          </span>
        ),
      }),
      helper.accessor('entry_price', {
        header: 'Entry',
        cell: info => (
          <span className="font-mono text-text-secondary text-xs">
            {info.getValue().toFixed(4)}
          </span>
        ),
      }),
      helper.accessor('exit_price', {
        header: 'Exit',
        cell: info => (
          <span className="font-mono text-text-secondary text-xs">
            {info.getValue()?.toFixed(4) ?? '—'}
          </span>
        ),
      }),
      helper.accessor('pnl', {
        header: 'P&L',
        cell: info => <PnlCell value={info.getValue()} />,
      }),
      helper.accessor('pnl_pct', {
        header: 'P&L%',
        cell: info => (
          <span
            className={`font-mono text-xs ${
              info.getValue() > 0
                ? 'text-profit'
                : info.getValue() < 0
                ? 'text-loss'
                : 'text-text-muted'
            }`}
          >
            {info.getValue() >= 0 ? '+' : ''}
            {info.getValue().toFixed(2)}%
          </span>
        ),
      }),
      helper.accessor('exit_reason', {
        header: 'Exit',
        cell: info => <ExitBadge reason={info.getValue() ?? ''} />,
      }),
      helper.display({
        id: 'duration',
        header: 'Duration',
        cell: ({ row }) => (
          <span className="text-text-muted text-xs">
            {duration(
              row.original.entry_time || row.original.timestamp,
              row.original.exit_time
            )}
          </span>
        ),
      }),
      helper.accessor('rr_ratio', {
        header: 'RR',
        cell: info => (
          <span className="font-mono text-text-muted text-xs">
            {info.getValue()?.toFixed(2) ?? '—'}
          </span>
        ),
      }),
    ],
    []
  )

  const table = useReactTable({
    data: trades,
    columns,
    state: { sorting },
    onSortingChange: setSorting,
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
    manualPagination: true,
    pageCount: Math.ceil(total / LIMIT),
  })

  const totalPages = Math.ceil(total / LIMIT)

  return (
    <div className="space-y-4">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h2 className="text-text-primary text-base font-semibold">Trade History</h2>
          <p className="text-text-muted text-xs mt-0.5">
            Closed trades with confirmed P&amp;L
          </p>
        </div>
        <div className="flex items-center gap-2">
          <BotSelector value={botId} onChange={setBotId} />
          <button
            onClick={exportCsv}
            disabled={trades.length === 0}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded bg-bg-card border border-border text-text-secondary hover:text-text-primary text-xs transition-colors disabled:opacity-40"
          >
            <Download size={12} />
            CSV
          </button>
        </div>
      </div>

      {/* Filters */}
      <div className="flex flex-wrap gap-2">
        <input
          type="text"
          placeholder="Filter symbol…"
          value={filterSym}
          onChange={e => { setFilterSym(e.target.value); setPage(0) }}
          className="bg-bg-card border border-border rounded px-3 py-1.5 text-xs text-text-primary placeholder:text-text-muted focus:outline-none focus:border-accent w-40"
        />
        <select
          value={filterDir}
          onChange={e => { setFilterDir(e.target.value); setPage(0) }}
          className="bg-bg-card border border-border rounded px-2 py-1.5 text-xs text-text-primary focus:outline-none focus:border-accent"
        >
          <option value="">All directions</option>
          <option value="LONG">Long</option>
          <option value="SHORT">Short</option>
        </select>
      </div>

      {error ? (
        <div className="bg-loss/10 border border-loss/30 rounded-lg p-4">
          <p className="text-loss text-sm">{error}</p>
        </div>
      ) : loading ? (
        <div className="text-text-muted text-sm animate-pulse py-12 text-center">Loading…</div>
      ) : trades.length === 0 ? (
        <div className="bg-bg-card border border-border rounded-lg p-12 text-center">
          <p className="text-text-muted text-sm">No closed trades found.</p>
        </div>
      ) : (
        <div className="bg-bg-card border border-border rounded-lg overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                {table.getHeaderGroups().map(hg => (
                  <tr key={hg.id} className="border-b border-border">
                    {hg.headers.map(header => (
                      <th
                        key={header.id}
                        className="px-3 py-3 text-left text-text-muted text-xs uppercase tracking-wider font-medium cursor-pointer select-none"
                        onClick={header.column.getToggleSortingHandler()}
                      >
                        <div className="flex items-center gap-1">
                          {flexRender(header.column.columnDef.header, header.getContext())}
                          {header.column.getCanSort() && (
                            <SortIcon sorted={header.column.getIsSorted()} />
                          )}
                        </div>
                      </th>
                    ))}
                  </tr>
                ))}
              </thead>
              <tbody className="divide-y divide-border">
                {table.getRowModel().rows.map(row => (
                  <tr key={row.id} className="hover:bg-bg-elevated transition-colors">
                    {row.getVisibleCells().map(cell => (
                      <td key={cell.id} className="px-3 py-2.5">
                        {flexRender(cell.column.columnDef.cell, cell.getContext())}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {/* Pagination */}
          {totalPages > 1 && (
            <div className="px-4 py-3 border-t border-border flex items-center justify-between">
              <span className="text-text-muted text-xs">
                {total} trades · page {page + 1} of {totalPages}
              </span>
              <div className="flex items-center gap-2">
                <button
                  onClick={() => setPage(p => Math.max(0, p - 1))}
                  disabled={page === 0}
                  className="px-2 py-1 rounded bg-bg-elevated text-text-secondary text-xs disabled:opacity-40 hover:text-text-primary transition-colors"
                >
                  ← Prev
                </button>
                <button
                  onClick={() => setPage(p => Math.min(totalPages - 1, p + 1))}
                  disabled={page >= totalPages - 1}
                  className="px-2 py-1 rounded bg-bg-elevated text-text-secondary text-xs disabled:opacity-40 hover:text-text-primary transition-colors"
                >
                  Next →
                </button>
              </div>
            </div>
          )}
        </div>
      )}

      <div className="text-xs text-text-muted">
        {total} closed trade{total !== 1 ? 's' : ''}
      </div>
    </div>
  )
}
