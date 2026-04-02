import { useEffect, useRef, useState } from 'react'
import { useParams, Link } from 'react-router-dom'
import { ArrowLeft, Edit2, Play, PauseCircle, Square, RefreshCw, Circle } from 'lucide-react'
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

type Tab = 'log' | 'trades' | 'perf'

// ── Log line color coding ─────────────────────────────────────────────────────

function logLineClass(line: string): string {
  if (/ERROR/.test(line)) return 'text-[#ef4444]'
  if (/WARNING|WARN/.test(line)) return 'text-[#eab308]'
  if (/SIGNAL:|Decision:|LONG|SHORT/.test(line)) return 'text-[#22c55e]'
  if (/[═─╔║╚╝╠╣]/.test(line)) return 'text-[#06b6d4]'
  return 'text-[#9ca3af]'
}

export default function BotDetail({ refreshTick }: Props) {
  const { id } = useParams<{ id: string }>()

  const [bot, setBot] = useState<Bot | null>(null)
  const [trades, setTrades] = useState<TradeRecord[]>([])
  const [agentData, setAgentData] = useState<AgentsData | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [actionLoading, setActionLoading] = useState(false)
  const [editOpen, setEditOpen] = useState(false)
  const [page, setPage] = useState(0)
  const [activeTab, setActiveTab] = useState<Tab>('log')
  const LIMIT = 50

  // ── Live log state ──────────────────────────────────────────────────────────
  const [logLines, setLogLines] = useState<string[]>([])
  const [wsConnected, setWsConnected] = useState(false)
  const [paused, setPaused] = useState(false)
  const logEndRef = useRef<HTMLDivElement>(null)
  const wsRef = useRef<WebSocket | null>(null)

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

  // ── WebSocket connection (only when log tab is active) ──────────────────────
  useEffect(() => {
    if (activeTab !== 'log' || !id) return

    const ws = new WebSocket(`ws://localhost:8001/ws/bots/${id}/logs`)
    wsRef.current = ws

    ws.onopen = () => setWsConnected(true)
    ws.onclose = () => setWsConnected(false)
    ws.onerror = () => setWsConnected(false)
    ws.onmessage = (ev) => {
      try {
        const msg = JSON.parse(ev.data)
        if (msg.type === 'log' && msg.data) {
          setLogLines(prev => [...prev, msg.data])
        }
      } catch {
        // ignore parse errors
      }
    }

    return () => {
      ws.close()
      wsRef.current = null
      setWsConnected(false)
    }
  }, [activeTab, id])

  // ── Auto-scroll log to bottom ───────────────────────────────────────────────
  useEffect(() => {
    if (!paused && logEndRef.current) {
      logEndRef.current.scrollIntoView({ behavior: 'smooth' })
    }
  }, [logLines, paused])

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

  const TABS: { key: Tab; label: string }[] = [
    { key: 'log', label: 'Live Log' },
    { key: 'trades', label: 'Trades' },
    { key: 'perf', label: 'Performance' },
  ]

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

      {/* Tabs */}
      <div className="flex gap-1 border-b border-border">
        {TABS.map(tab => (
          <button
            key={tab.key}
            onClick={() => setActiveTab(tab.key)}
            className={`px-4 py-2 text-sm font-medium transition-colors border-b-2 -mb-px ${
              activeTab === tab.key
                ? 'border-accent text-accent'
                : 'border-transparent text-text-muted hover:text-text-secondary'
            }`}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {/* Tab: Live Log */}
      {activeTab === 'log' && (
        <div className="space-y-3">
          {/* Log controls */}
          <div className="flex items-center gap-3 text-xs">
            <div className="flex items-center gap-1.5">
              <Circle
                size={8}
                className={wsConnected ? 'fill-[#22c55e] text-[#22c55e]' : 'fill-[#ef4444] text-[#ef4444]'}
              />
              <span className="text-text-muted">{wsConnected ? 'Connected' : 'Disconnected'}</span>
            </div>
            <button
              onClick={() => setLogLines([])}
              className="px-2 py-1 bg-bg-elevated border border-border rounded text-text-secondary hover:text-text-primary transition-colors"
            >
              Clear
            </button>
            <button
              onClick={() => setPaused(p => !p)}
              className={`px-2 py-1 border rounded transition-colors ${
                paused
                  ? 'bg-[#eab308]/15 border-[#eab308]/30 text-[#eab308]'
                  : 'bg-bg-elevated border-border text-text-secondary hover:text-text-primary'
              }`}
            >
              {paused ? 'Resume' : 'Pause'}
            </button>
            <span className="text-text-muted ml-auto">{logLines.length} lines</span>
          </div>

          {/* Terminal */}
          <div
            className="bg-[#0d1117] border border-[#2d3039] rounded-lg p-4 h-[500px] overflow-y-auto"
            style={{ fontFamily: "'JetBrains Mono', 'Fira Code', 'Cascadia Code', monospace" }}
          >
            {logLines.length === 0 ? (
              <p className="text-[#4b5563] text-xs">
                {wsConnected ? 'Waiting for log output…' : 'No log file found. Start the bot to begin streaming.'}
              </p>
            ) : (
              logLines.map((line, i) => (
                <div key={i} className={`text-xs leading-5 whitespace-pre-wrap break-all ${logLineClass(line)}`}>
                  {line}
                </div>
              ))
            )}
            <div ref={logEndRef} />
          </div>
        </div>
      )}

      {/* Tab: Trades */}
      {activeTab === 'trades' && (
        <div>
          <div className="flex items-center justify-between mb-3">
            <h2 className="text-text-primary font-semibold text-sm">
              Trade History
              <span className="text-text-muted font-normal ml-2 text-xs">{trades.length} records</span>
            </h2>
          </div>
          {trades.length === 0 ? (
            <p className="text-text-muted text-sm py-8 text-center">No trades yet for this bot</p>
          ) : (
            <TradeLogTable
              trades={trades}
              total={trades.length}
              page={page}
              onPageChange={setPage}
              limit={LIMIT}
              filters={{ symbol: '', direction: '', exit_type: '', bot_name: '' }}
              onFilterChange={() => {}}
              expandedRow={null}
              onExpandRow={() => {}}
            />
          )}
        </div>
      )}

      {/* Tab: Performance */}
      {activeTab === 'perf' && (
        <div className="space-y-6">
          {equityCurve.length > 0 ? (
            <div>
              <h2 className="text-text-primary font-semibold text-sm mb-3">Equity Curve</h2>
              <EquityCurve data={equityCurve} />
            </div>
          ) : (
            <p className="text-text-muted text-sm py-4">No trade data for equity curve.</p>
          )}

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
        </div>
      )}

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
