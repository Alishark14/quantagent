"""QuantAgent LangGraph workflow.

Graph structure:
    START → fetch_data → [indicator, pattern, trend] (parallel) → risk_decision → execute → END
"""

import logging

from langgraph.graph import StateGraph, START, END

from state import QuantAgentState
from utils.data import fetch_data_node
from agents.indicator import indicator_agent_node
from agents.pattern import pattern_agent_node
from agents.trend import trend_agent_node
from agents.risk_decision import risk_decision_agent_node
from execution import execute_trade_node, log_trade

logger = logging.getLogger(__name__)


def post_trade_node(state: dict) -> dict:
    """Log the trade after execution."""
    trade_result = state.get("trade_result", {})
    decision = state.get("decision", {})
    log_trade(trade_result, decision)
    return {}


def build_graph(execute_trades: bool = True) -> StateGraph:
    """Build and compile the QuantAgent graph.

    Args:
        execute_trades: If True, include the trade execution node.
                       Set to False for dry-run / analysis-only mode.

    Returns:
        Compiled LangGraph graph.
    """
    graph = StateGraph(QuantAgentState)

    # --- Add nodes ---
    graph.add_node("fetch_data", fetch_data_node)
    graph.add_node("indicator_agent", indicator_agent_node)
    graph.add_node("pattern_agent", pattern_agent_node)
    graph.add_node("trend_agent", trend_agent_node)
    graph.add_node("risk_decision", risk_decision_agent_node)

    if execute_trades:
        graph.add_node("execute_trade", execute_trade_node)
        graph.add_node("post_trade", post_trade_node)

    # --- Add edges ---

    # START → fetch data
    graph.add_edge(START, "fetch_data")

    # fetch_data → three parallel analysis agents (fan-out)
    graph.add_edge("fetch_data", "indicator_agent")
    graph.add_edge("fetch_data", "pattern_agent")
    graph.add_edge("fetch_data", "trend_agent")

    # Three agents → risk_decision (fan-in)
    graph.add_edge("indicator_agent", "risk_decision")
    graph.add_edge("pattern_agent", "risk_decision")
    graph.add_edge("trend_agent", "risk_decision")

    if execute_trades:
        # risk_decision → execute → post_trade → END
        graph.add_edge("risk_decision", "execute_trade")
        graph.add_edge("execute_trade", "post_trade")
        graph.add_edge("post_trade", END)
    else:
        graph.add_edge("risk_decision", END)

    return graph.compile()


def run_analysis(
    symbol: str = "BTCUSDT",
    timeframe: str = "1h",
    execute_trades: bool = True,
) -> dict:
    """Run a single analysis cycle.

    Args:
        symbol: Trading pair.
        timeframe: Candle interval.
        execute_trades: Whether to place orders on testnet.

    Returns:
        Final state dict with all reports and decision.
    """
    graph = build_graph(execute_trades=execute_trades)

    initial_state = {
        "symbol": symbol,
        "timeframe": timeframe,
        "ohlc_data": [],
        "indicator_report": "",
        "pattern_report": "",
        "trend_report": "",
        "indicator_values": {},
        "trend_params": {},
        "chart_pattern_img": "",
        "chart_trend_img": "",
        "decision": {},
        "trade_result": {},
        "indicator_signal": "neutral",
        "pattern_signal": "neutral",
        "trend_signal": "neutral",
        "position_size": 0.0,
        "sizing_details": {},
        "indicator_usage": {},
        "pattern_usage": {},
        "trend_usage": {},
        "decision_usage": {},
    }

    logger.info(f"=== QuantAgent cycle: {symbol} / {timeframe} ===")
    result = graph.invoke(
        initial_state,
        config={
            "run_name": f"QuantAgent_{symbol}_{timeframe}",
            "tags": [symbol, timeframe, "live" if execute_trades else "dry_run"],
            "metadata": {
                "symbol": symbol,
                "timeframe": timeframe,
                "mode": "live" if execute_trades else "dry_run",
            },
        },
    )
    logger.info(f"=== Cycle complete: {result.get('decision', {}).get('decision', 'N/A')} ===")

    return result
