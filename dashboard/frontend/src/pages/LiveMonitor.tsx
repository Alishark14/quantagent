import { useCallback, useEffect, useRef, useState } from 'react'
import { Circle, ChevronDown, ChevronUp, Filter } from 'lucide-react'
import type { Bot } from '../types'
import { getWsUrl } from '../api/client'

// ── Event type ────────────────────────────────────────────────────────────────

interface BotEvent {
  type: string
  timestamp: string
  bot_id?: string
  bot_name?: string
  agent?: string
  emoji?: string
  signal?: string
  report_summary?: string
  tokens_in?: number
  tokens_out?: number
  direction?: string
  entry_price?: number
  stop_loss?: number
  take_profit?: number
  risk_reward?: number
  reasoning?: string
  agreement_score?: number
  position_size_usd?: number
  status?: string
  order_id?: string
  error?: string
  sl_order_id?: string
  tp_order_id?: string
  native?: boolean
  // trailing_sl_update
  old_sl?: number
  new_sl?: number
  peak_price?: number
  trail_distance?: number
  // pyramid_add
  size?: number
  pyramid_number?: number
  sl_adjustment?: string
  symbol?: string
  timeframe?: string
  total_cost?: number
  agents?: Record<string, number>
  reason?: string
  message?: string
  age_minutes?: number
  max_minutes?: number
  remaining_minutes?: number
  // attached by LiveMonitor
  _bot_name?: string
  _bot_symbol?: string
}

// ── Helpers ───────────────────────────────────────────────────────────────────

function formatTime(iso: string): string {
  try {
    return new Date(iso).toLocaleTimeString([], {
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
    })
  } catch {
    return ''
  }
}

function SignalBadge({ signal }: { signal: string }) {
  const upper = signal.toUpperCase()
  if (upper === 'BULLISH')
    return (
      <span className="px-1.5 py-0.5 rounded text-[10px] font-bold bg-[#22c55e]/20 text-[#22c55e]">
        BULLISH
      </span>
    )
  if (upper === 'BEARISH')
    return (
      <span className="px-1.5 py-0.5 rounded text-[10px] font-bold bg-[#ef4444]/20 text-[#ef4444]">
        BEARISH
      </span>
    )
  return (
    <span className="px-1.5 py-0.5 rounded text-[10px] font-bold bg-[#6b7280]/20 text-[#6b7280]">
      NEUTRAL
    </span>
  )
}

function ExpandableText({ text, maxLen = 200 }: { text: string; maxLen?: number }) {
  const [expanded, setExpanded] = useState(false)
  if (!text) return null
  const isLong = text.length > maxLen
  return (
    <div>
      <p className="text-[#9ca3af] text-xs leading-relaxed whitespace-pre-wrap break-words">
        {!expanded && isLong ? text.slice(0, maxLen) + '…' : text}
      </p>
      {isLong && (
        <button
          onClick={() => setExpanded(e => !e)}
          className="flex items-center gap-0.5 text-[10px] text-[#6b7280] hover:text-[#9ca3af] mt-1 transition-colors"
        >
          {expanded ? <><ChevronUp size={10} /> show less</> : <><ChevronDown size={10} /> show more</>}
        </button>
      )}
    </div>
  )
}

// ── Bot label badge ───────────────────────────────────────────────────────────

const BOT_COLORS = [
  'bg-blue-500/20 text-blue-400',
  'bg-purple-500/20 text-purple-400',
  'bg-cyan-500/20 text-cyan-400',
  'bg-orange-500/20 text-orange-400',
  'bg-pink-500/20 text-pink-400',
  'bg-teal-500/20 text-teal-400',
  'bg-indigo-500/20 text-indigo-400',
  'bg-amber-500/20 text-amber-400',
]

