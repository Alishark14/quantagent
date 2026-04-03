import { useEffect, useRef, useState } from 'react'
import { ArrowRight, ChevronDown, ChevronUp, Circle, X } from 'lucide-react'
import { useNavigate } from 'react-router-dom'

interface BotEvent {
  type: string
  timestamp: string
  bot_id?: string
  bot_name?: string
  // agent_result
  agent?: string
  emoji?: string
  signal?: string
  report_summary?: string
  tokens_in?: number
  tokens_out?: number
  // decision
  direction?: string
  entry_price?: number
  stop_loss?: number
  take_profit?: number
  risk_reward?: number
  reasoning?: string
  agreement_score?: number
  position_size_usd?: number
  // trade_execution
  status?: string
  order_id?: string
  error?: string
  // sl_tp_placed
  sl_order_id?: string
  tp_order_id?: string
  native?: boolean
  // cycle_start
  symbol?: string
  timeframe?: string
  // cycle_cost
  total_cost?: number
  agents?: Record<string, number>
  // cycle_skip
  reason?: string
  message?: string
}

interface Props {
  botId: string
  botName?: string
  botSymbol?: string
  onClose: () => void
  onViewDetails: () => void
}

function formatTime(iso: string): string {
  try {
    return new Date(iso).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })
  } catch {
    return ''
  }
}

function SignalBadge({ signal }: { signal: string }) {
  const upper = signal.toUpperCase()
  if (upper === 'BULLISH') return (
    <span className="px-1.5 py-0.5 rounded text-[10px] font-bold bg-[#22c55e]/20 text-[#22c55e]">BULLISH</span>
  )
  if (upper === 'BEARISH') return (
    <span className="px-1.5 py-0.5 rounded text-[10px] font-bold bg-[#ef4444]/20 text-[#ef4444]">BEARISH</span>
  )
  return (
    <span className="px-1.5 py-0.5 rounded text-[10px] font-bold bg-[#6b7280]/20 text-[#6b7280]">NEUTRAL</span>
  )
}

