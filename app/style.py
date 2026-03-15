"""Custom CSS styling for the Streamlit app.

Provides a polished dark theme with indigo accent (#6366f1),
glass-morphism cards, Inter font, and smooth transitions."""

import base64
from pathlib import Path

import streamlit as st

LOGO_PATH = Path(__file__).resolve().parents[1] / "logo.png"

# ---------------------------------------------------------------------------
# Design System
# ---------------------------------------------------------------------------
ACCENT = "#6366f1"
ACCENT_HOVER = "#4f46e5"
ACCENT_DIM = "rgba(99, 102, 241, 0.12)"
BG_DARK = "#0b0d13"
BG_CARD = "rgba(255, 255, 255, 0.04)"
BG_CARD_SOLID = "#13141f"
BG_CARD_HOVER = "rgba(255, 255, 255, 0.07)"
TEXT_PRIMARY = "#f1f5f9"
TEXT_SECONDARY = "#94a3b8"
TEXT_DIM = "#64748b"
TEXT_FAINT = "#475569"
BORDER = "rgba(148, 163, 184, 0.08)"
BORDER_SUBTLE = "rgba(148, 163, 184, 0.05)"
GREEN = "#22c55e"
RED = "#ef4444"
AMBER = "#f59e0b"
LINK = "#818cf8"
BADGE = "#a5b4fc"

# Keep old name as alias so existing imports don't break
TEXT_MUTED = TEXT_SECONDARY

CHART_COLORS = {
    "equity": ACCENT,
    "price": TEXT_PRIMARY,
    "long": "rgba(34, 197, 94, 0.13)",
    "short": "rgba(239, 68, 68, 0.13)",
    "entry": GREEN,
    "exit": RED,
    "drawdown": "rgba(239, 68, 68, 0.35)",
    "drawdown_line": RED,
    "reference": "rgba(148, 163, 184, 0.3)",
    "histogram": ACCENT,
    "var_line": RED,
    "grid": "rgba(148, 163, 184, 0.08)",
    "text": TEXT_SECONDARY,
    "high_vol": AMBER,
    "low_vol": ACCENT,
    "mean_line": GREEN,
    "seasonality_fill": "rgba(99, 102, 241, 0.1)",
}