const _colorCache = new Map<string, string>()
function botColor(botId: string): string {
  if (!_colorCache.has(botId)) {
    let h = 0
    for (let i = 0; i < botId.length; i++) h = (h * 31 + botId.charCodeAt(i)) & 0xffffffff
    _colorCache.set(botId, BOT_COLORS[Math.abs(h) % BOT_COLORS.length])
  }
  return _colorCache.get(botId)!
}

function BotLabel({ event }: { event: BotEvent }) {
  if (!event.bot_id && !event._bot_name) return null
  const name = event._bot_name || event.bot_name || event.bot_id || ''
  const sym = event._bot_symbol
  const color = botColor(event.bot_id || name)
  return (
    <div className="flex items-center gap-1.5 mb-1.5">
      <span className={`px-1.5 py-0.5 rounded text-[10px] font-semibold ${color}`}>{name}</span>
      {sym && (
        <span className="text-[#4b5563] text-[10px] font-mono">{sym}</span>
      )}
    </div>
  )
}

// ── Event card variants ───────────────────────────────────────────────────────

function AgentResultCard({ event }: { event: BotEvent }) {
  const tokens = (event.tokens_in ?? 0) + (event.tokens_out ?? 0)
  return (
    <div className="bg-[#12151e] border border-[#2d3039] rounded-lg p-3 space-y-2">
      <BotLabel event={event} />
      <div className="flex items-center justify-between gap-2">
        <div className="flex items-center gap-1.5">
          <span className="text-sm">{event.emoji}</span>
          <span className="text-text-primary text-xs font-semibold">{event.agent}</span>
          {event.signal && <SignalBadge signal={event.signal} />}
        </div>
        <div className="flex items-center gap-2 shrink-0">
          {tokens > 0 && (
            <span className="text-[#4b5563] text-[10px] font-mono">
              {tokens.toLocaleString()} tok
            </span>
          )}
          <span className="text-[#4b5563] text-[10px]">{formatTime(event.timestamp)}</span>
        </div>
      </div>
      {event.report_summary && <ExpandableText text={event.report_summary} />}
    </div>
  )
}

function DecisionCard({ event }: { event: BotEvent }) {
  const [expanded, setExpanded] = useState(false)
  const isLong = (event.reasoning?.length ?? 0) > 200
  return (
    <div className="bg-[#12151e] border border-[#2d3039] rounded-lg p-3 space-y-2">
      <BotLabel event={event} />
      <div className="flex items-center justify-between gap-2">
        <div className="flex items-center gap-1.5">
          <span className="text-sm">🧠</span>
          <span className="text-text-primary text-xs font-semibold">DecisionAgent</span>
        </div>
        <span className="text-[#4b5563] text-[10px]">{formatTime(event.timestamp)}</span>
      </div>
      <div className="flex items-center gap-2">
        <span
          className={`text-base font-extrabold tracking-wide ${
            event.direction === 'LONG' ? 'text-[#22c55e]' : 'text-[#ef4444]'
          }`}
        >
          {event.direction}
        </span>
        {event.position_size_usd != null && event.position_size_usd > 0 && (
          <span className="text-text-secondary text-xs font-mono ml-auto">
            ${event.position_size_usd.toFixed(2)}
          </span>
        )}
      </div>
      {(event.entry_price || event.stop_loss || event.take_profit) && (
        <div className="flex gap-3 text-[10px]">
          <span className="text-text-muted">
            Entry <span className="text-text-primary font-mono">{event.entry_price?.toFixed(4)}</span>
          </span>
          <span className="text-text-muted">
            SL <span className="text-[#ef4444] font-mono">{event.stop_loss?.toFixed(4)}</span>
          </span>
          <span className="text-text-muted">
            TP <span className="text-[#22c55e] font-mono">{event.take_profit?.toFixed(4)}</span>
          </span>
          {event.risk_reward != null && event.risk_reward > 0 && (
            <span className="text-text-muted">
              RR <span className="text-text-secondary font-mono">{event.risk_reward.toFixed(2)}</span>
            </span>
          )}
        </div>
      )}
      {event.reasoning && (
        <div>
          <p className="text-[#9ca3af] text-xs leading-relaxed whitespace-pre-wrap break-words">
            {!expanded && isLong ? event.reasoning.slice(0, 200) + '…' : event.reasoning}
          </p>
          {isLong && (
            <button
              onClick={() => setExpanded(e => !e)}
              className="flex items-center gap-0.5 text-[10px] text-[#6b7280] hover:text-[#9ca3af] mt-1 transition-colors"
            >
              {expanded ? <><ChevronUp size={10} /> show less</> : <><ChevronDown size={10} /> show more</>}
            </button>
          )}
        </div>
      )}
    </div>
  )
}

