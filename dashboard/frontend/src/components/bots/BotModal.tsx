import { useEffect, useState } from 'react'
import { AlertTriangle, ChevronDown, ChevronUp, X } from 'lucide-react'
import { api } from '../../api/client'
import type { Bot, BotCreate } from '../../types'

interface Props {
  bot?: Bot
  onClose: () => void
  onSaved: (bot: Bot) => void
}

type FormData = Required<BotCreate>

const DEFAULTS: FormData = {
  name: '',
  symbol: 'BTC-USDC',
  market_type: 'perpetual',
  timeframe: '1h',
  budget_usd: 100,
  max_concurrent_positions: 1,
  trading_mode: 'live',
  atr_multiplier: 1.5,
  atr_length: 14,
  rr_ratio_min: 1.2,
  rr_ratio_max: 1.8,
  max_daily_loss_usd: 100,
  max_position_pct: 1.0,
  forecast_candles: 3,
  agents_enabled: 'indicator,pattern,trend',
  llm_model: 'claude-sonnet-4-20250514',
  exchange: 'hyperliquid',
  exchange_testnet: 0,
}

function parseAgents(str: string): { indicator: boolean; pattern: boolean; trend: boolean } {
  const parts = str.split(',').map(s => s.trim())
  return {
    indicator: parts.includes('indicator'),
    pattern: parts.includes('pattern'),
    trend: parts.includes('trend'),
  }
}

function buildAgentsStr(a: { indicator: boolean; pattern: boolean; trend: boolean }): string {
  return ['indicator', 'pattern', 'trend'].filter(k => a[k as keyof typeof a]).join(',')
}

// ── Sub-components ─────────────────────────────────────────────────────────

function Label({ children }: { children: React.ReactNode }) {
  return <label className="block text-xs font-medium text-text-secondary mb-1">{children}</label>
}

function Input({
  type = 'text',
  value,
  onChange,
  min,
  max,
  step,
  placeholder,
  className = '',
}: {
  type?: string
  value: string | number
  onChange: (v: string) => void
  min?: number
  max?: number
  step?: number
  placeholder?: string
  className?: string
}) {
  return (
    <input
      type={type}
      value={value}
      onChange={e => onChange(e.target.value)}
      min={min}
      max={max}
      step={step}
      placeholder={placeholder}
      className={`w-full bg-[#1a1d26] border border-[#2d3039] rounded-md px-3 py-1.5 text-sm text-text-primary placeholder-text-muted focus:outline-none focus:border-accent transition-colors ${className}`}
    />
  )
}

function Select({
  value,
  onChange,
  options,
}: {
  value: string
  onChange: (v: string) => void
  options: { value: string; label: string }[]
}) {
  return (
    <select
      value={value}
      onChange={e => onChange(e.target.value)}
      className="w-full bg-[#1a1d26] border border-[#2d3039] rounded-md px-3 py-1.5 text-sm text-text-primary focus:outline-none focus:border-accent transition-colors"
    >
      {options.map(o => (
        <option key={o.value} value={o.value} className="bg-[#1a1d26]">
          {o.label}
        </option>
      ))}
    </select>
  )
}

function GroupedSelect({
  value,
  onChange,
  groups,
}: {
  value: string
  onChange: (v: string) => void
  groups: { label: string; options: { value: string; label: string }[] }[]
}) {
  return (
    <select
      value={value}
      onChange={e => onChange(e.target.value)}
      className="w-full bg-[#1a1d26] border border-[#2d3039] rounded-md px-3 py-1.5 text-sm text-text-primary focus:outline-none focus:border-accent transition-colors"
    >
      {groups.map(g => (
        <optgroup key={g.label} label={g.label} className="bg-[#1a1d26] text-text-muted">
          {g.options.map(o => (
            <option key={o.value} value={o.value} className="bg-[#1a1d26]">
              {o.label}
            </option>
          ))}
        </optgroup>
      ))}
    </select>
  )
}

