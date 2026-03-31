import {
  Edit2,
  PauseCircle,
  Play,
  Square,
  Trash2,
} from 'lucide-react'
import type { Bot } from '../../types'

interface Props {
  bot: Bot
  onStart: () => void
  onStop: () => void
  onPause: () => void
  onEdit: () => void
  onDelete: () => void
  actionLoading?: boolean
}

const STATUS_DOT: Record<Bot['status'], string> = {
  running: 'bg-[#22c55e]',
  paused: 'bg-[#eab308]',
  stopped: 'bg-[#6b7280]',
  error: 'bg-[#ef4444]',
}

const STATUS_LABEL: Record<Bot['status'], string> = {
  running: 'Running',
  paused: 'Paused',
  stopped: 'Stopped',
  error: 'Error',
}

const STATUS_TEXT: Record<Bot['status'], string> = {
  running: 'text-[#22c55e]',
  paused: 'text-[#eab308]',
  stopped: 'text-[#6b7280]',
  error: 'text-[#ef4444]',
}

function leftBorderClass(status: Bot['status']): string {
  if (status === 'running') return 'border-l-[#22c55e]'
  if (status === 'error') return 'border-l-[#ef4444]'
  return 'border-l-[#2d3039]'
}

function heartbeatLabel(ts: string | null): string {
  if (!ts) return 'never'
  try {
    const diff = Date.now() - new Date(ts).getTime()
    if (diff < 60_000) return `${Math.round(diff / 1000)}s ago`
    if (diff < 3_600_000) return `${Math.round(diff / 60_000)}m ago`
    if (diff < 86_400_000) return `${Math.round(diff / 3_600_000)}h ago`
    return `${Math.round(diff / 86_400_000)}d ago`
  } catch {
    return 'unknown'
  }
}

// Simple sparkline from last 10 trades (just colored dots for now)
function Sparkline({ pnl }: { pnl: number[] }) {
  if (!pnl.length) return null
  return (
    <div className="flex items-end gap-0.5 h-5">
      {pnl.slice(-10).map((v, i) => (
        <div
          key={i}
          className={`w-1.5 rounded-sm ${v >= 0 ? 'bg-[#22c55e]' : 'bg-[#ef4444]'}`}
          style={{ height: `${Math.min(100, Math.max(20, Math.abs(v) * 5 + 20))}%` }}
        />
      ))}
    </div>
  )
}