function TradeExecutionCard({ event }: { event: BotEvent }) {
  const { status } = event
  let icon = '✅'; let color = 'text-[#22c55e]'; let label = 'Trade Executed'
  if (status === 'skipped') { icon = '⏭️'; color = 'text-[#6b7280]'; label = 'Trade Skipped' }
  if (status === 'failed') { icon = '❌'; color = 'text-[#ef4444]'; label = 'Trade Failed' }
  return (
    <div className="bg-[#12151e] border border-[#2d3039] rounded-lg px-3 py-2 space-y-1">
      <BotLabel event={event} />
      <div className="flex items-center gap-2">
        <span className="text-sm">{icon}</span>
        <span className={`text-xs font-semibold ${color}`}>{label}</span>
        {event.order_id && (
          <span className="text-[#4b5563] text-[10px] font-mono ml-1 truncate">
            {event.order_id.slice(0, 16)}
          </span>
        )}
        {event.error && (
          <span className="text-[#ef4444] text-[10px] ml-1 truncate">{event.error}</span>
        )}
        <span className="text-[#4b5563] text-[10px] ml-auto shrink-0">
          {formatTime(event.timestamp)}
        </span>
      </div>
    </div>
  )
}

function SlTpCard({ event }: { event: BotEvent }) {
  return (
    <div className="bg-[#12151e] border border-[#2d3039] rounded-lg px-3 py-2 space-y-1">
      <BotLabel event={event} />
      <div className="flex items-center gap-2">
        <span className="text-sm">🛡️</span>
        <span className="text-[#22c55e] text-xs font-semibold">SL/TP placed on exchange</span>
        {!event.native && <span className="text-[#4b5563] text-[10px]">(monitor)</span>}
        <span className="text-[#4b5563] text-[10px] ml-auto shrink-0">
          {formatTime(event.timestamp)}
        </span>
      </div>
    </div>
  )
}

function CycleStartCard({ event }: { event: BotEvent }) {
  return (
    <div className="flex items-center gap-2 px-1 py-0.5">
      <span className="text-sm">🔄</span>
      <div className="flex-1 min-w-0">
        <BotLabel event={event} />
        <span className="text-[#6b7280] text-xs">Cycle started</span>
        <span className="text-[#4b5563] text-[10px] font-mono ml-1">
          {event.symbol} · {event.timeframe}
        </span>
      </div>
      <span className="text-[#4b5563] text-[10px] ml-auto shrink-0">
        {formatTime(event.timestamp)}
      </span>
    </div>
  )
}

function CycleSkipCard({ event }: { event: BotEvent }) {
  const hasAge = event.age_minutes != null && event.max_minutes != null
  return (
    <div className="px-2 py-1.5 opacity-60 space-y-0.5">
      <div className="flex items-center gap-2">
        <span className="text-sm">⏭️</span>
        <div className="flex-1 min-w-0">
          <BotLabel event={event} />
          <span className="text-[#6b7280] text-xs font-medium">
            Waiting — position open on{' '}
            <span className="font-mono text-[#9ca3af]">{event.symbol}</span>
          </span>
        </div>
        <span className="text-[#4b5563] text-[10px] ml-auto shrink-0">
          {formatTime(event.timestamp)}
        </span>
      </div>
      {hasAge && (
        <div className="flex items-center gap-2 pl-6 text-[10px] text-[#4b5563]">
          <span>
            {event.age_minutes}m / {event.max_minutes}m elapsed
          </span>
          {event.remaining_minutes != null && event.remaining_minutes > 0 && (
            <span className="text-[#374151]">· {event.remaining_minutes}m remaining</span>
          )}
        </div>
      )}
    </div>
  )
}

