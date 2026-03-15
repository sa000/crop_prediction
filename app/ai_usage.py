"""AI usage tracking for Anthropic and DeepSeek API calls.

Logs token counts and estimated costs to SQLite. Provides query
helpers for the dedicated AI Usage dashboard page."""

import logging
import sqlite3
from datetime import datetime, timezone

from etl.db import get_app_connection, init_app_tables

logger = logging.getLogger(__name__)

# Pricing per 1M tokens (USD)
PRICING = {
    "claude-haiku-4-5-20251001": {"input": 1.00, "output": 5.00},
    "deepseek-chat": {"input": 0.28, "output": 0.42},
}


def _estimate_cost(model: str, input_tokens: int, output_tokens: int) -> float:
    """Compute estimated cost in USD from token counts and model pricing."""
    rates = PRICING.get(model, {"input": 0.0, "output": 0.0})
    return (input_tokens * rates["input"] + output_tokens * rates["output"]) / 1_000_000


def log_usage(
    provider: str,
    model: str,
    feature: str,
    input_tokens: int,
    output_tokens: int,
    duration_s: float | None = None,
) -> None:
    """Write one usage record to the database.

    Args:
        provider: 'anthropic' or 'deepseek'.
        model: Model ID string.
        feature: Which app feature triggered the call (e.g. 'trade_postmortem').
        input_tokens: Number of input/prompt tokens.
        output_tokens: Number of output/completion tokens.
        duration_s: Wall-clock seconds the API call took (optional).
    """
    cost = _estimate_cost(model, input_tokens, output_tokens)
    now = datetime.now(timezone.utc).isoformat()

    try:
        conn = get_app_connection()
        init_app_tables(conn)
        conn.execute(
            "INSERT INTO ai_usage (timestamp, provider, model, feature, "
            "input_tokens, output_tokens, cost_usd, duration_s) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (now, provider, model, feature, input_tokens, output_tokens,
             cost, duration_s),
        )
        conn.commit()
        conn.close()
        logger.debug(
            "Logged AI usage: %s/%s %d in + %d out = $%.6f (%.1fs)",
            provider, model, input_tokens, output_tokens, cost,
            duration_s or 0,
        )
    except Exception:
        logger.exception("Failed to log AI usage")


def get_usage_summary() -> dict:
    """Query aggregated usage stats for the dashboard.

    Returns:
        Dict with keys: total_cost, total_calls, by_provider, by_feature, recent.
    """
    try:
        conn = get_app_connection()
        init_app_tables(conn)
        cur = conn.cursor()

        cur.execute("SELECT COUNT(*), COALESCE(SUM(cost_usd), 0) FROM ai_usage")
        total_calls, total_cost = cur.fetchone()

        cur.execute(
            "SELECT provider, COUNT(*) as calls, "
            "SUM(input_tokens) as inp, SUM(output_tokens) as out, "
            "SUM(cost_usd) as cost FROM ai_usage GROUP BY provider"
        )
        by_provider = [
            {"provider": r[0], "calls": r[1], "input_tokens": r[2],
             "output_tokens": r[3], "cost": r[4]}
            for r in cur.fetchall()
        ]

        cur.execute(
            "SELECT feature, provider, COUNT(*) as calls, "
            "SUM(cost_usd) as cost FROM ai_usage GROUP BY feature, provider"
        )
        by_feature = [
            {"feature": r[0], "provider": r[1], "calls": r[2], "cost": r[3]}
            for r in cur.fetchall()
        ]

        cur.execute(
            "SELECT timestamp, provider, model, feature, "
            "input_tokens, output_tokens, cost_usd "
            "FROM ai_usage ORDER BY id DESC LIMIT 20"
        )
        recent = [
            {"timestamp": r[0], "provider": r[1], "model": r[2],
             "feature": r[3], "input_tokens": r[4], "output_tokens": r[5],
             "cost": r[6]}
            for r in cur.fetchall()
        ]

        conn.close()
        return {
            "total_cost": total_cost,
            "total_calls": total_calls,
            "by_provider": by_provider,
            "by_feature": by_feature,
            "recent": recent,
        }
    except Exception:
        logger.exception("Failed to query AI usage")
        return {
            "total_cost": 0.0,
            "total_calls": 0,
            "by_provider": [],
            "by_feature": [],
            "recent": [],
        }


