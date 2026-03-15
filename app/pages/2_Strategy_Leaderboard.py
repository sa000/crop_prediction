"""Strategy Leaderboard -- persistent history of all backtest runs.

Browse, filter, sort, star, and drill into every backtest run across all
strategies and tickers. Click View to rehydrate the full Strategy Backtester
with saved results."""

import sys
from pathlib import Path

import streamlit as st

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

st.set_page_config(
    page_title="Leaderboard | Cortex",
    page_icon=str(PROJECT_ROOT / "brain.png"),
    layout="wide",
)

from app.style import (
    inject_css, sidebar_logo,
    ACCENT, BG_CARD, BORDER,
    TEXT_PRIMARY, TEXT_SECONDARY, TEXT_DIM,
    GREEN, RED, AMBER, BADGE,
)
from etl.db import (
    get_app_connection, init_app_tables,
    list_backtest_runs, update_backtest_run_star,
    update_backtest_run_notes,
)

inject_css()
sidebar_logo(PROJECT_ROOT)

# ---------------------------------------------------------------------------
# Page header
# ---------------------------------------------------------------------------
st.markdown(
    f'<h1 style="font-weight: 600; font-size: 1.8rem; color: {TEXT_PRIMARY};">'
    f'Strategy Leaderboard</h1>',
    unsafe_allow_html=True,
)

# ---------------------------------------------------------------------------
# Sidebar filters
# ---------------------------------------------------------------------------
conn = get_app_connection()
init_app_tables(conn)

# Get distinct strategy names for the filter
all_runs_raw = list_backtest_runs(conn, limit=500)
strategy_names = sorted({r["strategy_name"] for r in all_runs_raw})

st.sidebar.markdown("---")

filter_strategy = st.sidebar.selectbox(
    "Strategy", ["All"] + strategy_names,
)
filter_ticker = st.sidebar.selectbox(
    "Ticker", ["All", "Corn", "Soybeans", "Wheat"],
)
filter_starred = st.sidebar.checkbox("Starred only")

SORT_OPTIONS = {
    "Date": "created_at",
    "Sharpe": "sharpe_ratio",
    "P&L": "total_pnl",
    "Max DD": "max_drawdown_pct",
    "Win Rate": "win_rate",
}
sort_label = st.sidebar.selectbox("Sort by", list(SORT_OPTIONS.keys()))
sort_col = SORT_OPTIONS[sort_label]
sort_order = st.sidebar.radio("Order", ["Desc", "Asc"], horizontal=True)

# ---------------------------------------------------------------------------
# Query runs
# ---------------------------------------------------------------------------
TICKER_NAME_TO_SYMBOL = {"Corn": "ZC=F", "Soybeans": "ZS=F", "Wheat": "ZW=F"}

runs = list_backtest_runs(
    conn,
    strategy_name=filter_strategy if filter_strategy != "All" else None,
    ticker=TICKER_NAME_TO_SYMBOL.get(filter_ticker) if filter_ticker != "All" else None,
    starred_only=filter_starred,
    sort_by=sort_col,
    sort_order=sort_order.upper(),
    limit=200,
)

# ---------------------------------------------------------------------------
# Summary stats
# ---------------------------------------------------------------------------
if runs:
    best_sharpe = max((r["sharpe_ratio"] or 0) for r in runs)
    best_pnl = max((r["total_pnl"] or 0) for r in runs)
    avg_wr = sum((r["win_rate"] or 0) for r in runs) / len(runs)

    s1, s2, s3, s4 = st.columns(4)
    s1.metric("Total Runs", len(runs))
    s2.metric("Best Sharpe", f"{best_sharpe:.2f}")

    def _fmt_dollar(v):
        if abs(v) >= 1e6:
            return f"${v / 1e6:.2f}M"
        if abs(v) >= 1e3:
            return f"${v / 1e3:.0f}K"
        return f"${v:,.0f}"

    s3.metric("Best P&L", _fmt_dollar(best_pnl))
    s4.metric("Avg Win Rate", f"{avg_wr:.1%}")
else:
    st.info("No backtest runs yet. Run a backtest from the Strategy Backtester to get started.")
    conn.close()
    st.stop()

# ---------------------------------------------------------------------------
# Leaderboard cards
# ---------------------------------------------------------------------------
st.markdown("")

