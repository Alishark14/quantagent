import { RefreshCw } from 'lucide-react'
import type { Mode } from '../../context/GlobalFilterContext'

interface HeaderProps {
  lastRefresh: Date | null
  onRefresh: () => void
  refreshing: boolean
  mode: Mode
  setMode: (m: Mode) => void
}

const MODE_BUTTONS: { key: Mode; label: string }[] = [
  { key: 'all', label: 'All' },
  { key: 'paper', label: 'Paper' },
  { key: 'live', label: 'Live' },
]

function modeStyle(key: Mode, active: Mode): string {
  if (key !== active) {
    return 'bg-transparent text-text-muted hover:text-text-secondary'
  }
  if (key === 'paper') return 'bg-blue-500/20 text-blue-400'
  if (key === 'live') return 'bg-orange-500/20 text-orange-400'
  return 'bg-bg-elevated text-text-primary'
}

export default function Header({ lastRefresh, onRefresh, refreshing, mode, setMode }: HeaderProps) {
  return (
    <header className="h-12 flex items-center justify-between px-6 border-b border-border bg-bg-card shrink-0 gap-4">
      <span className="text-text-secondary text-sm shrink-0">
        {lastRefresh
          ? `Last updated: ${lastRefresh.toLocaleTimeString()}`
          : 'Loading…'}
      </span>

      {/* Paper / Live / All segmented toggle */}
      <div className="flex items-center gap-0.5 bg-bg-elevated border border-border rounded-lg p-0.5">
        {MODE_BUTTONS.map(({ key, label }) => (
          <button
            key={key}
            onClick={() => setMode(key)}
            className={`px-3 py-1 rounded-md text-xs font-medium transition-colors ${modeStyle(key, mode)}`}
          >
            {label}
          </button>
        ))}
      </div>

      <button
        onClick={onRefresh}
        disabled={refreshing}
        className="flex items-center gap-2 px-3 py-1.5 rounded-md bg-bg-elevated border border-border text-text-secondary hover:text-text-primary text-xs transition-colors disabled:opacity-50 shrink-0"
      >
        <RefreshCw size={12} className={refreshing ? 'animate-spin' : ''} />
        Refresh
      </button>
    </header>
  )
}