def get_daily_breakdown() -> list[dict]:
    """Return usage aggregated by date and model.

    Returns:
        List of dicts with keys: date, provider, model, calls,
        input_tokens, output_tokens, cost.
    """
    try:
        conn = get_app_connection()
        init_app_tables(conn)
        cur = conn.cursor()
        cur.execute(
            "SELECT DATE(timestamp) as day, provider, model, "
            "COUNT(*) as calls, "
            "SUM(input_tokens) as inp, SUM(output_tokens) as out, "
            "SUM(cost_usd) as cost "
            "FROM ai_usage GROUP BY day, provider, model "
            "ORDER BY day DESC, provider"
        )
        rows = [
            {"date": r[0], "provider": r[1], "model": r[2], "calls": r[3],
             "input_tokens": r[4], "output_tokens": r[5], "cost": r[6]}
            for r in cur.fetchall()
        ]
        conn.close()
        return rows
    except Exception:
        logger.exception("Failed to query daily breakdown")
        return []


def get_function_breakdown() -> list[dict]:
    """Return usage aggregated by feature (function) and model.

    Returns:
        List of dicts with keys: feature, provider, model, calls,
        input_tokens, output_tokens, cost.
    """
    try:
        conn = get_app_connection()
        init_app_tables(conn)
        cur = conn.cursor()
        cur.execute(
            "SELECT feature, provider, model, "
            "COUNT(*) as calls, "
            "SUM(input_tokens) as inp, SUM(output_tokens) as out, "
            "SUM(cost_usd) as cost, "
            "AVG(duration_s) as avg_dur "
            "FROM ai_usage GROUP BY feature, provider, model "
            "ORDER BY cost DESC"
        )
        rows = [
            {"feature": r[0], "provider": r[1], "model": r[2], "calls": r[3],
             "input_tokens": r[4], "output_tokens": r[5], "cost": r[6],
             "avg_duration_s": r[7]}
            for r in cur.fetchall()
        ]
        conn.close()
        return rows
    except Exception:
        logger.exception("Failed to query function breakdown")
        return []


def get_all_calls() -> list[dict]:
    """Return every individual API call record, most recent first.

    Returns:
        List of dicts with keys: id, timestamp, provider, model, feature,
        input_tokens, output_tokens, cost.
    """
    try:
        conn = get_app_connection()
        init_app_tables(conn)
        cur = conn.cursor()
        cur.execute(
            "SELECT id, timestamp, provider, model, feature, "
            "input_tokens, output_tokens, cost_usd, duration_s "
            "FROM ai_usage ORDER BY id DESC"
        )
        rows = [
            {"id": r[0], "timestamp": r[1], "provider": r[2], "model": r[3],
             "feature": r[4], "input_tokens": r[5], "output_tokens": r[6],
             "cost": r[7], "duration_s": r[8]}
            for r in cur.fetchall()
        ]
        conn.close()
        return rows
    except Exception:
        logger.exception("Failed to query all calls")
        return []


def get_avg_durations() -> dict[str, float]:
    """Return average duration in seconds for each feature that has duration data.

    Returns:
        Dict mapping feature name to average duration_s.
    """
    try:
        conn = get_app_connection()
        init_app_tables(conn)
        cur = conn.cursor()
        cur.execute(
            "SELECT feature, AVG(duration_s) "
            "FROM ai_usage WHERE duration_s IS NOT NULL "
            "GROUP BY feature"
        )
        result = {r[0]: r[1] for r in cur.fetchall()}
        conn.close()
        return result
    except Exception:
        logger.exception("Failed to query avg durations")
        return {}
