"""The Cortex -- Streamlit entry point.

Configures page layout, applies dark theme styling, and renders the
landing page with TREXQUANT branding plus clickable quick-nav cards."""

import sys
from pathlib import Path

import streamlit as st

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import base64

from app.style import (
    inject_css, sidebar_logo,
    ACCENT, BG_CARD, BG_CARD_HOVER, BG_CARD_SOLID, BORDER, BORDER_SUBTLE,
    TEXT_PRIMARY, TEXT_SECONDARY, TEXT_DIM, TEXT_FAINT,
)

st.set_page_config(
    page_title="The Cortex | TREXQUANT",
    page_icon=str(PROJECT_ROOT / "logo.png"),
    layout="wide",
    initial_sidebar_state="expanded",
)

inject_css()
sidebar_logo()

# ---------------------------------------------------------------------------
# Hero
# ---------------------------------------------------------------------------
_logo_path = PROJECT_ROOT / "brain.png"
_logo_b64 = ""
if _logo_path.exists():
    _logo_b64 = base64.b64encode(_logo_path.read_bytes()).decode()

_logo_html = (
    f'<img src="data:image/png;base64,{_logo_b64}" width="120" '
    f'style="border-radius: 8px; display: block; margin: 0 auto 1rem auto;" />'
    if _logo_b64 else ""
)

st.markdown(
    f"""
    <div style="text-align: center; padding: 3rem 0 1rem 0;">
        {_logo_html}
        <h1 class="hero-gradient" style="font-weight: 700; font-size: 2.2rem;
                    margin: 0;">
            The Cortex
        </h1>
        <p style="color: {TEXT_SECONDARY}; font-size: 1rem; margin-bottom: 2rem;">
            Analyze strategies, run backtests, and extract alpha from research papers
        </p>
    </div>
    """,
    unsafe_allow_html=True,
)

# ---------------------------------------------------------------------------
# Quick-nav cards (clickable)
# ---------------------------------------------------------------------------
NAV_SECTIONS = {
    "Strategies": [
        ("Backtester",
         "Run backtests on crop futures strategies. View equity curves, "
         "risk metrics, trade signals, and Monte Carlo stress tests.",
         "pages/1_Backtester.py"),
        ("Run History",
         "Browse, filter, and compare all backtest runs across strategies "
         "and tickers. Star top performers and drill into saved results.",
         "pages/2_Run_History.py"),
    ],
    "Research": [
        ("Data Explorer",
         "Browse engineered features with stats, seasonality, and "
         "distributions. Explore raw data sources and quality metrics.",
         "pages/3_Data_Explorer.py"),
        ("Paper Upload",
         "Extract trading strategies from research papers. Map features "
         "to available data and generate runnable strategy modules.",
         "pages/4_Paper_Upload.py"),
    ],
    "System": [
        ("AI Usage",
         "Track API costs, token consumption, and call history across "
         "Claude and DeepSeek, broken down by day, model, and function.",
         "pages/5_AI_Usage.py"),
    ],
}

_CARD_CSS = (
    f"background: {BG_CARD}; backdrop-filter: blur(12px); "
    f"-webkit-backdrop-filter: blur(12px); border: 1px solid {BORDER}; "
    f"border-radius: 12px; padding: 1.5rem; height: 140px; "
    f"transition: background 0.2s ease, border-color 0.2s ease; cursor: pointer;"
)
_HOVER_ON = f"this.style.background='{BG_CARD_HOVER}'; this.style.borderColor='rgba(148,163,184,0.14)'"
_HOVER_OFF = f"this.style.background='{BG_CARD}'; this.style.borderColor='{BORDER}'"

_SECTION_LABEL = (
    f"color: {TEXT_DIM}; font-size: 0.7rem; font-weight: 700; "
    f"text-transform: uppercase; letter-spacing: 0.08em; margin-bottom: 0.4rem;"
)