function Toggle({
  value,
  onChange,
  labelOff,
  labelOn,
  colorOn = 'bg-accent',
}: {
  value: boolean
  onChange: (v: boolean) => void
  labelOff: string
  labelOn: string
  colorOn?: string
}) {
  return (
    <div className="flex items-center gap-2">
      <button
        type="button"
        onClick={() => onChange(!value)}
        className={`relative w-9 h-5 rounded-full transition-colors ${value ? colorOn : 'bg-[#2d3039]'}`}
      >
        <span
          className={`absolute top-0.5 left-0.5 w-4 h-4 rounded-full bg-white transition-transform ${value ? 'translate-x-4' : ''}`}
        />
      </button>
      <span className="text-sm text-text-secondary">{value ? labelOn : labelOff}</span>
    </div>
  )
}

function SliderRow({
  label,
  value,
  min,
  max,
  step,
  onChange,
  format = (v: number) => String(v),
}: {
  label: string
  value: number
  min: number
  max: number
  step: number
  onChange: (v: number) => void
  format?: (v: number) => string
}) {
  return (
    <div>
      <div className="flex items-center justify-between mb-1">
        <Label>{label}</Label>
        <span className="text-xs font-mono text-accent">{format(value)}</span>
      </div>
      <input
        type="range"
        min={min}
        max={max}
        step={step}
        value={value}
        onChange={e => onChange(Number(e.target.value))}
        className="w-full accent-accent"
      />
    </div>
  )
}

function SectionHeader({ children }: { children: React.ReactNode }) {
  return (
    <div className="text-xs font-semibold text-text-muted uppercase tracking-widest py-2 border-b border-[#2d3039] mb-3">
      {children}
    </div>
  )
}

function ErrMsg({ msg }: { msg?: string }) {
  if (!msg) return null
  return <p className="text-[#ef4444] text-xs mt-1">{msg}</p>
}

// ── Main component ─────────────────────────────────────────────────────────

