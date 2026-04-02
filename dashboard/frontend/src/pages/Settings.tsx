import { useEffect, useState } from 'react'
import { api } from '../api/client'
import type { ApiCostData, Bot, ConfigData, ExchangeStatus, HealthData } from '../types'
import { ExternalLink, CheckCircle2, XCircle } from 'lucide-react'

interface Props {
  refreshTick: number
}

const EXCHANGE_LINKS: Record<string, { main: string; label: string }> = {
  dydx: { main: 'https://dydx.trade', label: 'View on dYdX' },
  hyperliquid: { main: 'https://app.hyperliquid.xyz', label: 'View on Hyperliquid' },
  deribit: { main: 'https://www.deribit.com', label: 'View on Deribit' },
}

const EXCHANGE_LABELS: Record<string, string> = {
  dydx: 'dYdX v4',
  hyperliquid: 'Hyperliquid',
  deribit: 'Deribit',
}

const AGENT_COLORS: Record<string, string> = {
  indicator: 'bg-blue-500',
  pattern: 'bg-purple-500',
  trend: 'bg-cyan-500',
  decision: 'bg-amber-500',
}

function StatusDot({ status }: { status: ExchangeStatus['status'] }) {
  if (status === 'connected') {
    return <span className="w-2.5 h-2.5 rounded-full bg-[#22c55e] shrink-0" />
  }
  return <span className="w-2.5 h-2.5 rounded-full bg-[#6b7280] shrink-0" />
}

function ExchangeCard({ ex }: { ex: ExchangeStatus }) {
  const link = EXCHANGE_LINKS[ex.name]
  const label = EXCHANGE_LABELS[ex.name] ?? ex.name

  return (
    <div className="flex items-start gap-3 p-4 border-b border-border/50 last:border-0">
      <StatusDot status={ex.status} />
      <div className="flex-1 min-w-0">
        <div className="flex items-center justify-between gap-2 flex-wrap">
          <span className="text-text-primary text-sm font-medium">{label}</span>
          <span className={`text-xs font-medium px-2 py-0.5 rounded ${
            ex.status === 'connected'
              ? 'bg-[#22c55e]/15 text-[#22c55e]'
              : 'bg-[#6b7280]/15 text-[#6b7280]'
          }`}>
            {ex.status === 'connected' ? 'Connected' : 'Not configured'}
          </span>
        </div>
        {ex.status === 'connected' && (
          <div className="mt-1 text-xs text-text-muted space-y-0.5">
            <div>Network: {ex.testnet ? 'Testnet' : 'Mainnet'}</div>
            {ex.balance !== null && ex.balance !== undefined && (
              <div>Balance: <span className="text-text-secondary font-mono">${ex.balance.toFixed(2)}</span></div>
            )}
          </div>
        )}
        {ex.status === 'error' && ex.error && (
          <p className="text-[10px] text-text-muted mt-1 truncate" title={ex.error}>
            {ex.error.split('\n')[0].slice(0, 80)}
          </p>
        )}
      </div>
      {link && (
        <a
          href={link.main}
          target="_blank"
          rel="noopener noreferrer"
          className="inline-flex items-center gap-1 text-accent text-xs hover:underline shrink-0"
        >
          {link.label} <ExternalLink size={11} />
        </a>
      )}
    </div>
  )
}

