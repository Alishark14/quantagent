import { useMemo, useState } from 'react'
import {
  useReactTable,
  getCoreRowModel,
  getSortedRowModel,
  flexRender,
  createColumnHelper,
  type SortingState,
} from '@tanstack/react-table'
import { ChevronUp, ChevronDown, ChevronsUpDown } from 'lucide-react'
import type { TradeRecord } from '../../types'

interface Props {
  trades: TradeRecord[]
  total: number
  page: number
  onPageChange: (p: number) => void
  limit: number
  filters: { symbol: string; direction: string; exit_type: string; bot_name: string }
  onFilterChange: (f: Partial<{ symbol: string; direction: string; exit_type: string; bot_name: string }>) => void
  expandedRow: number | null
  onExpandRow: (i: number | null) => void
}

const helper = createColumnHelper<TradeRecord>()

const BOT_COLOR_PALETTE = [
  'bg-blue-500/20 text-blue-400',
  'bg-purple-500/20 text-purple-400',
  'bg-cyan-500/20 text-cyan-400',
  'bg-orange-500/20 text-orange-400',
  'bg-pink-500/20 text-pink-400',
  'bg-teal-500/20 text-teal-400',
  'bg-indigo-500/20 text-indigo-400',
  'bg-amber-500/20 text-amber-400',
]

function botColor(name: string): string {
  let hash = 0
  for (let i = 0; i < name.length; i++) {
    hash = (hash * 31 + name.charCodeAt(i)) & 0xffffffff
  }
  return BOT_COLOR_PALETTE[Math.abs(hash) % BOT_COLOR_PALETTE.length]
}

function BotBadge({ name }: { name: string }) {
  if (!name || name === 'unknown') {
    return <span className="text-text-muted text-xs">—</span>
  }
  return (
    <span className={`px-1.5 py-0.5 rounded text-xs font-medium truncate max-w-[100px] inline-block ${botColor(name)}`}>
      {name}
    </span>
  )
}

function PnlCell({ value }: { value: number }) {
  return (
    <span className={`font-mono tabular-nums font-semibold ${value > 0 ? 'text-profit' : value < 0 ? 'text-loss' : 'text-text-muted'}`}>
      {value >= 0 ? '+' : ''}{value.toFixed(4)}
    </span>
  )
}

function ExitBadge({ type, reason }: { type: string; reason?: string }) {
  const map: Record<string, string> = {
    tp: 'bg-profit/15 text-profit',
    sl: 'bg-loss/15 text-loss',
    time: 'bg-yellow-500/15 text-yellow-400',
    unknown: 'bg-bg-elevated text-text-muted',
  }
  const labelMap: Record<string, string> = {
    stop_loss: 'SL',
    take_profit: 'TP',
    time_exit: 'Time',
    manual: 'Manual',
    guardian: 'Guardian',
    monitor: 'Monitor',
  }
  const label = reason ? (labelMap[reason] ?? reason.toUpperCase()) : type.toUpperCase()
  return <span className={`px-1.5 py-0.5 rounded text-xs font-semibold uppercase ${map[type] ?? map.unknown}`}>{label}</span>
}

function StatusDot({ status, pnl }: { status: string; pnl: number }) {
  if (status === 'open') {
    return <span className="inline-flex items-center gap-1 text-xs text-yellow-400"><span className="w-1.5 h-1.5 rounded-full bg-yellow-400 animate-pulse inline-block" />Open</span>
  }
  return <span className={`inline-flex items-center gap-1 text-xs ${pnl >= 0 ? 'text-profit' : 'text-loss'}`}><span className={`w-1.5 h-1.5 rounded-full inline-block ${pnl >= 0 ? 'bg-profit' : 'bg-loss'}`} />Closed</span>
}