function TimeExitCard({ event }: { event: BotEvent }) {
  return (
    <div className="bg-[#1c1400] border border-[#78350f]/40 rounded-lg px-3 py-2 space-y-1">
      <BotLabel event={event} />
      <div className="flex items-center gap-2">
        <span className="text-sm">⏰</span>
        <span className="text-[#f59e0b] text-xs font-semibold">Time Exit</span>
        <span className="text-[#78350f] text-[10px] ml-auto shrink-0">
          {formatTime(event.timestamp)}
        </span>
      </div>
      <div className="text-[#d97706] text-xs pl-6">
        Position aged out on{' '}
        <span className="font-mono text-[#fbbf24]">{event.symbol}</span>
        {event.age_minutes != null && event.max_minutes != null && (
          <span className="text-[#92400e]">
            {' '}
            ({event.age_minutes}m &gt; {event.max_minutes}m)
          </span>
        )}
      </div>
      <div className="text-[#78350f] text-[10px] pl-6">Force closing position.</div>
    </div>
  )
}

function CycleCostCard({ event }: { event: BotEvent }) {
  return (
    <div className="flex items-center gap-2 px-1 py-0.5">
      <span className="text-sm">💰</span>
      <div className="flex-1 min-w-0">
        <BotLabel event={event} />
        <span className="text-[#6b7280] text-xs">
          Cycle cost:{' '}
          <span className="font-mono text-text-muted">${event.total_cost?.toFixed(4)}</span>
        </span>
      </div>
      <span className="text-[#4b5563] text-[10px] ml-auto shrink-0">
        {formatTime(event.timestamp)}
      </span>
    </div>
  )
}

function TrailingSlUpdateCard({ event }: { event: BotEvent }) {
  return (
    <div className="bg-[#0d1a1a] border border-[#0e7490]/40 rounded-lg px-3 py-2 space-y-1">
      <BotLabel event={event} />
      <div className="flex items-center gap-2">
        <span className="text-sm">📈</span>
        <span className="text-[#22d3ee] text-xs font-semibold">Trailing SL Updated</span>
        <span className="text-[#164e63] text-[10px] ml-auto shrink-0">{formatTime(event.timestamp)}</span>
      </div>
      <div className="flex gap-3 text-[10px] pl-6">
        <span className="text-[#0e7490]">
          <span className="font-mono text-[#6b7280]">{event.old_sl?.toFixed(4)}</span>
          {' → '}
          <span className="font-mono text-[#22d3ee]">{event.new_sl?.toFixed(4)}</span>
        </span>
        {event.peak_price != null && (
          <span className="text-[#0e7490]">
            Peak <span className="font-mono text-[#67e8f9]">{event.peak_price.toFixed(4)}</span>
          </span>
        )}
        {event.symbol && (
          <span className="text-[#164e63] font-mono">{event.symbol}</span>
        )}
      </div>
    </div>
  )
}

function DecisionSkipCard({ event }: { event: BotEvent }) {
  return (
    <div className="px-2 py-1.5 opacity-70 space-y-0.5">
      <div className="flex items-center gap-2">
        <span className="text-sm">🚫</span>
        <div className="flex-1 min-w-0">
          <BotLabel event={event} />
          <span className="text-[#6b7280] text-xs font-medium">Agents skipped — no clear signal</span>
        </div>
        <span className="text-[#4b5563] text-[10px] ml-auto shrink-0">
          {formatTime(event.timestamp)}
        </span>
      </div>
      {event.reasoning && (
        <p className="text-[#4b5563] text-[10px] pl-6 break-words">{event.reasoning.slice(0, 150)}</p>
      )}
    </div>
  )
}