export default function BotCard({
  bot,
  onStart,
  onStop,
  onPause,
  onEdit,
  onDelete,
  actionLoading = false,
}: Props) {
  const canStart = bot.status === 'stopped' || bot.status === 'paused' || bot.status === 'error'
  const canPause = bot.status === 'running'
  const canStop = bot.status === 'running' || bot.status === 'paused'

  const pnlColor = bot.daily_loss_usd > 0 ? 'text-[#ef4444]' : 'text-[#22c55e]'

  function handleDelete() {
    if (window.confirm(`Delete bot "${bot.name}"? This cannot be undone.`)) {
      onDelete()
    }
  }

  return (
    <div
      className={`
        relative flex flex-col rounded-xl border border-l-4 border-[#2d3039]
        ${leftBorderClass(bot.status)}
        bg-[#1a1d26] p-4 gap-3 transition-all duration-150
        hover:border-[#3d4050] hover:brightness-110
      `}
    >
      {/* Status dot */}
      <span
        className={`absolute top-3 right-3 w-2 h-2 rounded-full ${STATUS_DOT[bot.status]}`}
        title={STATUS_LABEL[bot.status]}
      />

      {/* Header */}
      <div className="pr-5">
        <div className="flex items-center gap-2 flex-wrap">
          <span className="text-text-primary font-bold text-base leading-tight">{bot.name}</span>
          <span className="px-1.5 py-0.5 rounded text-[10px] font-semibold tracking-wide bg-[#252830] text-text-secondary">
            {bot.symbol}
          </span>
        </div>
        <span className={`text-xs font-medium mt-0.5 block ${STATUS_TEXT[bot.status]}`}>
          {STATUS_LABEL[bot.status]}
          {bot.pid && bot.status === 'running' && (
            <span className="text-text-muted ml-1.5">PID {bot.pid}</span>
          )}
        </span>
      </div>

      {/* Badges row */}
      <div className="flex items-center gap-1.5 flex-wrap text-[10px] font-semibold">
        <span className="px-1.5 py-0.5 rounded bg-[#252830] text-text-secondary uppercase tracking-wide">
          {bot.timeframe}
        </span>
        {bot.trading_mode === 'paper' ? (
          <span className="px-1.5 py-0.5 rounded bg-[#3b82f6]/20 text-[#3b82f6]">PAPER</span>
        ) : (
          <span className="px-1.5 py-0.5 rounded bg-[#f97316]/20 text-[#f97316] animate-pulse">
            LIVE
          </span>
        )}
        {bot.market_type === 'perpetual' ? (
          <span className="px-1.5 py-0.5 rounded bg-[#8b5cf6]/20 text-[#8b5cf6]">PERP</span>
        ) : (
          <span className="px-1.5 py-0.5 rounded bg-[#06b6d4]/20 text-[#06b6d4]">SPOT</span>
        )}
        <span className="px-1.5 py-0.5 rounded bg-[#252830] text-text-muted">{bot.exchange}</span>
      </div>

      {/* Stats */}
      <div className="grid grid-cols-2 gap-x-4 gap-y-1 text-xs">
        <div>
          <span className="text-text-muted">Budget</span>
          <span className="text-text-primary ml-1.5 font-medium">${bot.budget_usd.toLocaleString()}</span>
        </div>
        <div>
          <span className="text-text-muted">Daily P&L</span>
          <span className={`ml-1.5 font-medium ${pnlColor}`}>
            {bot.daily_loss_usd > 0 ? `-$${bot.daily_loss_usd.toFixed(2)}` : '$0.00'}
          </span>
        </div>
        <div className="col-span-2">
          <span className="text-text-muted">Heartbeat</span>
          <span className="text-text-secondary ml-1.5">{heartbeatLabel(bot.last_heartbeat)}</span>
        </div>
      </div>

      {/* Error */}
      {bot.status === 'error' && bot.last_error && (
        <p className="text-[#ef4444] text-xs leading-tight bg-[#ef4444]/10 rounded px-2 py-1.5 break-words">
          {bot.last_error}
        </p>
      )}

      {/* Sparkline placeholder */}
      <Sparkline pnl={[]} />

      {/* Actions */}
      <div className="flex items-center gap-1.5 pt-1 border-t border-[#2d3039]">
        {canStart && (
          <button
            onClick={onStart}
            disabled={actionLoading}
            className="flex items-center gap-1 px-2 py-1 rounded text-xs font-medium bg-[#22c55e]/15 text-[#22c55e] hover:bg-[#22c55e]/25 transition-colors disabled:opacity-50"
          >
            <Play size={12} />
            Start
          </button>
        )}
        {canPause && (
          <button
            onClick={onPause}
            disabled={actionLoading}
            className="flex items-center gap-1 px-2 py-1 rounded text-xs font-medium bg-[#eab308]/15 text-[#eab308] hover:bg-[#eab308]/25 transition-colors disabled:opacity-50"
          >
            <PauseCircle size={12} />
            Pause
          </button>
        )}
        {canStop && (
          <button
            onClick={onStop}
            disabled={actionLoading}
            className="flex items-center gap-1 px-2 py-1 rounded text-xs font-medium bg-[#ef4444]/15 text-[#ef4444] hover:bg-[#ef4444]/25 transition-colors disabled:opacity-50"
          >
            <Square size={12} />
            Stop
          </button>
        )}
        <div className="flex-1" />
        <button
          onClick={onEdit}
          className="p-1.5 rounded text-text-muted hover:text-text-primary hover:bg-bg-elevated transition-colors"
          title="Edit"
        >
          <Edit2 size={13} />
        </button>
        {bot.status === 'stopped' && (
          <button
            onClick={handleDelete}
            className="p-1.5 rounded text-text-muted hover:text-[#ef4444] hover:bg-[#ef4444]/10 transition-colors"
            title="Delete"
          >
            <Trash2 size={13} />
          </button>
        )}
      </div>
    </div>
  )
}
