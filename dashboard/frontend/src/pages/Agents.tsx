import { useEffect, useState } from 'react'
import { api } from '../api/client'
import type { AgentsData } from '../types'
import AgentAccuracy from '../components/agents/AgentAccuracy'
import AgentAgreement from '../components/agents/AgentAgreement'
import BotSelector from '../components/bots/BotSelector'
import { useGlobalFilter } from '../context/GlobalFilterContext'

interface Props {
  refreshTick: number
}

const AGENT_NAMES: Record<string, string> = {
  indicator: 'Indicator',
  pattern: 'Pattern',
  trend: 'Trend',
}

export default function Agents({ refreshTick }: Props) {
  const [data, setData] = useState<AgentsData | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [botId, setBotId] = useState<string | undefined>()
  const { mode } = useGlobalFilter()

  useEffect(() => {
    setLoading(true)
    api.agents(botId, mode)
      .then(d => { setData(d); setError(null) })
      .catch(e => setError(e.message))
      .finally(() => setLoading(false))
  }, [refreshTick, botId, mode])

  return (
    <div className="space-y-6">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h1 className="text-text-primary text-lg font-semibold">Agent Analysis</h1>
          <p className="text-text-muted text-xs mt-0.5">
            Accuracy estimated by parsing DecisionAgent justification text — will improve once per-agent signals are logged explicitly
          </p>
        </div>
        <BotSelector value={botId} onChange={setBotId} />
      </div>

      {error ? (
        <div className="bg-loss/10 border border-loss/30 rounded-lg p-4">
          <p className="text-loss text-sm">{error}</p>
        </div>
      ) : loading ? (
        <div className="text-text-muted text-sm animate-pulse py-12 text-center">Loading…</div>
      ) : data ? (
        <>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            {Object.entries(data.agents).map(([key, stat]) => (
              <AgentAccuracy key={key} name={AGENT_NAMES[key] ?? key} stat={stat} />
            ))}
          </div>
          <AgentAgreement data={data.agreement_data} />
        </>
      ) : null}
    </div>
  )
}
