import { useEffect, useState } from 'react'
import { useParams, useNavigate, Link } from 'react-router-dom'
import { ArrowLeft, Edit2, Play, PauseCircle, Square, RefreshCw } from 'lucide-react'
import { api } from '../api/client'
import type { AgentsData, Bot, TradeRecord } from '../types'
import EquityCurve from '../components/overview/EquityCurve'
import AgentAccuracy from '../components/agents/AgentAccuracy'
import TradeLogTable from '../components/trades/TradeLogTable'
import BotModal from '../components/bots/BotModal'

interface Props {
  refreshTick: number
}

const AGENT_NAMES: Record<string, string> = {
  indicator: 'Indicator',
  pattern: 'Pattern',
  trend: 'Trend',
}

const STATUS_COLOR: Record<string, string> = {
  running: 'text-[#22c55e]',
  paused: 'text-[#eab308]',
  stopped: 'text-[#6b7280]',
  error: 'text-[#ef4444]',
}

export default function BotDetail({ refreshTick }: Props) {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()

  const [bot, setBot] = useState<Bot | null>(null)
  const [trades, setTrades] = useState<TradeRecord[]>([])
  const [agentData, setAgentData] = useState<AgentsData | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [actionLoading, setActionLoading] = useState(false)
  const [editOpen, setEditOpen] = useState(false)
  const [page, setPage] = useState(0)
  const LIMIT = 50

  async function fetchAll() {
    if (!id) return
    try {
      const [b, tr, ag] = await Promise.all([
        api.getBot(id),
        api.trades({ limit: LIMIT, offset: page * LIMIT, botId: id }),
        api.agents(id),
      ])
      setBot(b)
      setTrades(tr.trades)
      setAgentData(ag)
      setError(null)
    } catch (e: any) {
      setError(e.message)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    setLoading(true)
    fetchAll()
  }, [refreshTick, id, page])

  // ── Actions ────────────────────────────────────────────────────────────────

  async function doAction(fn: () => Promise<Bot>) {
    setActionLoading(true)
    try {
      const updated = await fn()
      setBot(updated)
    } catch (e: any) {
      setError(e.message)
    } finally {
      setActionLoading(false)
    }
  }

  // ── Equity curve from trades ───────────────────────────────────────────────
  const equityCurve = trades
    .slice()
    .reverse()
    .reduce<{ timestamp: string; cumulative_pnl: number }[]>((acc, t) => {
      const prev = acc.length ? acc[acc.length - 1].cumulative_pnl : 0
      acc.push({ timestamp: t.timestamp, cumulative_pnl: prev + (t.pnl ?? 0) })
      return acc
    }, [])

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="text-text-muted text-sm animate-pulse">Loading bot…</div>
      </div>
    )
  }

  if (error || !bot) {
    return (
      <div className="space-y-4">
        <Link to="/bots" className="flex items-center gap-1 text-text-muted hover:text-text-primary text-sm">
          <ArrowLeft size={14} /> Back to Bots
        </Link>
        <div className="bg-[#ef4444]/10 border border-[#ef4444]/30 rounded-lg p-6 text-[#ef4444] text-sm">
          {error ?? 'Bot not found'}
        </div>
      </div>
    )
  }

  const canStart = bot.status === 'stopped' || bot.status === 'paused' || bot.status === 'error'
  const canPause = bot.status === 'running'
  const canStop = bot.status === 'running' || bot.status === 'paused'

  return (
    <div className="space-y-6">
      {/* Nav + header */}
      <div>
        <Link to="/bots" className="flex items-center gap-1 text-text-muted hover:text-text-primary text-xs mb-3 w-fit">
          <ArrowLeft size={13} /> All Bots
        </Link>
        <div className="flex items-start justify-between gap-4 flex-wrap">
          <div className="flex items-center gap-3">
            <div>
              <h1 className="text-text-primary text-xl font-bold">{bot.name}</h1>
              <div className="flex items-center gap-2 mt-1 flex-wrap text-xs">
                <span className="px-1.5 py-0.5 rounded bg-bg-elevated text-text-secondary font-medium">
                  {bot.symbol}
                </span>
                <span className={`font-medium ${STATUS_COLOR[bot.status] ?? 'text-text-muted'}`}>
                  {bot.status.charAt(0).toUpperCase() + bot.status.slice(1)}
                </span>
                {bot.pid && <span className="text-text-muted">PID {bot.pid}</span>}
              </div>
            </div>
          </div>

          {/* Action buttons */}
          <div className="flex items-center gap-2 flex-wrap">
            {canStart && (
              <button
                disabled={actionLoading}
                onClick={() => doAction(() => api.startBot(bot.id))}
                className="flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-medium bg-[#22c55e]/15 text-[#22c55e] hover:bg-[#22c55e]/25 transition-colors disabled:opacity-50"
              >
                <Play size={13} /> Start
              </button>
            )}
            {canPause && (
              <button
                disabled={actionLoading}
                onClick={() => doAction(() => api.pauseBot(bot.id))}
                className="flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-medium bg-[#eab308]/15 text-[#eab308] hover:bg-[#eab308]/25 transition-colors disabled:opacity-50"
              >
                <PauseCircle size={13} /> Pause
              </button>
            )}
            {canStop && (
              <button
                disabled={actionLoading}
                onClick={() => doAction(() => api.stopBot(bot.id))}
                className="flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-medium bg-[#ef4444]/15 text-[#ef4444] hover:bg-[#ef4444]/25 transition-colors disabled:opacity-50"
              >
                <Square size={13} /> Stop
              </button>
            )}
            <button
              disabled={actionLoading}
              onClick={() => doAction(() => api.restartBot(bot.id))}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-medium bg-bg-elevated text-text-secondary hover:text-text-primary transition-colors disabled:opacity-50"
            >
              <RefreshCw size={13} /> Restart
            </button>
            <button
              onClick={() => setEditOpen(true)}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-medium bg-bg-elevated text-text-secondary hover:text-text-primary transition-colors"
            >
              <Edit2 size={13} /> Edit
            </button>
          </div>
        </div>
      </div>

      {/* Error banner */}
      {error && (
        <div className="bg-[#ef4444]/10 border border-[#ef4444]/30 rounded-lg px-4 py-3 text-[#ef4444] text-sm">
          {error}
          <button onClick={() => setError(null)} className="ml-3 text-xs underline">Dismiss</button>
        </div>
      )}

      {/* Config panel */}
      <div className="bg-[#1a1d26] border border-[#2d3039] rounded-xl p-5">
        <h2 className="text-text-primary font-semibold text-sm mb-4">Configuration</h2>
        <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-x-6 gap-y-3 text-xs">
          <ConfigItem label="Timeframe" value={bot.timeframe} />
          <ConfigItem label="Market type" value={bot.market_type} />
          <ConfigItem label="Mode" value={bot.trading_mode} />
          <ConfigItem label="Exchange" value={`${bot.exchange}${bot.exchange_testnet ? ' (testnet)' : ''}`} />
          <ConfigItem label="Budget" value={`$${bot.budget_usd.toLocaleString()}`} />
          <ConfigItem label="Max positions" value={String(bot.max_concurrent_positions)} />
          <ConfigItem label="ATR multiplier" value={String(bot.atr_multiplier)} />
          <ConfigItem label="ATR length" value={String(bot.atr_length)} />
          <ConfigItem label="RR ratio" value={`${bot.rr_ratio_min} – ${bot.rr_ratio_max}`} />
          <ConfigItem label="Max daily loss" value={`$${bot.max_daily_loss_usd}`} />
          <ConfigItem label="Max pos %" value={`${(bot.max_position_pct * 100).toFixed(0)}%`} />
          <ConfigItem label="Forecast candles" value={String(bot.forecast_candles)} />
          <ConfigItem label="Agents" value={bot.agents_enabled} />
          <ConfigItem label="LLM" value={bot.llm_model.split('-').slice(1, 3).join('-')} />
          <ConfigItem label="Daily P&L" value={`-$${bot.daily_loss_usd.toFixed(2)}`} />
          <ConfigItem
            label="Last heartbeat"
            value={bot.last_heartbeat ? new Date(bot.last_heartbeat).toLocaleTimeString() : 'never'}
          />
        </div>
        {bot.last_error && (
          <p className="mt-3 text-[#ef4444] text-xs bg-[#ef4444]/10 rounded px-3 py-2">
            Last error: {bot.last_error}
          </p>
        )}
      </div>

      {/* Equity curve */}
      {equityCurve.length > 0 && (
        <div>
          <h2 className="text-text-primary font-semibold text-sm mb-3">Equity Curve</h2>
          <EquityCurve data={equityCurve} />
        </div>
      )}

      {/* Agent accuracy */}
      {agentData && Object.keys(agentData.agents).length > 0 && (
        <div>
          <h2 className="text-text-primary font-semibold text-sm mb-3">Agent Performance</h2>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            {Object.entries(agentData.agents).map(([key, stat]) => (
              <AgentAccuracy key={key} name={AGENT_NAMES[key] ?? key} stat={stat} />
            ))}
          </div>
        </div>
      )}

      {/* Trade log */}
      <div>
        <h2 className="text-text-primary font-semibold text-sm mb-3">
          Trade History
          <span className="text-text-muted font-normal ml-2 text-xs">{trades.length} records</span>
        </h2>
        {trades.length === 0 ? (
          <p className="text-text-muted text-sm py-8 text-center">No trades yet for this bot</p>
        ) : (
          <TradeLogTable
            trades={trades}
            total={trades.length}
            page={page}
            onPageChange={setPage}
            limit={LIMIT}
            filters={{ symbol: '', direction: '', exit_type: '' }}
            onFilterChange={() => {}}
            expandedRow={null}
            onExpandRow={() => {}}
          />
        )}
      </div>

      {/* Edit modal */}
      {editOpen && (
        <BotModal
          bot={bot}
          onClose={() => setEditOpen(false)}
          onSaved={saved => { setBot(saved); setEditOpen(false) }}
        />
      )}
    </div>
  )
}

function ConfigItem({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <span className="text-text-muted block">{label}</span>
      <span className="text-text-primary font-medium">{value}</span>
    </div>
  )
}
