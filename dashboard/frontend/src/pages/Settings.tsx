import { useEffect, useState } from 'react'
import { api } from '../api/client'
import type { ConfigData } from '../types'
import { ExternalLink } from 'lucide-react'

interface Props {
  refreshTick: number
}

function Row({ label, value }: { label: string; value: string | number | boolean }) {
  return (
    <div className="flex items-center justify-between py-3 border-b border-border/50">
      <span className="text-text-secondary text-sm">{label}</span>
      <span className="font-mono text-xs text-text-primary bg-bg-elevated px-2 py-1 rounded">
        {String(value)}
      </span>
    </div>
  )
}

export default function Settings({ refreshTick }: Props) {
  const [config, setConfig] = useState<ConfigData | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    api.config()
      .then(c => setConfig(c))
      .catch(() => setConfig(null))
      .finally(() => setLoading(false))
  }, [refreshTick])

  return (
    <div className="space-y-6 max-w-2xl">
      <div>
        <h1 className="text-text-primary text-lg font-semibold">Settings</h1>
        <p className="text-text-muted text-xs mt-0.5">Current QuantAgent configuration (read-only)</p>
      </div>

      {loading ? (
        <div className="text-text-muted text-sm animate-pulse py-8">Loading…</div>
      ) : config ? (
        <>
          <section className="bg-bg-card border border-border rounded-lg p-5">
            <h2 className="text-text-primary text-sm font-semibold mb-3">Trading</h2>
            <Row label="Symbol" value={config.symbol} />
            <Row label="Timeframe" value={config.timeframe} />
            <Row label="Lookback Bars" value={config.lookback_bars} />
            <Row label="Data Exchange" value={config.data_exchange} />
          </section>

          <section className="bg-bg-card border border-border rounded-lg p-5">
            <h2 className="text-text-primary text-sm font-semibold mb-3">Risk / ATR</h2>
            <Row label="ATR Length" value={config.atr_length} />
            <Row label="ATR Multiplier" value={config.atr_multiplier} />
            <Row label="Forecast Candles" value={config.forecast_candles} />
          </section>

          <section className="bg-bg-card border border-border rounded-lg p-5">
            <h2 className="text-text-primary text-sm font-semibold mb-3">LLM</h2>
            <Row label="Model" value={config.model_name} />
          </section>

          <section className="bg-bg-card border border-border rounded-lg p-5">
            <h2 className="text-text-primary text-sm font-semibold mb-3">Integrations</h2>
            <Row label="LangSmith Tracing" value={config.langsmith_enabled ? 'Enabled' : 'Disabled'} />
            {config.langsmith_enabled && (
              <>
                <Row label="LangSmith Project" value={config.langsmith_project} />
                <div className="mt-3">
                  <a
                    href="https://smith.langchain.com"
                    target="_blank"
                    rel="noopener noreferrer"
                    className="inline-flex items-center gap-1.5 text-accent text-xs hover:underline"
                  >
                    Open LangSmith <ExternalLink size={12} />
                  </a>
                </div>
              </>
            )}
            <div className="mt-3">
              <a
                href="https://test.deribit.com"
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex items-center gap-1.5 text-accent text-xs hover:underline"
              >
                Open Deribit Testnet <ExternalLink size={12} />
              </a>
            </div>
          </section>
        </>
      ) : (
        <div className="bg-bg-card border border-border rounded-lg p-6">
          <p className="text-text-muted text-sm">Could not load config. Backend may not be running.</p>
        </div>
      )}
    </div>
  )
}