export default function BotModal({ bot, onClose, onSaved }: Props) {
  const isEdit = !!bot
  const [form, setForm] = useState<FormData>(() =>
    bot
      ? {
          name: bot.name,
          symbol: bot.symbol,
          market_type: bot.market_type,
          timeframe: bot.timeframe,
          budget_usd: bot.budget_usd,
          max_concurrent_positions: bot.max_concurrent_positions,
          trading_mode: bot.trading_mode,
          atr_multiplier: bot.atr_multiplier,
          atr_length: bot.atr_length,
          rr_ratio_min: bot.rr_ratio_min,
          rr_ratio_max: bot.rr_ratio_max,
          max_daily_loss_usd: bot.max_daily_loss_usd,
          max_position_pct: bot.max_position_pct,
          forecast_candles: bot.forecast_candles,
          agents_enabled: bot.agents_enabled,
          llm_model: bot.llm_model,
          exchange: bot.exchange,
          exchange_testnet: bot.exchange_testnet,
        }
      : DEFAULTS
  )

  const [agents, setAgents] = useState(() => parseAgents(form.agents_enabled))
  const [errors, setErrors] = useState<Record<string, string>>({})
  const [submitting, setSubmitting] = useState(false)
  const [apiError, setApiError] = useState<string | null>(null)
  const [symbolGroups, setSymbolGroups] = useState(SYMBOL_GROUPS)
  const [knownSymbols, setKnownSymbols] = useState<string[]>(() =>
    SYMBOL_GROUPS.flatMap(g => g.options.map(o => o.value)).filter(v => v !== '__custom__')
  )
  const [customSymbol, setCustomSymbol] = useState(() => {
    const known = SYMBOL_GROUPS.flatMap(g => g.options.map(o => o.value)).filter(v => v !== '__custom__')
    return !known.includes(form.symbol)
  })
  const [showAdvanced, setShowAdvanced] = useState(false)

  // Fetch live symbol list from backend (built from exchange markets)
  useEffect(() => {
    api.getAvailableSymbols().then(syms => {
      if (!syms || !syms.length) return
      // Build grouped options from API response
      const byCategory: Record<string, { value: string; label: string }[]> = {}
      for (const s of syms) {
        const cat = s.category || 'Other'
        if (!byCategory[cat]) byCategory[cat] = []
        byCategory[cat].push({ value: s.value, label: s.label })
      }
      const order = ['Crypto', 'Commodities', 'Indices', 'Stocks', 'Forex', 'Energy', 'Other']
      const groups = order
        .filter(c => byCategory[c])
        .map(c => ({ label: c, options: byCategory[c] }))
      // Always append custom option
      groups.push({ label: 'Other', options: [{ value: '__custom__', label: 'Custom symbol…' }] })
      setSymbolGroups(groups)
      const all = syms.map(s => s.value)
      setKnownSymbols(all)
      // If current symbol isn't in new list, switch to custom input
      if (form.symbol && !all.includes(form.symbol)) {
        setCustomSymbol(true)
      }
    }).catch(() => { /* keep static groups on error */ })
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

  // Keep agents_enabled in sync with checkboxes
  useEffect(() => {
    setForm(f => ({ ...f, agents_enabled: buildAgentsStr(agents) }))
  }, [agents])

  function set<K extends keyof FormData>(key: K, value: FormData[K]) {
    setForm(f => ({ ...f, [key]: value }))
    setErrors(e => { const c = { ...e }; delete c[key]; return c })
  }

  function validate(): boolean {
    const e: Record<string, string> = {}
    if (!form.name.trim()) e.name = 'Name is required'
    else if (form.name.length > 50) e.name = 'Max 50 characters'
    if (!form.symbol.trim()) e.symbol = 'Symbol is required'
    if (form.budget_usd < 20) e.budget_usd = 'Minimum budget is $20'
    if (form.max_daily_loss_usd < 10) e.max_daily_loss_usd = 'Minimum $10'
    if (!buildAgentsStr(agents)) e.agents_enabled = 'At least one agent required'
    if (form.rr_ratio_min >= form.rr_ratio_max) e.rr_ratio_min = 'Min must be less than max'
    setErrors(e)
    return Object.keys(e).length === 0
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    if (!validate()) return
    setSubmitting(true)
    setApiError(null)
    try {
      const payload = { ...form, symbol: form.symbol.toUpperCase() }
      const saved = isEdit
        ? await api.updateBot(bot!.id, payload)
        : await api.createBot(payload)
      onSaved(saved)
    } catch (err: any) {
      setApiError(err.message ?? 'Unknown error')
    } finally {
      setSubmitting(false)
    }
  }

  // Close on backdrop click
  function handleBackdrop(e: React.MouseEvent<HTMLDivElement>) {
    if (e.target === e.currentTarget) onClose()
  }

  const SYMBOL_GROUPS = [
    {
      label: 'Crypto',
      options: [
        { value: 'BTC-USDC',  label: 'BTC-USDC (Bitcoin)' },
        { value: 'ETH-USDC',  label: 'ETH-USDC (Ethereum)' },
        { value: 'SOL-USDC',  label: 'SOL-USDC (Solana)' },
        { value: 'DOGE-USDC', label: 'DOGE-USDC (Dogecoin)' },
        { value: 'AVAX-USDC', label: 'AVAX-USDC (Avalanche)' },
        { value: 'LINK-USDC', label: 'LINK-USDC (Chainlink)' },
        { value: 'HYPE-USDC', label: 'HYPE-USDC (Hyperliquid)' },
        { value: 'XPL-USDC',  label: 'XPL-USDC (Plasma)' },
      ],
    },
    {
      label: 'Commodities (HIP-3)',
      options: [
        { value: 'GOLD-USDC',      label: 'GOLD-USDC (Gold)' },
        { value: 'SILVER-USDC',    label: 'SILVER-USDC (Silver)' },
        { value: 'WTIOIL-USDC',    label: 'WTIOIL-USDC (WTI Crude Oil)' },
        { value: 'BRENTOIL-USDC',  label: 'BRENTOIL-USDC (Brent Crude)' },
        { value: 'NATGAS-USDC',    label: 'NATGAS-USDC (Natural Gas)' },
        { value: 'COPPER-USDC',    label: 'COPPER-USDC (Copper)' },
        { value: 'PLATINUM-USDC',  label: 'PLATINUM-USDC (Platinum)' },
        { value: 'PALLADIUM-USDC', label: 'PALLADIUM-USDC (Palladium)' },
        { value: 'URANIUM-USDC',   label: 'URANIUM-USDC (Uranium)' },
        { value: 'WHEAT-USDC',     label: 'WHEAT-USDC (Wheat)' },
        { value: 'CORN-USDC',      label: 'CORN-USDC (Corn)' },
        { value: 'ALUMINIUM-USDC', label: 'ALUMINIUM-USDC (Aluminium)' },
      ],
    },
    {
      label: 'Indices (HIP-3)',
      options: [
        { value: 'SP500-USDC', label: 'SP500-USDC (S&P 500)' },
        { value: 'JP225-USDC', label: 'JP225-USDC (Nikkei 225)' },
        { value: 'VIX-USDC',   label: 'VIX-USDC (Volatility Index)' },
        { value: 'DXY-USDC',    label: 'DXY-USDC (Dollar Index)' },
        { value: 'XYZ100-USDC', label: 'XYZ100-USDC (Nasdaq-100)' },
      ],
    },
    {
      label: 'Stocks (HIP-3)',
      options: [
        { value: 'TSLA-USDC',  label: 'TSLA-USDC (Tesla)' },
        { value: 'NVDA-USDC',  label: 'NVDA-USDC (Nvidia)' },
        { value: 'AAPL-USDC',  label: 'AAPL-USDC (Apple)' },
        { value: 'META-USDC',  label: 'META-USDC (Meta)' },
        { value: 'MSFT-USDC',  label: 'MSFT-USDC (Microsoft)' },
        { value: 'GOOGL-USDC', label: 'GOOGL-USDC (Google)' },
        { value: 'AMZN-USDC',  label: 'AMZN-USDC (Amazon)' },
        { value: 'AMD-USDC',   label: 'AMD-USDC (AMD)' },
        { value: 'NFLX-USDC',  label: 'NFLX-USDC (Netflix)' },
        { value: 'PLTR-USDC',  label: 'PLTR-USDC (Palantir)' },
        { value: 'COIN-USDC',  label: 'COIN-USDC (Coinbase)' },
        { value: 'MSTR-USDC',  label: 'MSTR-USDC (MicroStrategy)' },
      ],
    },
    {
      label: 'Forex (HIP-3)',
      options: [
        { value: 'EUR-USDC', label: 'EUR-USDC (Euro)' },
        { value: 'JPY-USDC', label: 'JPY-USDC (Japanese Yen)' },
      ],
    },
    {
      label: 'Other',
      options: [
        { value: '__custom__', label: 'Custom symbol…' },
      ],
    },
  ]

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm p-4"
      onClick={handleBackdrop}
    >
      <div className="bg-[#1a1d26] border border-[#2d3039] rounded-xl w-full max-w-2xl max-h-[90vh] flex flex-col shadow-2xl">
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-[#2d3039]">
          <h2 className="text-text-primary font-semibold text-base">
            {isEdit ? `Edit — ${bot!.name}` : 'Create Bot'}
          </h2>
          <button onClick={onClose} className="text-text-muted hover:text-text-primary transition-colors">
            <X size={18} />
          </button>
        </div>

        {/* Body */}
        <form onSubmit={handleSubmit} className="flex-1 overflow-y-auto px-6 py-5 space-y-6">
          {/* IDENTITY */}
          <div>
            <SectionHeader>Identity</SectionHeader>
            <div className="grid grid-cols-2 gap-4">
              <div className="col-span-2">
                <Label>Name</Label>
                <Input
                  value={form.name}
                  onChange={v => set('name', v)}
                  placeholder="e.g. BTC Scalper"
                />
                <ErrMsg msg={errors.name} />
              </div>
              <div>
                <Label>Symbol</Label>
                {customSymbol ? (
                  <div className="flex gap-2">
                    <Input
                      value={form.symbol}
                      onChange={v => set('symbol', v.toUpperCase())}
                      placeholder="e.g. XRP-USDC"
                    />
                    <button
                      type="button"
                      onClick={() => {
                        setCustomSymbol(false)
                        if (!knownSymbols.includes(form.symbol)) set('symbol', 'BTC-USDC')
                      }}
                      className="text-xs text-text-muted hover:text-text-primary px-2"
                    >
                      ↩
                    </button>
                  </div>
                ) : (
                  <GroupedSelect
                    value={form.symbol}
                    onChange={v => {
                      if (v === '__custom__') { setCustomSymbol(true); set('symbol', '') }
                      else set('symbol', v)
                    }}
                    groups={symbolGroups}
                  />
                )}
                <ErrMsg msg={errors.symbol} />
              </div>
              <div>
                <Label>Market type</Label>
                <Toggle
                  value={form.market_type === 'perpetual'}
                  onChange={v => set('market_type', v ? 'perpetual' : 'spot')}
                  labelOff="Spot"
                  labelOn="Perpetual"
                  colorOn="bg-[#8b5cf6]"
                />
              </div>
            </div>
          </div>

          {/* TRADING */}
          <div>
            <SectionHeader>Trading</SectionHeader>
            <div className="grid grid-cols-2 gap-4">
              <div>
                <Label>Timeframe</Label>
                <Select
                  value={form.timeframe}
                  onChange={v => set('timeframe', v)}
                  options={['1m','5m','15m','30m','1h','4h'].map(t => ({ value: t, label: t }))}
                />
              </div>
              <div>
                <Label>Budget (USD)</Label>
                <Input
                  type="number"
                  value={form.budget_usd}
                  onChange={v => set('budget_usd', Number(v))}
                  min={20}
                  step={10}
                />
                <ErrMsg msg={errors.budget_usd} />
              </div>
              <div className="col-span-2">
                <Label>Mode</Label>
                <div className="flex flex-col gap-1">
                  <Toggle
                    value={form.trading_mode === 'live'}
                    onChange={v => {
                      set('trading_mode', v ? 'live' : 'paper')
                      set('exchange_testnet', v ? 0 : 1)
                    }}
                    labelOff="Paper — trades on testnet with fake money"
                    labelOn="Live — uses real USDC on mainnet"
                    colorOn="bg-[#f97316]"
                  />
                  {form.trading_mode === 'live' && (
                    <div className="flex items-center gap-1 text-[#f97316] text-xs mt-1">
                      <AlertTriangle size={11} />
                      Real money will be used on mainnet!
                    </div>
                  )}
                </div>
              </div>
            </div>
          </div>

          {/* CONFIGURATION */}
          <div>
            <SectionHeader>Configuration</SectionHeader>
            <div className="grid grid-cols-2 gap-4">
              <div>
                <Label>Exchange</Label>
                <Select
                  value={form.exchange}
                  onChange={v => set('exchange', v)}
                  options={[
                    { value: 'dydx', label: 'dYdX' },
                    { value: 'hyperliquid', label: 'Hyperliquid' },
                    { value: 'deribit', label: 'Deribit' },
                  ]}
                />
              </div>
              <div>
                <Label>LLM model</Label>
                <Select
                  value={form.llm_model}
                  onChange={v => set('llm_model', v)}
                  options={[
                    { value: 'claude-sonnet-4-20250514', label: 'Claude Sonnet' },
                    { value: 'claude-haiku-4-5-20251001', label: 'Claude Haiku' },
                  ]}
                />
              </div>
            </div>
          </div>

          {/* ADVANCED SETTINGS (collapsed by default) */}
          <div>
            <button
              type="button"
              onClick={() => setShowAdvanced(v => !v)}
              className="flex items-center gap-2 text-xs font-semibold text-text-muted uppercase tracking-widest py-2 border-b border-[#2d3039] w-full hover:text-text-secondary transition-colors"
            >
              <span className="flex-1 text-left">Advanced Settings</span>
              {showAdvanced ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
            </button>

            {showAdvanced && (
              <div className="mt-3 space-y-4">
                <div className="grid grid-cols-2 gap-4">
                  <div className="col-span-2">
                    <SliderRow
                      label="ATR multiplier"
                      value={form.atr_multiplier}
                      min={0.5}
                      max={3.0}
                      step={0.1}
                      onChange={v => set('atr_multiplier', v)}
                      format={v => v.toFixed(1)}
                    />
                  </div>
                  <div>
                    <Label>ATR length</Label>
                    <Input
                      type="number"
                      value={form.atr_length}
                      onChange={v => set('atr_length', Number(v))}
                      min={7}
                      max={50}
                    />
                  </div>
                  <div>
                    <Label>Forecast candles</Label>
                    <Input
                      type="number"
                      value={form.forecast_candles}
                      onChange={v => set('forecast_candles', Number(v))}
                      min={1}
                      max={10}
                    />
                  </div>
                  <div>
                    <Label>RR ratio min</Label>
                    <Input
                      type="number"
                      value={form.rr_ratio_min}
                      onChange={v => set('rr_ratio_min', Number(v))}
                      step={0.1}
                      min={0.5}
                    />
                    <ErrMsg msg={errors.rr_ratio_min} />
                  </div>
                  <div>
                    <Label>RR ratio max</Label>
                    <Input
                      type="number"
                      value={form.rr_ratio_max}
                      onChange={v => set('rr_ratio_max', Number(v))}
                      step={0.1}
                      min={0.5}
                    />
                  </div>
                  <div>
                    <Label>Max daily loss (USD)</Label>
                    <Input
                      type="number"
                      value={form.max_daily_loss_usd}
                      onChange={v => set('max_daily_loss_usd', Number(v))}
                      min={10}
                      step={10}
                    />
                    <ErrMsg msg={errors.max_daily_loss_usd} />
                  </div>
                  <div>
                    <div className="flex items-center justify-between mb-1">
                      <Label>Max position %</Label>
                      <span className="text-xs font-mono text-accent">
                        {(form.max_position_pct * 100).toFixed(0)}%
                      </span>
                    </div>
                    <input
                      type="range"
                      min={0.1}
                      max={1.0}
                      step={0.05}
                      value={form.max_position_pct}
                      onChange={e => set('max_position_pct', Number(e.target.value))}
                      className="w-full accent-accent"
                    />
                  </div>
                  <div>
                    <Label>Max concurrent positions</Label>
                    <Input
                      type="number"
                      value={form.max_concurrent_positions}
                      onChange={v => set('max_concurrent_positions', Number(v))}
                      min={1}
                      max={5}
                    />
                  </div>
                </div>

                <div>
                  <Label>Agents enabled</Label>
                  <div className="flex gap-4 mt-1">
                    {(['indicator', 'pattern', 'trend'] as const).map(a => (
                      <label key={a} className="flex items-center gap-2 cursor-pointer">
                        <input
                          type="checkbox"
                          checked={agents[a]}
                          onChange={e => setAgents(ag => ({ ...ag, [a]: e.target.checked }))}
                          className="accent-accent"
                        />
                        <span className="text-sm text-text-secondary capitalize">{a}</span>
                      </label>
                    ))}
                  </div>
                  <ErrMsg msg={errors.agents_enabled} />
                </div>
              </div>
            )}
          </div>

          {apiError && (
            <div className="bg-[#ef4444]/10 border border-[#ef4444]/30 rounded-lg px-4 py-3 text-[#ef4444] text-sm">
              {apiError}
            </div>
          )}
        </form>

        {/* Footer */}
        <div className="flex items-center justify-end gap-3 px-6 py-4 border-t border-[#2d3039]">
          <button
            type="button"
            onClick={onClose}
            className="px-4 py-1.5 rounded-md text-sm text-text-secondary hover:text-text-primary hover:bg-bg-elevated transition-colors"
          >
            Cancel
          </button>
          <button
            type="submit"
            form="bot-form"
            disabled={submitting}
            onClick={handleSubmit}
            className="px-5 py-1.5 rounded-md text-sm font-medium bg-accent text-white hover:bg-accent/90 transition-colors disabled:opacity-50"
          >
            {submitting ? 'Saving…' : isEdit ? 'Save changes' : 'Create bot'}
          </button>
        </div>
      </div>
    </div>
  )
}