function Duration({ entryTime, exitTime }: { entryTime?: string; exitTime?: string | null }) {
  if (!entryTime || !exitTime) return <span className="text-text-muted text-xs">—</span>
  try {
    const ms = new Date(exitTime).getTime() - new Date(entryTime).getTime()
    if (ms < 0) return <span className="text-text-muted text-xs">—</span>
    const mins = Math.floor(ms / 60000)
    if (mins < 60) return <span className="font-mono text-xs text-text-muted">{mins}m</span>
    const hrs = Math.floor(mins / 60)
    const rem = mins % 60
    return <span className="font-mono text-xs text-text-muted">{hrs}h{rem > 0 ? ` ${rem}m` : ''}</span>
  } catch {
    return <span className="text-text-muted text-xs">—</span>
  }
}

function exportCSV(trades: TradeRecord[]) {
  const headers = ['bot_name','timestamp','symbol','direction','entry_price','stop_loss','take_profit','pnl','pnl_pct','exit_type','rr_ratio','atr_value','agreement_level']
  const rows = trades.map(t =>
    [t.bot_name, t.timestamp, t.symbol, t.direction, t.entry_price, t.stop_loss, t.take_profit, t.pnl, t.pnl_pct, t.exit_type, t.rr_ratio, t.atr_value ?? '', t.agreement_level].join(',')
  )
  const csv = [headers.join(','), ...rows].join('\n')
  const blob = new Blob([csv], { type: 'text/csv' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = 'quantagent_trades.csv'
  a.click()
  URL.revokeObjectURL(url)
}

const COLUMNS = [
  helper.display({
    id: 'status',
    header: 'Status',
    cell: ({ row }) => <StatusDot status={row.original.status} pnl={row.original.pnl} />,
  }),
  helper.accessor('bot_name', {
    header: 'Bot',
    cell: i => <BotBadge name={i.getValue()} />,
  }),
  helper.accessor('timestamp', {
    header: 'Date / Time',
    cell: i => <span className="font-mono text-xs text-text-muted tabular-nums whitespace-nowrap">{new Date(i.getValue()).toLocaleString()}</span>,
  }),
  helper.accessor('symbol', {
    header: 'Symbol',
    cell: i => <span className="font-mono text-xs">{i.getValue()}</span>,
  }),
  helper.accessor('direction', {
    header: 'Dir',
    cell: i => (
      <span className={`px-2 py-0.5 rounded text-xs font-semibold ${i.getValue() === 'LONG' ? 'bg-profit/15 text-profit' : 'bg-loss/15 text-loss'}`}>
        {i.getValue()}
      </span>
    ),
  }),
  helper.display({
    id: 'size',
    header: 'Size',
    cell: ({ row }) => {
      const t = row.original
      const usd = t.position_size_usd ?? 0
      const qty = t.quantity ?? 0
      const sym = (t.symbol ?? '').replace('USDT', '').replace('USDC', '')
      if (usd === 0) return <span className="text-text-muted text-xs">—</span>
      return (
        <div>
          <div className="font-mono tabular-nums text-xs">${usd.toFixed(2)}</div>
          {qty > 0 && (
            <div className="font-mono tabular-nums text-[10px] text-text-muted">
              {qty.toFixed(4)} {sym}
            </div>
          )}
        </div>
      )
    },
  }),
  helper.accessor('cycle_cost', {
    header: 'Cost',
    cell: i => {
      const v = i.getValue()
      if (!v || v === 0) return <span className="text-text-muted text-xs">—</span>
      return <span className="font-mono tabular-nums text-xs text-text-muted">${v.toFixed(4)}</span>
    },
  }),
  helper.accessor('entry_price', {
    header: 'Entry',
    cell: i => <span className="font-mono tabular-nums text-xs">{i.getValue().toLocaleString()}</span>,
  }),
  helper.accessor('stop_loss', {
    header: 'SL',
    cell: i => <span className="font-mono tabular-nums text-xs text-loss">{i.getValue().toLocaleString()}</span>,
  }),
  helper.accessor('take_profit', {
    header: 'TP',
    cell: i => <span className="font-mono tabular-nums text-xs text-profit">{i.getValue().toLocaleString()}</span>,
  }),
  helper.accessor('pnl', {
    header: 'P&L',
    cell: i => <PnlCell value={i.getValue()} />,
  }),
  helper.accessor('pnl_pct', {
    header: 'P&L %',
    cell: i => <PnlCell value={i.getValue()} />,
  }),
  helper.display({
    id: 'exit',
    header: 'Exit',
    cell: ({ row }) => <ExitBadge type={row.original.exit_type} reason={row.original.exit_reason} />,
  }),
  helper.display({
    id: 'duration',
    header: 'Duration',
    cell: ({ row }) => (
      <Duration
        entryTime={row.original.entry_time || row.original.timestamp}
        exitTime={row.original.exit_time}
      />
    ),
  }),
  helper.accessor('rr_ratio', {
    header: 'RR',
    cell: i => <span className="font-mono tabular-nums text-xs">{i.getValue().toFixed(1)}</span>,
  }),
  helper.accessor('atr_value', {
    header: 'ATR',
    cell: i => <span className="font-mono tabular-nums text-xs text-text-muted">{i.getValue()?.toFixed(2) ?? '—'}</span>,
  }),
  helper.accessor('agreement_level', {
    header: 'Agree',
    cell: i => <span className="font-mono text-xs text-text-secondary">{i.getValue()}</span>,
  }),
]

export default function TradeLogTable({
  trades, total, page, onPageChange, limit,
  filters, onFilterChange, expandedRow, onExpandRow,
}: Props) {
  const [sorting, setSorting] = useState<SortingState>([])

  const uniqueBotNames = useMemo(() => {
    const names = new Set(trades.map(t => t.bot_name).filter(n => n && n !== 'unknown'))
    return Array.from(names).sort()
  }, [trades])

  const table = useReactTable({
    data: trades,
    columns: COLUMNS,
    state: { sorting },
    onSortingChange: setSorting,
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
    manualPagination: true,
    rowCount: total,
  })

  const totalPages = Math.ceil(total / limit)

  return (
    <div className="space-y-4">
      {/* Filters */}
      <div className="flex flex-wrap gap-3 items-center justify-between">
        <div className="flex flex-wrap gap-2">
          <select
            value={filters.bot_name}
            onChange={e => onFilterChange({ bot_name: e.target.value })}
            className="bg-bg-elevated border border-border text-text-secondary text-xs rounded-md px-3 py-1.5 focus:outline-none focus:border-accent"
          >
            <option value="">All Bots</option>
            {uniqueBotNames.map(name => (
              <option key={name} value={name}>{name}</option>
            ))}
          </select>
          <select
            value={filters.direction}
            onChange={e => onFilterChange({ direction: e.target.value })}
            className="bg-bg-elevated border border-border text-text-secondary text-xs rounded-md px-3 py-1.5 focus:outline-none focus:border-accent"
          >
            <option value="">All Directions</option>
            <option value="LONG">LONG</option>
            <option value="SHORT">SHORT</option>
          </select>
          <select
            value={filters.exit_type}
            onChange={e => onFilterChange({ exit_type: e.target.value })}
            className="bg-bg-elevated border border-border text-text-secondary text-xs rounded-md px-3 py-1.5 focus:outline-none focus:border-accent"
          >
            <option value="">All Exits</option>
            <option value="tp">TP</option>
            <option value="sl">SL</option>
            <option value="time">Time</option>
          </select>
          <input
            type="text"
            placeholder="Filter symbol…"
            value={filters.symbol}
            onChange={e => onFilterChange({ symbol: e.target.value })}
            className="bg-bg-elevated border border-border text-text-secondary text-xs rounded-md px-3 py-1.5 focus:outline-none focus:border-accent w-36"
          />
        </div>
        <button
          onClick={() => exportCSV(trades)}
          className="px-3 py-1.5 text-xs bg-bg-elevated border border-border text-text-secondary hover:text-text-primary rounded-md transition-colors"
        >
          Export CSV
        </button>
      </div>

      {/* Table */}
      <div className="bg-bg-card border border-border rounded-lg overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              {table.getHeaderGroups().map(hg => (
                <tr key={hg.id} className="border-b border-border">
                  {hg.headers.map(header => (
                    <th
                      key={header.id}
                      className="px-4 py-3 text-left text-text-muted text-xs uppercase tracking-wider font-medium cursor-pointer select-none hover:text-text-secondary whitespace-nowrap"
                      onClick={header.column.getToggleSortingHandler()}
                    >
                      <span className="inline-flex items-center gap-1">
                        {flexRender(header.column.columnDef.header, header.getContext())}
                        {header.column.getIsSorted() === 'asc' ? (
                          <ChevronUp size={12} />
                        ) : header.column.getIsSorted() === 'desc' ? (
                          <ChevronDown size={12} />
                        ) : (
                          <ChevronsUpDown size={12} className="opacity-30" />
                        )}
                      </span>
                    </th>
                  ))}
                  <th className="px-4 py-3 text-left text-text-muted text-xs uppercase tracking-wider font-medium">Note</th>
                </tr>
              ))}
            </thead>
            <tbody>
              {table.getRowModel().rows.length === 0 ? (
                <tr>
                  <td colSpan={COLUMNS.length + 1} className="px-4 py-12 text-center text-text-muted text-sm">
                    No trades found
                  </td>
                </tr>
              ) : (
                table.getRowModel().rows.map((row, i) => {
                  const t = row.original
                  const rowBg = t.pnl > 0 ? 'bg-profit/5' : t.pnl < 0 ? 'bg-loss/5' : ''
                  const isExpanded = expandedRow === i
                  return (
                    <>
                      <tr
                        key={row.id}
                        className={`border-b border-border/50 hover:bg-bg-elevated/60 transition-colors ${rowBg}`}
                      >
                        {row.getVisibleCells().map(cell => (
                          <td key={cell.id} className="px-4 py-2.5">
                            {flexRender(cell.column.columnDef.cell, cell.getContext())}
                          </td>
                        ))}
                        <td className="px-4 py-2.5">
                          {t.estimated && (
                            <span className="text-yellow-500/70 text-xs italic">est.</span>
                          )}
                        </td>
                      </tr>
                      {/* Expandable justification row */}
                      <tr
                        key={`${row.id}-just`}
                        className={`border-b border-border/50 cursor-pointer ${rowBg}`}
                        onClick={() => onExpandRow(isExpanded ? null : i)}
                      >
                        <td colSpan={COLUMNS.length + 1} className="px-4 pb-2">
                          <p className={`text-text-muted text-xs leading-relaxed transition-all ${isExpanded ? '' : 'line-clamp-1'}`}>
                            <span className="text-text-secondary font-medium mr-1">Justification:</span>
                            {t.justification}
                          </p>
                        </td>
                      </tr>
                    </>
                  )
                })
              )}
            </tbody>
          </table>
        </div>
      </div>

      {/* Pagination */}
      {totalPages > 1 && (
        <div className="flex items-center justify-between text-xs text-text-muted">
          <span>{total} total trades</span>
          <div className="flex gap-2">
            <button
              disabled={page === 0}
              onClick={() => onPageChange(page - 1)}
              className="px-3 py-1.5 border border-border rounded-md hover:bg-bg-elevated disabled:opacity-40 transition-colors"
            >
              Prev
            </button>
            <span className="px-3 py-1.5">
              {page + 1} / {totalPages}
            </span>
            <button
              disabled={page >= totalPages - 1}
              onClick={() => onPageChange(page + 1)}
              className="px-3 py-1.5 border border-border rounded-md hover:bg-bg-elevated disabled:opacity-40 transition-colors"
            >
              Next
            </button>
          </div>
        </div>
      )}
    </div>
  )
}