function ExpandableText({ text, maxLines = 3 }: { text: string; maxLines?: number }) {
  const [expanded, setExpanded] = useState(false)
  if (!text) return null
  const lines = text.split('\n')
  const isLong = lines.length > maxLines || text.length > 200
  const display = !expanded && isLong ? text.slice(0, 200) + '…' : text
  return (
    <div>
      <p className="text-[#9ca3af] text-xs leading-relaxed whitespace-pre-wrap break-words">{display}</p>
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

function AgentResultCard({ event }: { event: BotEvent }) {
  const tokens = (event.tokens_in ?? 0) + (event.tokens_out ?? 0)
  return (
    <div className="bg-[#12151e] border border-[#2d3039] rounded-lg p-3 space-y-2">
      <div className="flex items-center justify-between gap-2">
        <div className="flex items-center gap-1.5">
          <span className="text-sm">{event.emoji}</span>
          <span className="text-text-primary text-xs font-semibold">{event.agent}</span>
          {event.signal && <SignalBadge signal={event.signal} />}
        </div>
        <div className="flex items-center gap-2 shrink-0">
          {tokens > 0 && (
            <span className="text-[#4b5563] text-[10px] font-mono">{tokens.toLocaleString()} tok</span>
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
  const isLong = event.reasoning ? event.reasoning.length > 200 : false
  const isLong_ = isLong && !expanded

  return (
    <div className="bg-[#12151e] border border-[#2d3039] rounded-lg p-3 space-y-2">
      <div className="flex items-center justify-between gap-2">
        <div className="flex items-center gap-1.5">
          <span className="text-sm">🧠</span>
          <span className="text-text-primary text-xs font-semibold">DecisionAgent</span>
        </div>
        <span className="text-[#4b5563] text-[10px]">{formatTime(event.timestamp)}</span>
      </div>

      {/* Direction + size */}
      <div className="flex items-center gap-2">
        <span className={`text-base font-extrabold tracking-wide ${
          event.direction === 'LONG' ? 'text-[#22c55e]' : 'text-[#ef4444]'
        }`}>
          {event.direction}
        </span>
        {event.position_size_usd != null && event.position_size_usd > 0 && (
          <span className="text-text-secondary text-xs font-mono ml-auto">
            ${event.position_size_usd.toFixed(2)}
          </span>
        )}
      </div>

      {/* Entry / SL / TP */}
      {(event.entry_price || event.stop_loss || event.take_profit) && (
        <div className="flex gap-3 text-[10px]">
          <span className="text-text-muted">Entry <span className="text-text-primary font-mono">{event.entry_price?.toFixed(4)}</span></span>
          <span className="text-text-muted">SL <span className="text-[#ef4444] font-mono">{event.stop_loss?.toFixed(4)}</span></span>
          <span className="text-text-muted">TP <span className="text-[#22c55e] font-mono">{event.take_profit?.toFixed(4)}</span></span>
          {event.risk_reward != null && event.risk_reward > 0 && (
            <span className="text-text-muted">RR <span className="text-text-secondary font-mono">{event.risk_reward.toFixed(2)}</span></span>
          )}
        </div>
      )}

      {/* Reasoning */}
      {event.reasoning && (
        <div>
          <p className="text-[#9ca3af] text-xs leading-relaxed whitespace-pre-wrap break-words">
            {isLong_ ? event.reasoning.slice(0, 200) + '…' : event.reasoning}
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
  let icon = '✅'
  let color = 'text-[#22c55e]'
  let label = 'Trade Executed'
  if (status === 'skipped') { icon = '⏭️'; color = 'text-[#6b7280]'; label = 'Trade Skipped' }
  if (status === 'failed') { icon = '❌'; color = 'text-[#ef4444]'; label = 'Trade Failed' }

  return (
    <div className="bg-[#12151e] border border-[#2d3039] rounded-lg px-3 py-2 flex items-center gap-2">
      <span className="text-sm">{icon}</span>
      <span className={`text-xs font-semibold ${color}`}>{label}</span>
      {event.order_id && (
        <span className="text-[#4b5563] text-[10px] font-mono ml-1 truncate">{event.order_id.slice(0, 16)}</span>
      )}
      {event.error && (
        <span className="text-[#ef4444] text-[10px] ml-1 truncate">{event.error}</span>
      )}
      <span className="text-[#4b5563] text-[10px] ml-auto shrink-0">{formatTime(event.timestamp)}</span>
    </div>
  )
}

function SlTpCard({ event }: { event: BotEvent }) {
  return (
    <div className="bg-[#12151e] border border-[#2d3039] rounded-lg px-3 py-2 flex items-center gap-2">
      <span className="text-sm">🛡️</span>
      <span className="text-[#22c55e] text-xs font-semibold">SL/TP placed on exchange</span>
      {!event.native && <span className="text-[#4b5563] text-[10px]">(monitor)</span>}
      <span className="text-[#4b5563] text-[10px] ml-auto shrink-0">{formatTime(event.timestamp)}</span>
    </div>
  )
}

function CycleStartCard({ event }: { event: BotEvent }) {
  return (
    <div className="flex items-center gap-2 px-1 py-0.5">
      <span className="text-sm">🔄</span>
      <span className="text-[#6b7280] text-xs">Cycle started</span>
      <span className="text-[#4b5563] text-[10px] font-mono">{event.symbol} · {event.timeframe}</span>
      <span className="text-[#4b5563] text-[10px] ml-auto shrink-0">{formatTime(event.timestamp)}</span>
    </div>
  )
}

function CycleSkipCard({ event }: { event: BotEvent }) {
  return (
    <div className="flex items-center gap-2 px-1 py-0.5 opacity-60">
      <span className="text-sm">⏭️</span>
      <span className="text-[#6b7280] text-xs">
        Cycle skipped — position open on{' '}
        <span className="font-mono text-[#9ca3af]">{event.symbol}</span>
      </span>
      <span className="text-[#4b5563] text-[10px] ml-auto shrink-0">{formatTime(event.timestamp)}</span>
    </div>
  )
}

function CycleCostCard({ event }: { event: BotEvent }) {
  return (
    <div className="flex items-center gap-2 px-1 py-0.5">
      <span className="text-sm">💰</span>
      <span className="text-[#6b7280] text-xs">
        Cycle cost: <span className="font-mono text-text-muted">${event.total_cost?.toFixed(4)}</span>
      </span>
      <span className="text-[#4b5563] text-[10px] ml-auto shrink-0">{formatTime(event.timestamp)}</span>
    </div>
  )
}

function EventCard({ event }: { event: BotEvent }) {
  switch (event.type) {
    case 'agent_result': return <AgentResultCard event={event} />
    case 'decision': return <DecisionCard event={event} />
    case 'trade_execution': return <TradeExecutionCard event={event} />
    case 'sl_tp_placed': return <SlTpCard event={event} />
    case 'cycle_start': return <CycleStartCard event={event} />
    case 'cycle_skip': return <CycleSkipCard event={event} />
    case 'cycle_cost': return <CycleCostCard event={event} />
    default: return null
  }
}

export default function BotPeekDrawer({ botId, botName, botSymbol, onClose, onViewDetails }: Props) {
  const [events, setEvents] = useState<BotEvent[]>([])
  const [connected, setConnected] = useState(false)
  const topRef = useRef<HTMLDivElement>(null)
  const navigate = useNavigate()

  // Close on Escape
  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (e.key === 'Escape') onClose()
    }
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [onClose])

  // Fetch cached events immediately on mount, then connect WebSocket for live updates
  useEffect(() => {
    let cancelled = false

    // Track timestamps already shown to deduplicate WebSocket replay
    const seenTimestamps = new Set<string>()

    // Fetch cached events via REST as a quick first-paint fallback
    fetch(`/api/bots/${botId}/events`)
      .then(r => r.json())
      .then((cached: BotEvent[]) => {
        if (cancelled || !Array.isArray(cached) || cached.length === 0) return
        // Cache comes oldest-first; display newest-first
        const ordered = [...cached].reverse()
        ordered.forEach(e => seenTimestamps.add(e.timestamp))
        setEvents(ordered)
      })
      .catch(() => {})

    const ws = new WebSocket(`ws://localhost:8001/ws/bots/${botId}/events`)

    ws.onopen = () => setConnected(true)
    ws.onclose = () => setConnected(false)
    ws.onerror = () => setConnected(false)
    ws.onmessage = (ev) => {
      try {
        const data: BotEvent = JSON.parse(ev.data)
        if (data.type === 'keepalive') return
        // Deduplicate: skip events already loaded from the REST cache
        if (seenTimestamps.has(data.timestamp)) return
        seenTimestamps.add(data.timestamp)
        setEvents(prev => [data, ...prev])
        topRef.current?.scrollIntoView({ behavior: 'smooth' })
      } catch {
        // ignore
      }
    }

    const interval = setInterval(() => {
      if (ws.readyState === WebSocket.OPEN) {
        ws.send('ping')
      }
    }, 20000)

    return () => {
      cancelled = true
      clearInterval(interval)
      ws.close()
    }
  }, [botId])

  return (
    <>
      {/* Backdrop */}
      <div
        className="fixed inset-0 z-40 bg-black/50 backdrop-blur-sm"
        onClick={onClose}
      />

      {/* Drawer */}
      <div
        className="fixed right-0 top-0 bottom-0 z-50 flex flex-col bg-[#13161f] border-l border-[#2d3039] shadow-2xl"
        style={{ width: 'min(450px, 100vw)' }}
      >
        {/* Header */}
        <div className="flex items-center gap-3 px-4 py-3 border-b border-[#2d3039] shrink-0">
          <button
            onClick={onClose}
            className="p-1 rounded text-text-muted hover:text-text-primary hover:bg-bg-elevated transition-colors"
            title="Close"
          >
            <X size={15} />
          </button>

          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2">
              <span className="text-text-primary font-semibold text-sm truncate">
                {botName ?? botId}
              </span>
              {botSymbol && (
                <span className="px-1.5 py-0.5 rounded text-[10px] font-semibold bg-[#252830] text-text-secondary shrink-0">
                  {botSymbol}
                </span>
              )}
            </div>
            <div className="flex items-center gap-1.5 mt-0.5">
              <Circle
                size={6}
                className={connected ? 'fill-[#22c55e] text-[#22c55e]' : 'fill-[#6b7280] text-[#6b7280]'}
              />
              <span className={`text-[10px] ${connected ? 'text-[#22c55e]' : 'text-[#6b7280]'}`}>
                {connected ? 'Connected' : 'Waiting for events…'}
              </span>
            </div>
          </div>

          <button
            onClick={() => { onClose(); navigate(`/bots/${botId}`) }}
            className="flex items-center gap-1 text-[10px] text-text-muted hover:text-text-primary transition-colors shrink-0"
            title="View full details"
          >
            Full details <ArrowRight size={11} />
          </button>
        </div>

        {/* Events list */}
        <div className="flex-1 overflow-y-auto px-3 py-3 space-y-2">
          <div ref={topRef} />
          {events.length === 0 ? (
            <div className="flex flex-col items-center justify-center h-full gap-3 py-16">
              <div className="w-10 h-10 rounded-full border border-[#2d3039] flex items-center justify-center">
                <span className="text-lg">👁️</span>
              </div>
              <p className="text-[#4b5563] text-sm text-center">
                {connected
                  ? 'Waiting for the next cycle…\nEvents will appear here in real-time.'
                  : 'Connecting to event stream…'
                }
              </p>
            </div>
          ) : (
            events.map((event, i) => (
              <EventCard key={i} event={event} />
            ))
          )}
        </div>

        {/* Footer */}
        {events.length > 0 && (
          <div className="px-4 py-2 border-t border-[#2d3039] shrink-0 flex items-center justify-between">
            <span className="text-[#4b5563] text-[10px]">{events.length} events</span>
            <button
              onClick={() => setEvents([])}
              className="text-[10px] text-[#4b5563] hover:text-text-muted transition-colors"
            >
              Clear
            </button>
          </div>
        )}
      </div>
    </>
  )
}
