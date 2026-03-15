"""AI Usage -- track API costs, tokens, and calls across all AI features.

Displays usage broken down by day, model, and function with a cost trend
chart, filterable tables, and CSV export."""

import sys
from pathlib import Path

import pandas as pd
import streamlit as st

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.ai_usage import (
    get_usage_summary, get_daily_breakdown,
    get_function_breakdown, get_all_calls,
)
from app.style import (
    inject_css, sidebar_logo,
    ACCENT, BG_CARD, BG_CARD_SOLID, BORDER,
    TEXT_PRIMARY, TEXT_SECONDARY, TEXT_DIM,
    GREEN, RED, AMBER,
)

inject_css()
sidebar_logo()

# ---------------------------------------------------------------------------
# Page header + refresh
# ---------------------------------------------------------------------------
header_col, refresh_col = st.columns([6, 1])
with header_col:
    st.markdown(
        f'<h1 style="color: {TEXT_PRIMARY}; font-weight: 600; font-size: 1.8rem; margin-bottom: 0.25rem;">'
        f'AI Usage</h1>'
        f'<p style="color: {TEXT_SECONDARY}; font-size: 0.9rem; margin-bottom: 1.5rem;">'
        f'Token consumption and cost tracking across Claude and DeepSeek</p>',
        unsafe_allow_html=True,
    )
with refresh_col:
    st.markdown("")
    if st.button("Refresh", width="stretch"):
        st.rerun()

summary = get_usage_summary()

if summary["total_calls"] == 0:
    st.info("No AI API calls have been recorded yet.")
    st.stop()

# ---------------------------------------------------------------------------
# Top-level metrics
# ---------------------------------------------------------------------------
PROVIDER_LABELS = {"anthropic": "Claude", "deepseek": "DeepSeek"}
FEATURE_LABELS = {
    "catalog_agent": "Feature Catalog Agent",
    "trade_postmortem": "Trade Post-Mortem",
    "paper_extractor": "Paper Extractor",
    "paper_mapper": "Paper Feature Mapper",
    "paper_generator": "Strategy Code Generator",
}

total_input = sum(p["input_tokens"] for p in summary["by_provider"])
total_output = sum(p["output_tokens"] for p in summary["by_provider"])

col1, col2, col3, col4 = st.columns(4)
col1.metric("Total Cost", f"${summary['total_cost']:.4f}")
col2.metric("Total API Calls", summary["total_calls"])
col3.metric("Input Tokens", f"{total_input:,}")
col4.metric("Output Tokens", f"{total_output:,}")

# Per-provider summary cards
if summary["by_provider"]:
    st.markdown("")
    provider_cols = st.columns(len(summary["by_provider"]))
    for col, p in zip(provider_cols, summary["by_provider"]):
        label = PROVIDER_LABELS.get(p["provider"], p["provider"])
        color = AMBER if p["provider"] == "anthropic" else GREEN
        total_tok = p["input_tokens"] + p["output_tokens"]
        with col:
            st.markdown(
                f'<div style="background: {BG_CARD}; backdrop-filter: blur(12px); '
                f'-webkit-backdrop-filter: blur(12px); border: 1px solid {BORDER}; '
                f'border-radius: 10px; padding: 1rem 1.25rem;">'
                f'<div style="color: {color}; font-weight: 600; font-size: 1rem; '
                f'margin-bottom: 0.5rem;">{label}</div>'
                f'<div style="display: flex; justify-content: space-between; '
                f'margin-bottom: 0.25rem;">'
                f'<span style="color: {TEXT_DIM}; font-size: 0.8rem;">Calls</span>'
                f'<span style="color: {TEXT_PRIMARY}; font-weight: 600;">'
                f'{p["calls"]}</span></div>'
                f'<div style="display: flex; justify-content: space-between; '
                f'margin-bottom: 0.25rem;">'
                f'<span style="color: {TEXT_DIM}; font-size: 0.8rem;">Tokens</span>'
                f'<span style="color: {TEXT_PRIMARY}; font-weight: 500;">'
                f'{total_tok:,}</span></div>'
                f'<div style="display: flex; justify-content: space-between;">'
                f'<span style="color: {TEXT_DIM}; font-size: 0.8rem;">Cost</span>'
                f'<span style="color: {color}; font-weight: 600;">'
                f'${p["cost"]:.4f}</span></div>'
                f'</div>',
                unsafe_allow_html=True,
            )

# ---------------------------------------------------------------------------
# Cost trend chart
# ---------------------------------------------------------------------------
daily = get_daily_breakdown()
if daily:
    st.markdown(
        f'<h3 style="color: {TEXT_PRIMARY}; font-weight: 500; margin-top: 2rem;">'
        f'Cost Trend</h3>',
        unsafe_allow_html=True,
    )
    df_trend = pd.DataFrame(daily)
    # Aggregate cost per day (across providers) for the chart
    df_trend["date"] = pd.to_datetime(df_trend["date"])
    daily_cost = df_trend.groupby("date")["cost"].sum().reset_index()
    daily_cost = daily_cost.set_index("date").sort_index()
    daily_cost.columns = ["Daily Cost ($)"]
    st.area_chart(daily_cost, color=ACCENT, width="stretch", height=220)

