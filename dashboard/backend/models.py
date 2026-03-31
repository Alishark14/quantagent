"""Pydantic models for API responses."""

from typing import Optional
from pydantic import BaseModel


class EquityPoint(BaseModel):
    timestamp: str
    cumulative_pnl: float


class OverviewResponse(BaseModel):
    total_trades: int
    wins: int
    losses: int
    win_rate: float
    total_pnl: float
    profit_factor: float
    expectancy: float
    max_drawdown: float
    sharpe_ratio: float
    avg_hold_time: str
    trades_today: int
    equity_curve: list[EquityPoint]


class TradeRecord(BaseModel):
    timestamp: str
    symbol: str
    direction: str
    entry_price: float
    stop_loss: float
    take_profit: float
    exit_price: Optional[float] = None
    pnl: float
    pnl_pct: float
    exit_type: str
    rr_ratio: float
    atr_value: Optional[float] = None
    sl_distance: Optional[float] = None
    justification: str
    order_id: str
    status: str
    estimated: bool
    agreement_level: str


class TradesResponse(BaseModel):
    trades: list[TradeRecord]
    total: int
    offset: int
    limit: int


class AgentStat(BaseModel):
    total_signals: int
    correct_signals: int
    accuracy_pct: float


class AgreementRow(BaseModel):
    agreement_level: str
    count: int
    win_rate: float


class AgentsResponse(BaseModel):
    agents: dict[str, AgentStat]
    agreement_data: list[AgreementRow]


class BreakdownRow(BaseModel):
    group: str
    trades: int
    wins: int
    losses: int
    win_rate: float
    avg_pnl: float
    total_pnl: float


class ExitsResponse(BaseModel):
    tp_count: int
    sl_count: int
    time_count: int
    unknown_count: int
    tp_pct: float
    sl_pct: float
    time_pct: float


class ConfigResponse(BaseModel):
    atr_length: int
    atr_multiplier: float
    forecast_candles: int
    lookback_bars: int
    symbol: str
    timeframe: str
    model_name: str
    langsmith_enabled: bool
    langsmith_project: str
    data_exchange: str


# ── Bot models ────────────────────────────────────────────────────────────────

class BotCreate(BaseModel):
    name: str
    symbol: str
    market_type: str = "perpetual"
    timeframe: str = "1h"
    budget_usd: float = 500
    max_concurrent_positions: int = 3
    trading_mode: str = "paper"
    atr_multiplier: float = 1.5
    atr_length: int = 14
    rr_ratio_min: float = 1.2
    rr_ratio_max: float = 1.8
    max_daily_loss_usd: float = 100
    max_position_pct: float = 0.5
    forecast_candles: int = 3
    agents_enabled: str = "indicator,pattern,trend"
    llm_model: str = "claude-sonnet-4-20250514"
    exchange: str = "deribit"
    exchange_testnet: int = 1


class BotUpdate(BaseModel):
    name: Optional[str] = None
    timeframe: Optional[str] = None
    budget_usd: Optional[float] = None
    max_concurrent_positions: Optional[int] = None
    trading_mode: Optional[str] = None
    atr_multiplier: Optional[float] = None
    atr_length: Optional[int] = None
    rr_ratio_min: Optional[float] = None
    rr_ratio_max: Optional[float] = None
    max_daily_loss_usd: Optional[float] = None
    max_position_pct: Optional[float] = None
    forecast_candles: Optional[int] = None
    agents_enabled: Optional[str] = None
    llm_model: Optional[str] = None
    exchange: Optional[str] = None
    exchange_testnet: Optional[int] = None


class BotResponse(BaseModel):
    id: str
    name: str
    symbol: str
    market_type: str
    timeframe: str
    budget_usd: float
    max_concurrent_positions: int
    trading_mode: str
    atr_multiplier: float
    atr_length: int
    rr_ratio_min: float
    rr_ratio_max: float
    max_daily_loss_usd: float
    max_position_pct: float
    forecast_candles: int
    agents_enabled: str
    llm_model: str
    exchange: str
    exchange_testnet: int
    status: str
    pid: Optional[int] = None
    last_heartbeat: Optional[str] = None
    last_error: Optional[str] = None
    consecutive_losses: int
    daily_loss_usd: float
    created_at: str
    updated_at: str