for section_name, cards in NAV_SECTIONS.items():
    st.markdown(
        f'<p style="{_SECTION_LABEL}">{section_name}</p>',
        unsafe_allow_html=True,
    )
    cols = st.columns(2)
    for col, (title, desc, page) in zip(cols, cards):
        with col:
            st.markdown(
                f'<div style="{_CARD_CSS}" '
                f'onmouseover="{_HOVER_ON}" onmouseout="{_HOVER_OFF}">'
                f'<h3 style="color: {ACCENT}; font-size: 1.1rem; margin: 0 0 0.5rem 0; '
                f'border: none; padding: 0;">{title}</h3>'
                f'<p style="color: {TEXT_SECONDARY}; font-size: 0.88rem; line-height: 1.5; '
                f'margin: 0;">{desc}</p></div>',
                unsafe_allow_html=True,
            )

# ---------------------------------------------------------------------------
# Table of Contents
# ---------------------------------------------------------------------------
st.markdown("")
st.markdown("")

st.markdown(
    f"""
    <div style="background: {BG_CARD_SOLID}; border: 1px solid {BORDER};
                border-radius: 10px; padding: 1.25rem 1.5rem; margin-bottom: 2rem;">
        <h4 style="color: {TEXT_PRIMARY}; font-size: 1rem; margin: 0 0 0.75rem 0;
                    border: none; padding: 0;">
            Table of Contents
        </h4>
        <div style="display: flex; flex-wrap: wrap; gap: 0.5rem 2rem;">
            <a href="#methodology" style="color: {TEXT_SECONDARY}; text-decoration: none;
               font-size: 0.85rem;">1. Methodology</a>
            <a href="#data-architecture" style="color: {TEXT_SECONDARY}; text-decoration: none;
               font-size: 0.85rem;">2. Data Architecture</a>
            <a href="#etl-pipeline" style="color: {TEXT_SECONDARY}; text-decoration: none;
               font-size: 0.85rem;">3. ETL Pipeline</a>
            <a href="#strategy-design" style="color: {TEXT_SECONDARY}; text-decoration: none;
               font-size: 0.85rem;">4. Strategy Design</a>
            <a href="#backtesting-engine" style="color: {TEXT_SECONDARY}; text-decoration: none;
               font-size: 0.85rem;">5. Backtesting Engine</a>
            <a href="#faq" style="color: {TEXT_SECONDARY}; text-decoration: none;
               font-size: 0.85rem;">6. FAQ</a>
        </div>
    </div>
    """,
    unsafe_allow_html=True,
)


# ---------------------------------------------------------------------------
# Helper: section placeholder
# ---------------------------------------------------------------------------
def _placeholder_block(label: str = "Your content here"):
    """Render a dashed placeholder box for future content."""
    st.markdown(
        f'<div style="border: 2px dashed {BORDER_SUBTLE}; border-radius: 10px; '
        f'padding: 2.5rem; text-align: center; margin: 1rem 0;">'
        f'<p style="color: {TEXT_FAINT}; font-size: 0.85rem; margin: 0;">{label}</p>'
        f'</div>',
        unsafe_allow_html=True,
    )


# ---------------------------------------------------------------------------
# 1. Methodology
# ---------------------------------------------------------------------------
st.markdown('<div id="methodology"></div>', unsafe_allow_html=True)
with st.expander("1. Methodology", expanded=False):
    st.markdown(
        f'<p style="color: {TEXT_DIM}; font-size: 0.85rem; font-style: italic;">'
        f'Describe the research hypothesis, signal construction approach, '
        f'and why agricultural weather data can predict commodity futures moves.</p>',
        unsafe_allow_html=True,
    )
    _placeholder_block("Add methodology overview text here")
    _placeholder_block("Add diagram / image here")

