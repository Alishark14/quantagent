import type {
  AgentsData,
  Bot,
  BotCreate,
  BreakdownResponse,
  ConfigData,
  ExitsData,
  OverviewData,
  TradeRecord,
  TradesResponse,
} from '../types'

const BASE_URL = 'http://localhost:8001'

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
  overview: (botId?: string) => {
    const q = botId ? `?bot_id=${botId}` : ''
    return get<OverviewData>(`/api/overview${q}`)
  },

  trades: (params?: {
    limit?: number
    offset?: number
    symbol?: string
    direction?: string
    exit_type?: string
    botId?: string
  }) => {
    const q = new URLSearchParams()
    if (params?.limit !== undefined) q.set('limit', String(params.limit))
    if (params?.offset !== undefined) q.set('offset', String(params.offset))
    if (params?.symbol) q.set('symbol', params.symbol)
    if (params?.direction) q.set('direction', params.direction)
    if (params?.exit_type) q.set('exit_type', params.exit_type)
    if (params?.botId) q.set('bot_id', params.botId)
    return get<TradesResponse>(`/api/trades?${q}`)
  },

  agents: (botId?: string) => {
    const q = botId ? `?bot_id=${botId}` : ''
    return get<AgentsData>(`/api/agents${q}`)
  },

  breakdown: (dimension: 'asset' | 'timeframe' | 'direction', botId?: string) => {
    const q = new URLSearchParams({ dimension })
    if (botId) q.set('bot_id', botId)
    return get<BreakdownResponse>(`/api/breakdown?${q}`)
  },

  exits: (botId?: string) => {
    const q = botId ? `?bot_id=${botId}` : ''
    return get<ExitsData>(`/api/exits${q}`)
  },

  config: () => get<ConfigData>('/api/config'),

  health: () => get<{ status: string }>('/api/health'),

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
}