# ---------------------------------------------------------------------------
# Tabs for breakdowns
# ---------------------------------------------------------------------------
tab_daily, tab_func, tab_log = st.tabs([
    "Daily Breakdown", "By Function", "Full Call Log",
])

# --- Daily breakdown -------------------------------------------------------
with tab_daily:
    if daily:
        df_daily = pd.DataFrame(daily)
        df_daily["provider"] = df_daily["provider"].map(
            lambda x: PROVIDER_LABELS.get(x, x)
        )
        df_daily["total_tokens"] = df_daily["input_tokens"] + df_daily["output_tokens"]
        st.dataframe(
            df_daily,
            column_config={
                "date": st.column_config.TextColumn("Date"),
                "provider": st.column_config.TextColumn("Provider"),
                "model": st.column_config.TextColumn("Model"),
                "calls": st.column_config.NumberColumn("Calls"),
                "input_tokens": st.column_config.NumberColumn("Input Tokens", format="%d"),
                "output_tokens": st.column_config.NumberColumn("Output Tokens", format="%d"),
                "total_tokens": st.column_config.NumberColumn("Total Tokens", format="%d"),
                "cost": st.column_config.NumberColumn("Cost ($)", format="%.6f"),
            },
            width="stretch",
            hide_index=True,
        )
        csv_daily = pd.DataFrame(daily).to_csv(index=False)
        st.download_button(
            "Export CSV", csv_daily, file_name="ai_usage_daily.csv",
            mime="text/csv",
        )
    else:
        st.caption("No daily data available.")

# --- Function breakdown ----------------------------------------------------
with tab_func:
    func_data = get_function_breakdown()
    if func_data:
        df_func = pd.DataFrame(func_data)
        df_func["feature"] = df_func["feature"].map(
            lambda x: FEATURE_LABELS.get(x, x.replace("_", " ").title())
        )
        df_func["provider"] = df_func["provider"].map(
            lambda x: PROVIDER_LABELS.get(x, x)
        )
        df_func["total_tokens"] = df_func["input_tokens"] + df_func["output_tokens"]
        st.dataframe(
            df_func,
            column_config={
                "feature": st.column_config.TextColumn("Function"),
                "provider": st.column_config.TextColumn("Provider"),
                "model": st.column_config.TextColumn("Model"),
                "calls": st.column_config.NumberColumn("Calls"),
                "input_tokens": st.column_config.NumberColumn("Input Tokens", format="%d"),
                "output_tokens": st.column_config.NumberColumn("Output Tokens", format="%d"),
                "total_tokens": st.column_config.NumberColumn("Total Tokens", format="%d"),
                "cost": st.column_config.NumberColumn("Cost ($)", format="%.6f"),
            },
            width="stretch",
            hide_index=True,
        )
        csv_func = pd.DataFrame(func_data).to_csv(index=False)
        st.download_button(
            "Export CSV", csv_func, file_name="ai_usage_by_function.csv",
            mime="text/csv",
        )
    else:
        st.caption("No function data available.")

# --- Full call log ---------------------------------------------------------
with tab_log:
    all_data = get_all_calls()
    if all_data:
        df_all = pd.DataFrame(all_data)
        df_all["timestamp"] = pd.to_datetime(df_all["timestamp"]).dt.strftime(
            "%Y-%m-%d %H:%M:%S"
        )
        df_all["feature"] = df_all["feature"].map(
            lambda x: FEATURE_LABELS.get(x, x.replace("_", " ").title())
        )
        df_all["provider"] = df_all["provider"].map(
            lambda x: PROVIDER_LABELS.get(x, x)
        )
        df_all["total_tokens"] = df_all["input_tokens"] + df_all["output_tokens"]
        st.dataframe(
            df_all,
            column_config={
                "id": st.column_config.NumberColumn("ID"),
                "timestamp": st.column_config.TextColumn("Timestamp"),
                "provider": st.column_config.TextColumn("Provider"),
                "model": st.column_config.TextColumn("Model"),
                "feature": st.column_config.TextColumn("Function"),
                "input_tokens": st.column_config.NumberColumn("Input Tokens", format="%d"),
                "output_tokens": st.column_config.NumberColumn("Output Tokens", format="%d"),
                "total_tokens": st.column_config.NumberColumn("Total Tokens", format="%d"),
                "cost": st.column_config.NumberColumn("Cost ($)", format="$%.6f"),
            },
            column_order=["id", "timestamp", "provider", "model", "feature",
                          "input_tokens", "output_tokens", "total_tokens", "cost"],
            width="stretch",
            hide_index=True,
        )
        csv_all = pd.DataFrame(all_data).to_csv(index=False)
        st.download_button(
            "Export CSV", csv_all, file_name="ai_usage_full_log.csv",
            mime="text/csv",
        )
    else:
        st.caption("No calls recorded yet.")