# ---------------------------------------------------------------------------
# 2. Data Architecture
# ---------------------------------------------------------------------------
st.markdown('<div id="data-architecture"></div>', unsafe_allow_html=True)
with st.expander("2. Data Architecture", expanded=False):
    st.markdown(
        f'<p style="color: {TEXT_DIM}; font-size: 0.85rem; font-style: italic;">'
        f'Explain the data flow: sources, landing zone, validation, '
        f'warehouse, feature store, and how consumers read from each layer.</p>',
        unsafe_allow_html=True,
    )
    _placeholder_block("Add architecture diagram here")
    col_l, col_r = st.columns(2)
    with col_l:
        _placeholder_block("Data sources overview")
    with col_r:
        _placeholder_block("Storage format details")

# ---------------------------------------------------------------------------
# 3. ETL Pipeline
# ---------------------------------------------------------------------------
st.markdown('<div id="etl-pipeline"></div>', unsafe_allow_html=True)
with st.expander("3. ETL Pipeline", expanded=False):
    st.markdown(
        f'<p style="color: {TEXT_DIM}; font-size: 0.85rem; font-style: italic;">'
        f'Walk through the scraping, validation, and loading process. '
        f'Cover Yahoo Finance futures and Open-Meteo weather ingestion.</p>',
        unsafe_allow_html=True,
    )
    _placeholder_block("Add ETL flow diagram here")
    _placeholder_block("Add validation rules / checks explanation here")

# ---------------------------------------------------------------------------
# 4. Strategy Design
# ---------------------------------------------------------------------------
st.markdown('<div id="strategy-design"></div>', unsafe_allow_html=True)
with st.expander("4. Strategy Design", expanded=False):
    st.markdown(
        f'<p style="color: {TEXT_DIM}; font-size: 0.85rem; font-style: italic;">'
        f'Explain the signal generation logic, feature engineering, '
        f'and how strategies are structured as pluggable modules.</p>',
        unsafe_allow_html=True,
    )
    _placeholder_block("Add signal logic explanation here")
    col_l, col_r = st.columns(2)
    with col_l:
        _placeholder_block("Feature engineering details")
    with col_r:
        _placeholder_block("Strategy interface / example")

# ---------------------------------------------------------------------------
# 5. Backtesting Engine
# ---------------------------------------------------------------------------
st.markdown('<div id="backtesting-engine"></div>', unsafe_allow_html=True)
with st.expander("5. Backtesting Engine", expanded=False):
    st.markdown(
        f'<p style="color: {TEXT_DIM}; font-size: 0.85rem; font-style: italic;">'
        f'Cover position sizing, transaction costs, P&L calculation, '
        f'risk metrics, and Monte Carlo / bootstrap stress testing.</p>',
        unsafe_allow_html=True,
    )
    _placeholder_block("Add backtesting flow diagram here")
    _placeholder_block("Add risk metrics explanation here")
    _placeholder_block("Add stress testing methodology here")

# ---------------------------------------------------------------------------
# 6. FAQ
# ---------------------------------------------------------------------------
st.markdown('<div id="faq"></div>', unsafe_allow_html=True)
st.markdown("### Frequently Asked Questions")

faq_items = [
    ("What data sources does the platform use?", "Add answer here"),
    ("How often is data refreshed?", "Add answer here"),
    ("What does the Sharpe ratio measure?", "Add answer here"),
    ("How does Monte Carlo stress testing work?", "Add answer here"),
    ("Can I add my own strategy?", "Add answer here"),
    ("What is the feature store?", "Add answer here"),
    ("How are trades sized?", "Add answer here"),
    ("What time period does the backtest cover?", "Add answer here"),
]

for question, answer in faq_items:
    with st.expander(question):
        st.markdown(
            f'<p style="color: {TEXT_DIM}; font-size: 0.85rem; font-style: italic;">'
            f'{answer}</p>',
            unsafe_allow_html=True,
        )

# ---------------------------------------------------------------------------
# Footer
# ---------------------------------------------------------------------------
st.markdown(
    f"""
    <p style="text-align: center; color: {TEXT_FAINT}; font-size: 0.75rem;
              margin-top: 3rem;">
        Navigate using the sidebar or the cards above
    </p>
    """,
    unsafe_allow_html=True,
)
