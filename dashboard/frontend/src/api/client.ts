import type {
  AgentsData,
  ApiCostData,
  Bot,
  BotCreate,
  BreakdownResponse,
  ConfigData,
  ExchangeStatus,
  ExitsData,
  HealthData,
  LiveOrder,
  LivePosition,
  OverviewData,
  TradeRecord,
  TradesResponse,
} from '../types'

const BASE_URL = ''

export const getWsUrl = (path: string): string => {
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
  const host = window.location.host
  return `${protocol}//${host}${path}`
}

async function get<T>(path: string): Promise<T> {
  const res = await fetch(`${BASE_URL}${path}`)
  if (!res.ok) throw new Error(`API error ${res.status}: ${path}`)
  return res.json()
}

async function post<T>(path: string, body?: unknown): Promise<T> {
  const res = await fetch(`${BASE_URL}${path}`, {
    method: 'POST',
    headers: body !== undefined ? { 'Content-Type': 'application/json' } : {},
    body: body !== undefined ? JSON.stringify(body) : undefined,
  })
  if (!res.ok) {
    const detail = await res.json().catch(() => ({ detail: res.statusText }))
    throw new Error(detail.detail ?? `API error ${res.status}: ${path}`)
  }
  return res.json()
}

async function put<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(`${BASE_URL}${path}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  if (!res.ok) {
    const detail = await res.json().catch(() => ({ detail: res.statusText }))
    throw new Error(detail.detail ?? `API error ${res.status}: ${path}`)
  }
  return res.json()
}

async function del<T>(path: string): Promise<T> {
  const res = await fetch(`${BASE_URL}${path}`, { method: 'DELETE' })
  if (!res.ok) {
    const detail = await res.json().catch(() => ({ detail: res.statusText }))
    throw new Error(detail.detail ?? `API error ${res.status}: ${path}`)
  }
  return res.json()
}

export const api = {
  // ── Performance analytics ──────────────────────────────────────────────────
  overview: (botId?: string, mode?: string) => {
    const q = new URLSearchParams()
    if (botId) q.set('bot_id', botId)
    if (mode && mode !== 'all') q.set('mode', mode)
    const qs = q.toString()
    return get<OverviewData>(`/api/overview${qs ? `?${qs}` : ''}`)
  },

  trades: (params?: {
    limit?: number
    offset?: number
    symbol?: string
    direction?: string
    exit_type?: string
    bot_name?: string
    botId?: string
    mode?: string
    status?: string
  }) => {
    const q = new URLSearchParams()
    if (params?.limit !== undefined) q.set('limit', String(params.limit))
    if (params?.offset !== undefined) q.set('offset', String(params.offset))
    if (params?.symbol) q.set('symbol', params.symbol)
    if (params?.direction) q.set('direction', params.direction)
    if (params?.exit_type) q.set('exit_type', params.exit_type)
    if (params?.bot_name) q.set('bot_name', params.bot_name)
    if (params?.botId) q.set('bot_id', params.botId)
    if (params?.mode && params.mode !== 'all') q.set('mode', params.mode)
    if (params?.status) q.set('status', params.status)
    return get<TradesResponse>(`/api/trades?${q}`)
  },

  agents: (botId?: string, mode?: string) => {
    const q = new URLSearchParams()
    if (botId) q.set('bot_id', botId)
    if (mode && mode !== 'all') q.set('mode', mode)
    const qs = q.toString()
    return get<AgentsData>(`/api/agents${qs ? `?${qs}` : ''}`)
  },

  breakdown: (dimension: string, botId?: string, mode?: string) => {
    const q = new URLSearchParams({ dimension })
    if (botId) q.set('bot_id', botId)
    if (mode && mode !== 'all') q.set('mode', mode)
    return get<BreakdownResponse>(`/api/breakdown?${q}`)
  },

  exits: (botId?: string, mode?: string) => {
    const q = new URLSearchParams()
    if (botId) q.set('bot_id', botId)
    if (mode && mode !== 'all') q.set('mode', mode)
    const qs = q.toString()
    return get<ExitsData>(`/api/exits${qs ? `?${qs}` : ''}`)
  },

  config: () => get<ConfigData>('/api/config'),

  health: () => get<HealthData>('/api/health'),

  exchangeStatus: () => get<ExchangeStatus[]>('/api/settings/exchanges'),

  apiCosts: (botId?: string, days?: number, mode?: string) => {
    const q = new URLSearchParams()
    if (botId) q.set('bot_id', botId)
    if (days !== undefined) q.set('days', String(days))
    if (mode && mode !== 'all') q.set('mode', mode)
    const qs = q.toString()
    return get<ApiCostData>(`/api/stats/api-costs${qs ? `?${qs}` : ''}`)
  },

  // ── Bot CRUD ───────────────────────────────────────────────────────────────
  getBots: () => get<Bot[]>('/api/bots'),

  getBot: (id: string) => get<Bot>(`/api/bots/${id}`),

  createBot: (config: BotCreate) => post<Bot>('/api/bots', config),

  updateBot: (id: string, updates: Partial<BotCreate>) =>
    put<Bot>(`/api/bots/${id}`, updates),

  deleteBot: (id: string) => del<{ ok: boolean }>(`/api/bots/${id}`),

  // ── Bot lifecycle ──────────────────────────────────────────────────────────
  startBot: (id: string) => post<Bot>(`/api/bots/${id}/start`),

  stopBot: (id: string) => post<Bot>(`/api/bots/${id}/stop`),

  restartBot: (id: string) => post<Bot>(`/api/bots/${id}/restart`),

  pauseBot: (id: string) => post<Bot>(`/api/bots/${id}/pause`),

  killAllBots: () => post<{ ok: boolean; message: string }>('/api/bots/kill-all'),

  // ── Bot trades ─────────────────────────────────────────────────────────────
  getBotTrades: (id: string, limit = 50, offset = 0) =>
    get<TradeRecord[]>(`/api/bots/${id}/trades?limit=${limit}&offset=${offset}`),

  // ── Stats ──────────────────────────────────────────────────────────────────
  dailyPnl: (mode?: string) => {
    const q = new URLSearchParams()
    if (mode && mode !== 'all') q.set('mode', mode)
    const qs = q.toString()
    return get<Record<string, number>>(`/api/stats/daily-pnl${qs ? `?${qs}` : ''}`)
  },

  // ── Symbol catalogue ──────────────────────────────────────────────────────
  getAvailableSymbols: () =>
    get<{ value: string; label: string; ccxt: string; category: string }[]>('/api/symbols'),

  // ── Live exchange data ─────────────────────────────────────────────────────
  getPositions: () => get<LivePosition[]>('/api/positions'),

  getOrders: () => get<LiveOrder[]>('/api/orders'),

  // ── Guardian ───────────────────────────────────────────────────────────────
  guardianStatus: () =>
    get<{ active: boolean; orphan_tracker: Record<string, string> }>('/api/guardian/status'),

  // ── Emergency ──────────────────────────────────────────────────────────────
  closeAllPositions: () =>
    post<{ closed: number; failed: number; orders_cancelled: number }>(
      '/api/emergency/close-all-positions'
    ),
}