export default function Settings({ refreshTick }: Props) {
  const [exchanges, setExchanges] = useState<ExchangeStatus[]>([])
  const [exLoading, setExLoading] = useState(true)
  const [config, setConfig] = useState<ConfigData | null>(null)
  const [bots, setBots] = useState<Bot[]>([])
  const [healthData, setHealthData] = useState<HealthData | null>(null)
  const [costData, setCostData] = useState<ApiCostData | null>(null)

  useEffect(() => {
    setExLoading(true)
    Promise.all([
      api.exchangeStatus().catch(() => [] as ExchangeStatus[]),
      api.config().catch(() => null),
      api.getBots().catch(() => [] as Bot[]),
      api.health().catch(() => null),
      api.apiCosts().catch(() => null),
    ]).then(([ex, cfg, bs, health, costs]) => {
      setExchanges(ex)
      setConfig(cfg)
      setBots(bs)
      setHealthData(health)
      setCostData(costs)
    }).finally(() => setExLoading(false))
  }, [refreshTick])

  const runningBots = bots.filter(b => b.status === 'running').length
  const versionLabel = healthData?.version_full ?? 'QuantAgent v0.5.0'

  return (
    <div className="space-y-6 max-w-2xl">
      <div>
        <h1 className="text-text-primary text-lg font-semibold">Settings</h1>
        <p className="text-text-muted text-xs mt-0.5">Exchange connections, API services, and system info</p>
      </div>

      {/* Exchange Connections */}
      <section className="bg-bg-card border border-border rounded-lg overflow-hidden">
        <div className="px-5 py-4 border-b border-border">
          <h2 className="text-text-primary text-sm font-semibold">Exchange Connections</h2>
        </div>
        {exLoading ? (
          <div className="px-5 py-8 text-text-muted text-sm animate-pulse">Checking connections…</div>
        ) : exchanges.length === 0 ? (
          <div className="px-5 py-8 text-text-muted text-sm">No exchange data available.</div>
        ) : (
          <div>
            {exchanges.map(ex => (
              <ExchangeCard key={ex.name} ex={ex} />
            ))}
            <div className="flex items-center gap-3 p-4 opacity-40">
              <span className="w-2.5 h-2.5 rounded-full border border-border shrink-0" />
              <div>
                <span className="text-text-secondary text-sm">Add Exchange</span>
                <p className="text-text-muted text-xs">Configure additional exchange credentials in .env</p>
              </div>
            </div>
          </div>
        )}
      </section>

      {/* API Services */}
      <section className="bg-bg-card border border-border rounded-lg p-5">
        <h2 className="text-text-primary text-sm font-semibold mb-4">API Services</h2>
        <div className="space-y-3">
          <div className="flex items-center justify-between">
            <span className="text-text-secondary text-sm">Anthropic API</span>
            <span className="flex items-center gap-1.5 text-xs text-[#22c55e]">
              <CheckCircle2 size={13} /> Active (key configured)
            </span>
          </div>
          <div className="flex items-center justify-between">
            <span className="text-text-secondary text-sm">LangSmith</span>
            {config?.langsmith_enabled ? (
              <div className="flex items-center gap-2">
                <span className="flex items-center gap-1.5 text-xs text-[#22c55e]">
                  <CheckCircle2 size={13} /> Enabled
                </span>
                <a
                  href="https://smith.langchain.com"
                  target="_blank"
                  rel="noopener noreferrer"
                  className="inline-flex items-center gap-1 text-accent text-xs hover:underline"
                >
                  Open Dashboard <ExternalLink size={11} />
                </a>
              </div>
            ) : (
              <span className="flex items-center gap-1.5 text-xs text-text-muted">
                <XCircle size={13} /> Disabled
              </span>
            )}
          </div>
        </div>
      </section>

      {/* API Cost Analytics */}
      <section className="bg-bg-card border border-border rounded-lg p-5">
        <h2 className="text-text-primary text-sm font-semibold mb-4">API Cost Analytics</h2>
        {costData && costData.cycles_run > 0 ? (
          <div className="space-y-5">
            {/* Summary */}
            <div className="grid grid-cols-3 gap-4">
              <div>
                <p className="text-text-muted text-xs uppercase tracking-wide mb-1">Total Spend</p>
                <p className="text-text-primary font-mono text-xl font-bold">${costData.total_cost.toFixed(2)}</p>
              </div>
              <div>
                <p className="text-text-muted text-xs uppercase tracking-wide mb-1">Cycles Run</p>
                <p className="text-text-primary font-mono text-xl font-bold">{costData.cycles_run}</p>
              </div>
              <div>
                <p className="text-text-muted text-xs uppercase tracking-wide mb-1">Avg / Cycle</p>
                <p className="text-text-primary font-mono text-xl font-bold">${costData.avg_cost_per_cycle.toFixed(4)}</p>
              </div>
            </div>

            {/* Agent breakdown */}
            <div>
              <p className="text-text-secondary text-xs font-medium mb-3">Agent Breakdown</p>
              <div className="space-y-2.5">
                {(Object.entries(costData.agents) as [string, { cost: number; pct: number; input_tokens: number; output_tokens: number }][]).map(([agent, stat]) => (
                  <div key={agent}>
                    <div className="flex items-center justify-between text-xs mb-1">
                      <span className="text-text-secondary capitalize">{agent}</span>
                      <span className="font-mono text-text-primary tabular-nums">
                        ${stat.cost.toFixed(4)} <span className="text-text-muted">({stat.pct}%)</span>
                      </span>
                    </div>
                    <div className="h-1.5 bg-bg-elevated rounded-full overflow-hidden">
                      <div
                        className={`h-full rounded-full ${AGENT_COLORS[agent] ?? 'bg-accent'}`}
                        style={{ width: `${Math.max(stat.pct, 2)}%` }}
                      />
                    </div>
                  </div>
                ))}
              </div>
            </div>

            {/* Today + monthly estimate */}
            <div className="space-y-2 pt-3 border-t border-border/40">
              <div className="flex items-center justify-between text-xs">
                <span className="text-text-secondary">Today</span>
                <span className="font-mono text-text-primary tabular-nums">
                  ${costData.daily_cost.toFixed(4)} · {costData.cycles_today} cycles
                </span>
              </div>
              <div className="flex items-center justify-between text-xs">
                <span className="text-text-secondary">Monthly Estimate</span>
                <span className="font-mono text-text-primary tabular-nums">
                  ${costData.monthly_estimate.toFixed(2)}
                  <span className="text-text-muted ml-1">(based on today's rate)</span>
                </span>
              </div>
            </div>
          </div>
        ) : (
          <p className="text-text-muted text-sm">No cost data yet. Run trading cycles to see analytics.</p>
        )}
      </section>

      {/* System Info */}
      <section className="bg-bg-card border border-border rounded-lg p-5">
        <h2 className="text-text-primary text-sm font-semibold mb-4">System Info</h2>
        <div className="space-y-2 text-sm">
          {[
            ['Version', versionLabel],
            ['Phase', healthData?.phase ?? '—'],
            ['Architecture', 'Pluggable Exchange Adapters'],
            ['LLM', config?.model_name ?? '—'],
            ['Data Source', config?.data_exchange ?? '—'],
            ['Active Bots', String(runningBots)],
            ['Total Bots', String(bots.length)],
          ].map(([label, value]) => (
            <div key={label} className="flex items-center justify-between py-1.5 border-b border-border/40 last:border-0">
              <span className="text-text-secondary">{label}</span>
              <span className="font-mono text-xs text-text-primary bg-bg-elevated px-2 py-0.5 rounded">{value}</span>
            </div>
          ))}
        </div>
      </section>
    </div>
  )
}
