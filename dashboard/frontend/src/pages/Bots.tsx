import { useCallback, useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { AlertTriangle, Plus, Zap } from 'lucide-react'
import { api } from '../api/client'
import type { Bot, BotCreate } from '../types'
import BotCard from '../components/bots/BotCard'
import BotModal from '../components/bots/BotModal'

interface Props {
  refreshTick: number
}

const AUTO_REFRESH_MS = 10_000

export default function Bots({ refreshTick }: Props) {
  const [bots, setBots] = useState<Bot[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [actionLoading, setActionLoading] = useState<string | null>(null) // bot_id being acted on

  const [modalOpen, setModalOpen] = useState(false)
  const [editBot, setEditBot] = useState<Bot | undefined>()

  const [killConfirm, setKillConfirm] = useState(false)
  const [killing, setKilling] = useState(false)

  const fetchBots = useCallback(() => {
    api.getBots()
      .then(data => { setBots(data); setError(null) })
      .catch(e => setError(e.message))
      .finally(() => setLoading(false))
  }, [])

  // Initial load + external refresh tick
  useEffect(() => {
    setLoading(true)
    fetchBots()
  }, [refreshTick, fetchBots])

  // Local 10s auto-refresh
  useEffect(() => {
    const id = setInterval(fetchBots, AUTO_REFRESH_MS)
    return () => clearInterval(id)
  }, [fetchBots])

  // ── Bot actions ───────────────────────────────────────────────────────────

  async function withAction(botId: string, fn: () => Promise<Bot>) {
    setActionLoading(botId)
    try {
      const updated = await fn()
      setBots(prev => prev.map(b => b.id === botId ? updated : b))
    } catch (err: any) {
      setError(err.message ?? 'Action failed')
    } finally {
      setActionLoading(null)
    }
  }

  async function handleKillAll() {
    if (!killConfirm) {
      setKillConfirm(true)
      setTimeout(() => setKillConfirm(false), 4000)
      return
    }
    setKilling(true)
    setKillConfirm(false)
    try {
      await api.killAllBots()
      fetchBots()
    } catch (err: any) {
      setError(err.message ?? 'Kill all failed')
    } finally {
      setKilling(false)
    }
  }

  async function handleDelete(bot: Bot) {
    try {
      await api.deleteBot(bot.id)
      setBots(prev => prev.filter(b => b.id !== bot.id))
    } catch (err: any) {
      setError(err.message ?? 'Delete failed')
    }
  }

  function handleSaved(saved: Bot) {
    setBots(prev => {
      const exists = prev.find(b => b.id === saved.id)
      return exists ? prev.map(b => b.id === saved.id ? saved : b) : [saved, ...prev]
    })
    setModalOpen(false)
    setEditBot(undefined)
  }

  // ── Summary counts ────────────────────────────────────────────────────────
  const running = bots.filter(b => b.status === 'running').length
  const paused = bots.filter(b => b.status === 'paused').length
  const stopped = bots.filter(b => b.status === 'stopped' || b.status === 'error').length
  const hasRunning = running + paused > 0

  // ── Render ────────────────────────────────────────────────────────────────
  return (
    <div className="space-y-6">
      {/* Page header */}
      <div className="flex items-center justify-between gap-4 flex-wrap">
        <div>
          <h1 className="text-text-primary text-lg font-semibold">Bot Management</h1>
          <p className="text-text-muted text-xs mt-0.5">Command center — spawn, monitor, and control trading bots</p>
        </div>

        <div className="flex items-center gap-3 flex-wrap">
          {/* Kill All */}
          {hasRunning && (
            <button
              onClick={handleKillAll}
              disabled={killing}
              className={`flex items-center gap-1.5 px-3 py-1.5 rounded-md text-sm font-medium transition-colors disabled:opacity-50 ${
                killConfirm
                  ? 'bg-[#ef4444] text-white animate-pulse'
                  : 'bg-[#ef4444]/15 text-[#ef4444] hover:bg-[#ef4444]/30'
              }`}
            >
              <Zap size={14} />
              {killing ? 'Stopping all…' : killConfirm ? 'Are you sure?' : 'Kill All'}
            </button>
          )}

          {/* Create Bot */}
          <button
            onClick={() => { setEditBot(undefined); setModalOpen(true) }}
            className="flex items-center gap-1.5 px-4 py-1.5 rounded-md text-sm font-semibold bg-gradient-to-r from-accent to-accent/80 text-white hover:opacity-90 transition-opacity shadow-lg shadow-accent/20"
          >
            <Plus size={15} />
            Create Bot
          </button>
        </div>
      </div>

      {/* Summary row */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        <SummaryCard label="Total" value={bots.length} color="text-text-primary" />
        <SummaryCard label="Running" value={running} color="text-[#22c55e]" />
        <SummaryCard label="Paused" value={paused} color="text-[#eab308]" />
        <SummaryCard label="Stopped" value={stopped} color="text-[#6b7280]" />
      </div>

      {/* Error banner */}
      {error && (
        <div className="flex items-center gap-2 bg-[#ef4444]/10 border border-[#ef4444]/30 rounded-lg px-4 py-3 text-[#ef4444] text-sm">
          <AlertTriangle size={14} />
          {error}
          <button onClick={() => setError(null)} className="ml-auto text-xs underline">Dismiss</button>
        </div>
      )}

      {/* Bot grid */}
      {loading ? (
        <div className="text-text-muted text-sm animate-pulse py-16 text-center">Loading bots…</div>
      ) : bots.length === 0 ? (
        <EmptyState onCreateClick={() => setModalOpen(true)} />
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
          {bots.map(bot => (
            <div key={bot.id} className="relative group">
              {/* Clickable name overlay to navigate to detail */}
              <Link
                to={`/bots/${bot.id}`}
                className="absolute top-4 left-4 z-10 text-text-primary font-bold text-base leading-tight hover:text-accent transition-colors"
                style={{ pointerEvents: 'auto' }}
              >
                {/* invisible hit target over the name area — handled by BotCard's own name display */}
              </Link>
              <BotCard
                bot={bot}
                actionLoading={actionLoading === bot.id}
                onStart={() => withAction(bot.id, () => api.startBot(bot.id))}
                onStop={() => withAction(bot.id, () => api.stopBot(bot.id))}
                onPause={() => withAction(bot.id, () => api.pauseBot(bot.id))}
                onEdit={() => { setEditBot(bot); setModalOpen(true) }}
                onDelete={() => handleDelete(bot)}
              />
            </div>
          ))}
        </div>
      )}

      {/* Modal */}
      {modalOpen && (
        <BotModal
          bot={editBot}
          onClose={() => { setModalOpen(false); setEditBot(undefined) }}
          onSaved={handleSaved}
        />
      )}
    </div>
  )
}

function SummaryCard({ label, value, color }: { label: string; value: number; color: string }) {
  return (
    <div className="bg-[#1a1d26] border border-[#2d3039] rounded-xl px-4 py-3">
      <p className="text-text-muted text-xs">{label}</p>
      <p className={`text-2xl font-bold mt-0.5 ${color}`}>{value}</p>
    </div>
  )
}

function EmptyState({ onCreateClick }: { onCreateClick: () => void }) {
  return (
    <div className="flex flex-col items-center justify-center py-24 gap-4 text-center">
      <div className="w-14 h-14 rounded-2xl bg-[#1a1d26] border border-[#2d3039] flex items-center justify-center">
        <Plus size={24} className="text-text-muted" />
      </div>
      <div>
        <p className="text-text-primary font-medium">No bots yet</p>
        <p className="text-text-muted text-sm mt-1">Create your first bot to start trading</p>
      </div>
      <button
        onClick={onCreateClick}
        className="px-5 py-2 rounded-md text-sm font-semibold bg-accent text-white hover:bg-accent/90 transition-colors"
      >
        Create Bot
      </button>
    </div>
  )
}
