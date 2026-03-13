"""Custom CSS styling for the Streamlit app.

Provides a dark, minimalist theme matching the Trex Quant brand:
dark navy background, blue accent (#3B82F6), clean sans-serif type."""

import base64
from pathlib import Path

import streamlit as st

LOGO_PATH = Path(__file__).resolve().parents[1] / "trexquant_logo.png"

ACCENT = "#3B82F6"
ACCENT_DIM = "rgba(59, 130, 246, 0.15)"
BG_DARK = "#0f1117"
BG_CARD = "#1a1b2e"
BG_CARD_HOVER = "#222340"
TEXT_PRIMARY = "#e2e8f0"
TEXT_MUTED = "#94a3b8"
BORDER = "rgba(59, 130, 246, 0.2)"

CUSTOM_CSS = f"""
<style>
    /* --- Global --- */
    .stApp {{
        background-color: {BG_DARK};
    }}

    /* --- Sidebar --- */
    section[data-testid="stSidebar"] {{
        background-color: {BG_CARD};
        border-right: 1px solid {BORDER};
    }}
    section[data-testid="stSidebar"] .stSelectbox label,
    section[data-testid="stSidebar"] .stMarkdown p {{
        color: {TEXT_MUTED};
        font-size: 0.85rem;
    }}

    /* --- Metric cards --- */
    div[data-testid="stMetric"] {{
        background: {BG_CARD};
        border: 1px solid {BORDER};
        border-radius: 8px;
        padding: 12px 16px;
    }}
    div[data-testid="stMetric"] label {{
        color: {TEXT_MUTED} !important;
        font-size: 0.75rem !important;
        text-transform: uppercase;
        letter-spacing: 0.05em;
    }}
    div[data-testid="stMetric"] div[data-testid="stMetricValue"] {{
        font-size: 1.3rem !important;
        font-weight: 600;
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
        border-radius: 8px;
    }}

    /* --- Expander --- */
    .streamlit-expanderHeader {{
        color: {TEXT_MUTED} !important;
        font-size: 0.85rem;
    }}

    /* --- Button --- */
    .stButton > button[kind="primary"] {{
        background-color: {ACCENT};
        border: none;
        border-radius: 6px;
        font-weight: 500;
    }}
    .stButton > button[kind="primary"]:hover {{
        background-color: #2563EB;
    }}

    /* --- Tabs --- */
    .stTabs [data-baseweb="tab"] {{
        color: {TEXT_MUTED};
    }}
    .stTabs [aria-selected="true"] {{
        color: {ACCENT} !important;
        border-bottom-color: {ACCENT} !important;
    }}

    /* --- Remove default padding at top --- */
    .block-container {{
        padding-top: 2rem;
    }}

    /* --- Chart containers (components.html iframes) --- */
    iframe {{
        border-radius: 8px;
    }}
</style>
"""


def inject_css():
    """Inject custom CSS into the current page."""
    st.markdown(CUSTOM_CSS, unsafe_allow_html=True)


def sidebar_logo():
    """Render the Trex Quant logo in the sidebar."""
    if LOGO_PATH.exists():
        logo_bytes = LOGO_PATH.read_bytes()
        b64 = base64.b64encode(logo_bytes).decode()
        st.sidebar.markdown(
            f"""
            <div style="text-align: center; padding: 0.5rem 0 1rem 0;">
                <img src="data:image/png;base64,{b64}" width="120"
                     style="border-radius: 8px;" />
                <div style="color: {TEXT_PRIMARY}; font-size: 1.1rem;
                            font-weight: 600; margin-top: 8px;
                            letter-spacing: 0.02em;">
                    Trex Quant
                </div>
                <div style="color: {TEXT_MUTED}; font-size: 0.75rem;
                            margin-top: 2px;">
                    Crop Yield Trading Platform
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    else:
        st.sidebar.title("Trex Quant")
        st.sidebar.caption("Crop Yield Trading Platform")
