import type { TradeRecord } from '../../types'

interface Props {
  trades: TradeRecord[]
}

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
    <span className={`px-1.5 py-0.5 rounded text-xs font-medium truncate max-w-[80px] inline-block ${botColor(name)}`}>
      {name}
    </span>
  )
}

function DirectionBadge({ direction }: { direction: string }) {
  return (
    <span
      className={`px-2 py-0.5 rounded text-xs font-semibold ${
        direction === 'LONG' ? 'bg-profit/15 text-profit' : 'bg-loss/15 text-loss'
      }`}
    >
      {direction}
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
  return (
    <span className={`px-2 py-0.5 rounded text-xs font-semibold uppercase ${map[type] ?? map.unknown}`}>
      {type}
    </span>
  )
}

export default function RecentTrades({ trades }: Props) {
  if (trades.length === 0) {
    return (
      <div className="bg-bg-card border border-border rounded-lg p-6">
        <h2 className="text-text-primary text-sm font-semibold mb-3">Recent Trades</h2>
        <p className="text-text-muted text-sm">No executed trades yet</p>
      </div>
    )
  }

  return (
    <div className="bg-bg-card border border-border rounded-lg p-5">
      <h2 className="text-text-primary text-sm font-semibold mb-4">
        Recent Trades
        <span className="ml-2 text-text-muted text-xs font-normal">(P&amp;L from exchange)</span>
      </h2>
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="text-text-muted text-xs uppercase border-b border-border">
              <th className="pb-2 text-left font-medium pr-4">Bot</th>
              <th className="pb-2 text-left font-medium pr-4">Time</th>
              <th className="pb-2 text-left font-medium pr-4">Symbol</th>
              <th className="pb-2 text-left font-medium pr-4">Dir</th>
              <th className="pb-2 text-right font-medium pr-4">Entry</th>
              <th className="pb-2 text-right font-medium pr-4">P&amp;L</th>
              <th className="pb-2 text-left font-medium">Exit</th>
            </tr>
          </thead>
          <tbody>
            {trades.slice(0, 10).map((t, i) => {
              const pnlColor = t.pnl > 0 ? 'text-profit' : t.pnl < 0 ? 'text-loss' : 'text-text-secondary'
              return (
                <tr key={i} className="border-b border-border/50 hover:bg-bg-elevated/50 transition-colors">
                  <td className="py-2.5 pr-4">
                    <BotBadge name={t.bot_name} />
                  </td>
                  <td className="py-2.5 pr-4 text-text-muted text-xs font-mono tabular-nums whitespace-nowrap">
                    {new Date(t.timestamp).toLocaleString('en-US', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })}
                  </td>
                  <td className="py-2.5 pr-4 text-text-secondary text-xs font-mono">{t.symbol.replace('/USD:BTC', '').replace('/USD:ETH', '')}</td>
                  <td className="py-2.5 pr-4"><DirectionBadge direction={t.direction} /></td>
                  <td className="py-2.5 pr-4 text-right font-mono tabular-nums text-text-primary text-xs">{t.entry_price.toLocaleString()}</td>
                  <td className={`py-2.5 pr-4 text-right font-mono tabular-nums text-xs font-semibold ${pnlColor}`}>
                    {t.pnl >= 0 ? '+' : ''}{t.pnl.toFixed(2)}
                  </td>
                  <td className="py-2.5"><ExitBadge type={t.exit_type} /></td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
    </div>
  )
}
