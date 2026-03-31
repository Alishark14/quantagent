import { useEffect, useState } from 'react'
import { api } from '../../api/client'
import type { Bot } from '../../types'

interface Props {
  value: string | undefined
  onChange: (botId: string | undefined) => void
}

export default function BotSelector({ value, onChange }: Props) {
  const [bots, setBots] = useState<Bot[]>([])

  useEffect(() => {
    api.getBots().then(setBots).catch(() => {})
  }, [])

  if (!bots.length) return null

  return (
    <div className="flex items-center gap-2">
      <span className="text-xs text-text-muted">Bot:</span>
      <select
        value={value ?? ''}
        onChange={e => onChange(e.target.value || undefined)}
        className="bg-bg-elevated border border-border rounded-md px-2 py-1 text-xs text-text-primary focus:outline-none focus:border-accent transition-colors"
      >
        <option value="">All Bots</option>
        {bots.map(b => (
          <option key={b.id} value={b.id}>
            {b.name} ({b.symbol})
          </option>
        ))}
      </select>
    </div>
  )
}
