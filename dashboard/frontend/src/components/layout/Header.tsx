import { RefreshCw } from 'lucide-react'

interface HeaderProps {
  lastRefresh: Date | null
  onRefresh: () => void
  refreshing: boolean
}

export default function Header({ lastRefresh, onRefresh, refreshing }: HeaderProps) {
  return (
    <header className="h-12 flex items-center justify-between px-6 border-b border-border bg-bg-card shrink-0">
      <span className="text-text-secondary text-sm">
        {lastRefresh
          ? `Last updated: ${lastRefresh.toLocaleTimeString()}`
          : 'Loading…'}
      </span>
      <button
        onClick={onRefresh}
        disabled={refreshing}
        className="flex items-center gap-2 px-3 py-1.5 rounded-md bg-bg-elevated border border-border text-text-secondary hover:text-text-primary text-xs transition-colors disabled:opacity-50"
      >
        <RefreshCw size={12} className={refreshing ? 'animate-spin' : ''} />
        Refresh
      </button>
    </header>
  )
}