for rank, run in enumerate(runs, 1):
    run_id = run["id"]
    sharpe = run["sharpe_ratio"] or 0
    pnl = run["total_pnl"] or 0
    max_dd = run["max_drawdown_pct"] or 0
    win_rate = run["win_rate"] or 0
    trades = run["num_trades"] or 0
    is_starred = bool(run["starred"])

    star_icon = "★" if is_starred else ""
    pnl_color = GREEN if pnl >= 0 else RED
    sharpe_color = GREEN if sharpe >= 1 else (AMBER if sharpe >= 0 else RED)

    # Card HTML
    st.markdown(
        f'<div style="background: {BG_CARD}; backdrop-filter: blur(12px); '
        f'-webkit-backdrop-filter: blur(12px); border: 1px solid {BORDER}; '
        f'border-radius: 10px; padding: 1rem 1.25rem; margin-bottom: 0.5rem;">'

        # Header row
        f'<div style="display: flex; align-items: center; gap: 0.5rem; '
        f'margin-bottom: 0.75rem;">'
        f'<span style="color: {TEXT_DIM}; font-size: 0.85rem; font-weight: 600; '
        f'min-width: 28px;">#{rank}</span>'
        f'<span style="color: {TEXT_PRIMARY}; font-weight: 600; font-size: 1rem;">'
        f'{run["strategy_name"]}</span>'
        f'<span style="color: {TEXT_SECONDARY}; font-size: 0.82rem; '
        f'margin-left: 0.5rem;">{run["ticker_name"]}</span>'
        f'<span style="background: {ACCENT}18; color: {BADGE}; '
        f'font-size: 0.72rem; font-weight: 600; padding: 0.15rem 0.5rem; '
        f'border-radius: 4px; margin-left: 0.5rem;">{run["run_by"]}</span>'
        f'<span style="color: {AMBER}; margin-left: auto;">{star_icon}</span>'
        f'</div>'

        # Metrics row
        f'<div style="display: flex; gap: 1.5rem; flex-wrap: wrap; margin-bottom: 0.5rem;">'
        f'<div><div style="color: {TEXT_DIM}; font-size: 0.72rem;">Sharpe</div>'
        f'<div style="color: {sharpe_color}; font-size: 1.05rem; font-weight: 600;">'
        f'{sharpe:.2f}</div></div>'
        f'<div><div style="color: {TEXT_DIM}; font-size: 0.72rem;">P&L</div>'
        f'<div style="color: {pnl_color}; font-size: 1.05rem; font-weight: 600;">'
        f'{_fmt_dollar(pnl)}</div></div>'
        f'<div><div style="color: {TEXT_DIM}; font-size: 0.72rem;">Max DD</div>'
        f'<div style="color: {TEXT_PRIMARY}; font-size: 1.05rem; font-weight: 600;">'
        f'{max_dd:.3f}%</div></div>'
        f'<div><div style="color: {TEXT_DIM}; font-size: 0.72rem;">Win Rate</div>'
        f'<div style="color: {TEXT_PRIMARY}; font-size: 1.05rem; font-weight: 600;">'
        f'{win_rate:.1%}</div></div>'
        f'<div><div style="color: {TEXT_DIM}; font-size: 0.72rem;">Trades</div>'
        f'<div style="color: {TEXT_PRIMARY}; font-size: 1.05rem; font-weight: 600;">'
        f'{trades}</div></div>'
        f'</div>'

        # Footer
        f'<div style="color: {TEXT_DIM}; font-size: 0.75rem;">'
        f'{run["date_range_start"] or "?"} to {run["date_range_end"] or "?"}'
        f' &nbsp;&bull;&nbsp; Run on {run["created_at"][:16].replace("T", " at ")}</div>'
        f'</div>',
        unsafe_allow_html=True,
    )

    # Action buttons
    col_view, col_star, col_notes = st.columns([1, 1, 3])

    with col_view:
        if st.button("View", key=f"view_{run_id}", width="stretch"):
            st.session_state["leaderboard_run_id"] = run_id
            st.switch_page("pages/1_Strategy_Backtester.py")

    with col_star:
        star_label = "Unstar" if is_starred else "Star"
        if st.button(star_label, key=f"star_{run_id}", width="stretch"):
            update_backtest_run_star(conn, run_id, 0 if is_starred else 1)
            st.rerun()

    with col_notes:
        with st.expander("Notes", expanded=False):
            current_notes = run.get("notes", "") or ""
            new_notes = st.text_area(
                "Notes", value=current_notes,
                key=f"notes_input_{run_id}",
                label_visibility="collapsed",
                height=80,
            )
            if st.button("Save Notes", key=f"save_notes_{run_id}"):
                update_backtest_run_notes(conn, run_id, new_notes)
                st.rerun()

conn.close()