# ---------------------------------------------------------------------------
# CSS
# ---------------------------------------------------------------------------
CUSTOM_CSS = f"""
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap"
      rel="stylesheet">
<style>
    /* --- Global --- */
    .stApp {{
        background-color: {BG_DARK};
        font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
    }}
    .stMarkdown, .stMetric, .stDataFrame,
    .stSelectbox, .stTextInput, .stSlider,
    .stButton > button, .stTabs,
    .block-container h1, .block-container h2,
    .block-container h3, .block-container h4,
    .block-container p {{
        font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
    }}

    /* --- Sidebar --- */
    section[data-testid="stSidebar"] {{
        background-color: {BG_CARD_SOLID};
        border-right: 1px solid {BORDER};
    }}
    section[data-testid="stSidebar"] .stSelectbox label,
    section[data-testid="stSidebar"] .stMarkdown p {{
        color: {TEXT_SECONDARY};
        font-size: 0.85rem;
    }}
    /* Hide sidebar collapse-button tooltip / keyboard-shortcut hint */
    section[data-testid="stSidebar"] [data-testid="stSidebarCollapseButton"] span,
    [data-testid="collapsedControl"] span {{
        font-size: 0 !important;
        overflow: hidden !important;
    }}

    /* --- Metric cards (glass-morphism) --- */
    div[data-testid="stMetric"] {{
        background: {BG_CARD};
        backdrop-filter: blur(12px);
        -webkit-backdrop-filter: blur(12px);
        border: 1px solid {BORDER};
        border-radius: 10px;
        padding: 14px 18px;
        transition: background 0.2s ease, border-color 0.2s ease, box-shadow 0.2s ease;
    }}
    div[data-testid="stMetric"]:hover {{
        background: {BG_CARD_HOVER};
        border-color: rgba(148, 163, 184, 0.14);
        box-shadow: 0 8px 24px rgba(0, 0, 0, 0.35), 0 0 0 1px rgba(99, 102, 241, 0.10);
    }}
    div[data-testid="stMetric"] label {{
        color: {TEXT_SECONDARY} !important;
        font-size: 0.72rem !important;
        text-transform: uppercase;
        letter-spacing: 0.06em;
        font-weight: 500;
    }}
    div[data-testid="stMetric"] div[data-testid="stMetricValue"] {{
        font-size: 1.3rem !important;
        font-weight: 600;
        color: {TEXT_PRIMARY};
    }}

    /* --- Section headers --- */
    .stMarkdown h3 {{
        color: {TEXT_PRIMARY};
        font-weight: 500;
        border-bottom: 1px solid {BORDER};
        padding-bottom: 8px;
        margin-top: 2rem;
    }}

    /* --- DataFrames --- */
    .stDataFrame {{
        border: 1px solid {BORDER};
        border-radius: 10px;
    }}

    /* --- Expander --- */
    .streamlit-expanderHeader {{
        color: {TEXT_SECONDARY} !important;
        font-size: 0.85rem;
        transition: color 0.2s ease;
    }}
    .streamlit-expanderHeader:hover {{
        color: {TEXT_PRIMARY} !important;
    }}

    /* --- Button --- */
    .stButton > button[kind="primary"] {{
        background-color: {ACCENT};
        border: none;
        border-radius: 8px;
        font-weight: 500;
        transition: background-color 0.2s ease, transform 0.15s ease, box-shadow 0.2s ease;
    }}
    .stButton > button[kind="primary"]:hover {{
        background-color: {ACCENT_HOVER};
        transform: translateY(-1px);
        box-shadow: 0 0 16px rgba(99, 102, 241, 0.45);
    }}

    /* --- Tabs --- */
    .stTabs [data-baseweb="tab"] {{
        color: {TEXT_SECONDARY};
        transition: color 0.2s ease;
    }}
    .stTabs [aria-selected="true"] {{
        color: {ACCENT} !important;
        border-bottom-color: {ACCENT} !important;
    }}

    /* --- Entrance animation --- */
    @keyframes fadeInUp {{
        from {{ opacity: 0; transform: translateY(12px); }}
        to   {{ opacity: 1; transform: translateY(0); }}
    }}

    /* --- Remove default padding at top --- */
    .block-container {{
        padding-top: 2rem;
        animation: fadeInUp 0.45s ease-out;
    }}

    /* --- Chart containers (components.html iframes) --- */
    iframe {{
        border-radius: 10px;
    }}

    /* --- Links --- */
    a {{
        color: {LINK};
        transition: color 0.2s ease;
    }}
    a:hover {{
        color: {BADGE};
    }}

    /* --- Selectbox / inputs --- */
    .stSelectbox > div > div,
    .stTextInput > div > div > input {{
        transition: border-color 0.2s ease;
    }}

    /* --- Rename "main" to "Home" in sidebar nav --- */
    [data-testid="stSidebarNav"] li:first-child span {{
        font-size: 0 !important;
        line-height: 0 !important;
    }}
    [data-testid="stSidebarNav"] li:first-child span::before {{
        content: "Home";
        font-size: 0.875rem !important;
        line-height: 1.6 !important;
    }}

    /* --- Hero gradient text --- */
    .hero-gradient {{
        background: linear-gradient(135deg, {ACCENT}, #8b5cf6);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        background-clip: text;
    }}

    /* --- Focus ring for accessibility --- */
    .stButton > button:focus-visible,
    .stSelectbox > div > div:focus-visible,
    .stTextInput > div > div > input:focus-visible,
    .stTabs [data-baseweb="tab"]:focus-visible {{
        outline: 2px solid rgba(99, 102, 241, 0.6);
        outline-offset: 2px;
    }}

    /* --- Custom scrollbar --- */
    ::-webkit-scrollbar {{
        width: 8px;
        height: 8px;
    }}
    ::-webkit-scrollbar-track {{
        background: {BG_DARK};
    }}
    ::-webkit-scrollbar-thumb {{
        background: {TEXT_FAINT};
        border-radius: 4px;
    }}
    ::-webkit-scrollbar-thumb:hover {{
        background: {TEXT_DIM};
    }}
    /* Firefox */
    * {{
        scrollbar-width: thin;
        scrollbar-color: {TEXT_FAINT} {BG_DARK};
    }}
</style>
"""


def inject_css():
    """Inject custom CSS into the current page."""
    st.markdown(CUSTOM_CSS, unsafe_allow_html=True)


def sidebar_logo():
    """Render the TREXQUANT logo in the sidebar."""
    if LOGO_PATH.exists():
        logo_bytes = LOGO_PATH.read_bytes()
        b64 = base64.b64encode(logo_bytes).decode()
        st.sidebar.markdown(
            f"""
            <div style="text-align: center; padding: 0.5rem 0 1rem 0;">
                <img src="data:image/png;base64,{b64}" width="200"
                     style="border-radius: 6px;" />
            </div>
            """,
            unsafe_allow_html=True,
        )
    else:
        st.sidebar.title("TREXQUANT")