function PyramidAddCard({ event }: { event: BotEvent }) {
  const dir = (event.direction ?? '').replace('ADD_', '')
  return (
    <div className="bg-[#1a1400] border border-[#854d0e]/40 rounded-lg px-3 py-2 space-y-1">
      <BotLabel event={event} />
      <div className="flex items-center gap-2">
        <span className="text-sm">📊</span>
        <span className="text-[#fbbf24] text-xs font-semibold">
          Pyramid #{event.pyramid_number ?? '?'}
        </span>
        <span className="text-[#78350f] text-[10px] ml-auto shrink-0">{formatTime(event.timestamp)}</span>
      </div>
      <div className="flex gap-3 text-[10px] pl-6">
        <span className={`font-bold ${dir === 'LONG' ? 'text-[#22c55e]' : 'text-[#ef4444]'}`}>{dir}</span>
        {event.size != null && event.size > 0 && (
          <span className="text-[#d97706] font-mono">${event.size.toFixed(0)}</span>
        )}
        {event.symbol && <span className="text-[#78350f] font-mono">{event.symbol}</span>}
        {event.sl_adjustment && event.sl_adjustment !== 'maintain' && (
          <span className="text-[#92400e]">SL → {event.sl_adjustment.replace(/_/g, ' ')}</span>
        )}
      </div>
    </div>
  )
}

function EarlyCloseCard({ event }: { event: BotEvent }) {
  return (
    <div className="bg-[#1a0a0a] border border-[#991b1b]/40 rounded-lg px-3 py-2 space-y-1">
      <BotLabel event={event} />
      <div className="flex items-center gap-2">
        <span className="text-sm">🔴</span>
        <span className="text-[#f87171] text-xs font-semibold">Early Close</span>
        <span className="text-[#7f1d1d] text-[10px] ml-auto shrink-0">{formatTime(event.timestamp)}</span>
      </div>
      <div className="text-[#fca5a5] text-xs pl-6">
        Contrary signal{event.symbol ? ` — closing ${event.symbol}` : ''}
      </div>
      {event.message && (
        <p className="text-[#7f1d1d] text-[10px] pl-6 break-words">{event.message.slice(0, 150)}</p>
      )}
    </div>
  )
}

function HoldCard({ event }: { event: BotEvent }) {
  return (
    <div className="px-2 py-1.5 opacity-60 space-y-0.5">
      <div className="flex items-center gap-2">
        <span className="text-sm">✋</span>
        <div className="flex-1 min-w-0">
          <BotLabel event={event} />
          <span className="text-[#6b7280] text-xs font-medium">
            Hold — keeping <span className="font-mono text-[#9ca3af]">{event.symbol}</span> position
          </span>
        </div>
        <span className="text-[#4b5563] text-[10px] ml-auto shrink-0">{formatTime(event.timestamp)}</span>
      </div>
      {event.message && (
        <p className="text-[#4b5563] text-[10px] pl-6 break-words">{event.message.slice(0, 120)}</p>
      )}
    </div>
  )
}

function EventCard({ event }: { event: BotEvent }) {
  switch (event.type) {
    case 'agent_result': return <AgentResultCard event={event} />
    case 'decision': return <DecisionCard event={event} />
    case 'decision_skip': return <DecisionSkipCard event={event} />
    case 'pyramid_add': return <PyramidAddCard event={event} />
    case 'early_close': return <EarlyCloseCard event={event} />
    case 'hold': return <HoldCard event={event} />
    case 'trade_execution': return <TradeExecutionCard event={event} />
    case 'sl_tp_placed': return <SlTpCard event={event} />
    case 'trailing_sl_update': return <TrailingSlUpdateCard event={event} />
    case 'cycle_start': return <CycleStartCard event={event} />
    case 'cycle_skip': return <CycleSkipCard event={event} />
    case 'time_exit': return <TimeExitCard event={event} />
    case 'cycle_cost': return <CycleCostCard event={event} />
    default: return null
  }
}

