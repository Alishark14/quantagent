export interface EquityPoint {
  timestamp: string
  cumulative_pnl: number
}

export interface OverviewData {
  total_trades: number
  wins: number
  losses: number
  win_rate: number
  total_pnl: number
  profit_factor: number
  expectancy: number
  max_drawdown: number
  sharpe_ratio: number
  avg_hold_time: string
  trades_today: number
  equity_curve: EquityPoint[]
}

export interface TradeRecord {
  timestamp: string
  symbol: string
  direction: 'LONG' | 'SHORT'
  entry_price: number
  stop_loss: number
  take_profit: number
  exit_price: number | null
  pnl: number
  pnl_pct: number
  exit_type: 'tp' | 'sl' | 'time' | 'unknown'
  rr_ratio: number
  atr_value: number | null
  sl_distance: number | null
  justification: string
  order_id: string
  status: string
  estimated: boolean
  agreement_level: string
}

export interface TradesResponse {
  trades: TradeRecord[]
  total: number
  offset: number
  limit: number
}

export interface AgentStat {
  total_signals: number
  correct_signals: number
  accuracy_pct: number
}

export interface AgreementRow {
  agreement_level: string
  count: number
  win_rate: number
}

export interface AgentsData {
  agents: {
    indicator: AgentStat
    pattern: AgentStat
    trend: AgentStat
  }
  agreement_data: AgreementRow[]
}

export interface BreakdownRow {
  group: string
  trades: number
  wins: number
  losses: number
  win_rate: number
  avg_pnl: number
  total_pnl: number
}

export interface BreakdownResponse {
  dimension: string
  data: BreakdownRow[]
}

export interface ExitsData {
  tp_count: number
  sl_count: number
  time_count: number
  unknown_count: number
  tp_pct: number
  sl_pct: number
  time_pct: number
}

export interface ConfigData {
  atr_length: number
  atr_multiplier: number
  forecast_candles: number
  lookback_bars: number
  symbol: string
  timeframe: string
  model_name: string
  langsmith_enabled: boolean
  langsmith_project: string
  data_exchange: string
}

export interface Bot {
  id: string
  name: string
  symbol: string
  market_type: 'perpetual' | 'spot'
  timeframe: string
  budget_usd: number
  max_concurrent_positions: number
  trading_mode: 'paper' | 'live'
  atr_multiplier: number
  atr_length: number
  rr_ratio_min: number
  rr_ratio_max: number
  max_daily_loss_usd: number
  max_position_pct: number
  forecast_candles: number
  agents_enabled: string
  llm_model: string
  exchange: string
  exchange_testnet: number
  status: 'running' | 'paused' | 'stopped' | 'error'
  pid: number | null
  last_heartbeat: string | null
  last_error: string | null
  consecutive_losses: number
  daily_loss_usd: number
  created_at: string
  updated_at: string
}

export interface BotCreate {
  name: string
  symbol: string
  market_type?: string
  timeframe?: string
  budget_usd?: number
  max_concurrent_positions?: number
  trading_mode?: string
  atr_multiplier?: number
  atr_length?: number
  rr_ratio_min?: number
  rr_ratio_max?: number
  max_daily_loss_usd?: number
  max_position_pct?: number
  forecast_candles?: number
  agents_enabled?: string
  llm_model?: string
  exchange?: string
  exchange_testnet?: number
}
