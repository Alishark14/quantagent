import { useState } from 'react'
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
  filters: { symbol: string; direction: string; exit_type: string }
  onFilterChange: (f: Partial<{ symbol: string; direction: string; exit_type: string }>) => void
  expandedRow: number | null
  onExpandRow: (i: number | null) => void
}

const helper = createColumnHelper<TradeRecord>()

function PnlCell({ value }: { value: number }) {
  return (
    <span className={`font-mono tabular-nums font-semibold ${value > 0 ? 'text-profit' : value < 0 ? 'text-loss' : 'text-text-muted'}`}>
      {value >= 0 ? '+' : ''}{value.toFixed(4)}
    </span>
  )
}

function ExitBadge({ type }: { type: string }) {
  const map: Record<string, string> = {
    tp: 'bg-profit/15 text-profit',
    sl: 'bg-loss/15 text-loss',
    time: 'bg-yellow-500/15 text-yellow-400',
    unknown: 'bg-bg-elevated text-text-muted',
  }
  return <span className={`px-1.5 py-0.5 rounded text-xs font-semibold uppercase ${map[type] ?? map.unknown}`}>{type}</span>
}

function exportCSV(trades: TradeRecord[]) {
  const headers = ['timestamp','symbol','direction','entry_price','stop_loss','take_profit','pnl','pnl_pct','exit_type','rr_ratio','atr_value','agreement_level']
  const rows = trades.map(t =>
    [t.timestamp, t.symbol, t.direction, t.entry_price, t.stop_loss, t.take_profit, t.pnl, t.pnl_pct, t.exit_type, t.rr_ratio, t.atr_value ?? '', t.agreement_level].join(',')
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
  helper.accessor('exit_type', {
    header: 'Exit',
    cell: i => <ExitBadge type={i.getValue()} />,
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
        <div className="flex gap-2">
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