// ── Main component ────────────────────────────────────────────────────────────

const MAX_EVENTS = 100

export default function LiveMonitor() {
  const [bots, setBots] = useState<Bot[]>([])
  const [events, setEvents] = useState<BotEvent[]>([])
  const [connectedBots, setConnectedBots] = useState<Set<string>>(new Set())
  const [filterBotId, setFilterBotId] = useState<string>('all')
  const [autoScroll, setAutoScroll] = useState(true)
  const bottomRef = useRef<HTMLDivElement>(null)
  const wsRefs = useRef<Map<string, WebSocket>>(new Map())

  // Fetch running bots on mount
  useEffect(() => {
    fetch('/api/bots')
      .then(r => r.json())
      .then((all: Bot[]) => {
        const running = all.filter(b => b.status === 'running')
        setBots(running)
      })
      .catch(() => {})
  }, [])

  // Connect to each running bot's WebSocket
  useEffect(() => {
    if (bots.length === 0) return

    const cleanup: (() => void)[] = []

    for (const bot of bots) {
      // Load cached events first
      fetch(`/api/bots/${bot.id}/events`)
        .then(r => r.json())
        .then((cached: BotEvent[]) => {
          if (!Array.isArray(cached) || cached.length === 0) return
          const tagged = cached.map(e => ({
            ...e,
            _bot_name: bot.name,
            _bot_symbol: bot.symbol,
          }))
          setEvents(prev => {
            const merged = [...tagged, ...prev]
              .sort((a, b) => b.timestamp.localeCompare(a.timestamp))
              .slice(0, MAX_EVENTS)
            return merged
          })
        })
        .catch(() => {})

      const seenTimestamps = new Set<string>()
      const ws = new WebSocket(getWsUrl(`/ws/bots/${bot.id}/events`))

      ws.onopen = () =>
        setConnectedBots(prev => new Set([...prev, bot.id]))
      ws.onclose = () =>
        setConnectedBots(prev => { const s = new Set(prev); s.delete(bot.id); return s })
      ws.onerror = () =>
        setConnectedBots(prev => { const s = new Set(prev); s.delete(bot.id); return s })

      ws.onmessage = ev => {
        try {
          const data: BotEvent = JSON.parse(ev.data)
          if (data.type === 'keepalive') return
          if (seenTimestamps.has(data.timestamp)) return
          seenTimestamps.add(data.timestamp)
          const tagged = { ...data, _bot_name: bot.name, _bot_symbol: bot.symbol }
          setEvents(prev =>
            [tagged, ...prev].slice(0, MAX_EVENTS)
          )
        } catch {
          // ignore
        }
      }

      const pingInterval = setInterval(() => {
        if (ws.readyState === WebSocket.OPEN) ws.send('ping')
      }, 20000)

      wsRefs.current.set(bot.id, ws)
      cleanup.push(() => {
        clearInterval(pingInterval)
        ws.close()
        wsRefs.current.delete(bot.id)
      })
    }

    return () => cleanup.forEach(fn => fn())
  }, [bots])

  // Auto-scroll to bottom when new events arrive
  useEffect(() => {
    if (autoScroll) {
      bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
    }
  }, [events, autoScroll])

  const clearEvents = useCallback(() => setEvents([]), [])

  const visibleEvents =
    filterBotId === 'all'
      ? events
      : events.filter(e => (e.bot_id || '') === filterBotId)

  const runningCount = bots.length
  const connectedCount = connectedBots.size

  return (
    <div className="flex flex-col h-full space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between gap-4 shrink-0">
        <div>
          <h1 className="text-text-primary text-lg font-semibold">Live Monitor</h1>
          <p className="text-text-muted text-xs mt-0.5">
            {runningCount === 0
              ? 'No bots running'
              : `${connectedCount}/${runningCount} bot${runningCount !== 1 ? 's' : ''} connected`}
          </p>
        </div>

        <div className="flex items-center gap-3">
          {/* Bot filter */}
          <div className="flex items-center gap-1.5">
            <Filter size={13} className="text-text-muted" />
            <select
              value={filterBotId}
              onChange={e => setFilterBotId(e.target.value)}
              className="bg-bg-card border border-border rounded px-2 py-1 text-xs text-text-primary focus:outline-none focus:border-accent"
            >
              <option value="all">All bots</option>
              {bots.map(b => (
                <option key={b.id} value={b.id}>{b.name}</option>
              ))}
            </select>
          </div>

          {/* Auto-scroll toggle */}
          <button
            onClick={() => setAutoScroll(a => !a)}
            className={`flex items-center gap-1.5 px-2 py-1 rounded text-xs transition-colors ${
              autoScroll
                ? 'bg-accent/15 text-accent'
                : 'bg-bg-card border border-border text-text-secondary hover:text-text-primary'
            }`}
          >
            Auto-scroll {autoScroll ? '⬇' : '—'}
          </button>

          {/* Clear */}
          {events.length > 0 && (
            <button
              onClick={clearEvents}
              className="px-2 py-1 rounded text-xs text-text-muted hover:text-text-primary bg-bg-card border border-border transition-colors"
            >
              Clear
            </button>
          )}
        </div>
      </div>

      {/* Connection status per bot */}
      {bots.length > 0 && (
        <div className="flex flex-wrap gap-2 shrink-0">
          {bots.map(bot => (
            <div key={bot.id} className="flex items-center gap-1.5 bg-bg-card border border-border rounded px-2 py-1">
              <Circle
                size={6}
                className={
                  connectedBots.has(bot.id)
                    ? 'fill-[#22c55e] text-[#22c55e]'
                    : 'fill-[#6b7280] text-[#6b7280]'
                }
              />
              <span className="text-[10px] text-text-secondary">{bot.name}</span>
              <span className="text-[10px] text-text-muted font-mono">{bot.symbol}</span>
            </div>
          ))}
        </div>
      )}

      {/* Event feed */}
      <div className="flex-1 bg-bg-card border border-border rounded-lg overflow-y-auto min-h-0">
        {bots.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-full gap-3 py-16">
            <div className="w-10 h-10 rounded-full border border-border flex items-center justify-center">
              <span className="text-lg">📡</span>
            </div>
            <p className="text-text-muted text-sm text-center">
              No bots are currently running.
              <br />
              Start a bot from the Bots page to see live events here.
            </p>
          </div>
        ) : visibleEvents.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-full gap-3 py-16">
            <div className="w-10 h-10 rounded-full border border-border flex items-center justify-center">
              <span className="text-lg">👁️</span>
            </div>
            <p className="text-text-muted text-sm text-center">
              Waiting for the next cycle…
              <br />
              Events will appear here in real-time.
            </p>
          </div>
        ) : (
          <div className="px-3 py-3 space-y-2">
            {visibleEvents.map((event, i) => (
              <EventCard key={`${event.bot_id}-${event.timestamp}-${i}`} event={event} />
            ))}
            <div ref={bottomRef} />
          </div>
        )}
      </div>

      {/* Footer */}
      <div className="shrink-0 flex items-center justify-between text-[11px] text-text-muted">
        <span>{visibleEvents.length} events{filterBotId !== 'all' ? ' (filtered)' : ''}</span>
        <span>Max {MAX_EVENTS} events retained</span>
      </div>
    </div>
  )
}
