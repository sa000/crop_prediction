"""Data Explorer -- browse price, weather, and feature data."""

import sys
from pathlib import Path

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app import charts
from app.style import inject_css, sidebar_logo, BG_CARD
from etl import db
from features import query as fquery

inject_css()
sidebar_logo()

TICKER_MAP = {
    "Corn": "ZC=F",
    "Soybeans": "ZS=F",
    "Wheat": "ZW=F",
}

CATEGORIES = ["momentum", "mean_reversion", "weather"]

CATEGORY_LABELS = {
    "momentum": "Momentum",
    "mean_reversion": "Mean Reversion",
    "weather": "Weather",
}


def show_chart(fig, height=580):
    """Render a Plotly figure via HTML."""
    html = fig.to_html(include_plotlyjs="cdn", full_html=False)
    wrapper = f"""
    <div style="background: {BG_CARD}; border-radius: 8px;
                border: 1px solid rgba(59,130,246,0.12); padding: 4px;">
        {html}
    </div>
    """
    components.html(wrapper, height=height, scrolling=False)


def load_ticker(symbol: str) -> pd.DataFrame:
    """Load OHLCV data for a ticker from the warehouse."""
    conn = db.get_connection()
    df = pd.read_sql(
        "SELECT date, open, high, low, close, volume "
        "FROM futures_daily WHERE ticker = ? ORDER BY date",
        conn,
        params=(symbol,),
        parse_dates=["date"],
        index_col="date",
    )
    conn.close()
    df.columns = [c.capitalize() for c in df.columns]
    return df


@st.cache_data(ttl=300)
def load_registry():
    """Load and cache the feature registry."""
    return fquery.load_registry()


def get_entities_for_category(registry: dict, category: str) -> list[str]:
    """Get available entities for a category from the registry."""
    files = registry.get("files", {}).get(category, {})
    return sorted(files.keys())


def get_features_for_category(registry: dict, category: str) -> list[str]:
    """Get feature names for a category from the registry."""
    all_features = registry.get("features", [])
    return [f["name"] for f in all_features if f["category"] == category]


def get_feature_description(registry: dict, feature_name: str) -> str:
    """Look up a feature's description from the registry."""
    for f in registry.get("features", []):
        if f["name"] == feature_name:
            return f.get("description", "")
    return ""


st.markdown(
    '<h1 style="font-weight: 600; font-size: 1.8rem; color: #e2e8f0;">'
    'Data Explorer</h1>',
    unsafe_allow_html=True,
)

tab_price, tab_features = st.tabs(["Price Data", "Feature Explorer"])

VIEWS = ["Candlestick (All)", "Open", "High", "Low", "Close", "Volume"]

with tab_price:
    col_ticker, col_view = st.columns([1, 2])
    with col_ticker:
        ticker_name = st.selectbox("Ticker", list(TICKER_MAP.keys()), key="price_ticker")
    with col_view:
        view = st.selectbox("View", VIEWS, key="price_view")

    symbol = TICKER_MAP[ticker_name]
    df = load_ticker(symbol)

    st.markdown(
        f'<p style="color: #64748b; font-size: 0.85rem;">'
        f'{len(df):,} trading days &nbsp;&bull;&nbsp; '
        f'{df.index[0].date()} to {df.index[-1].date()}</p>',
        unsafe_allow_html=True,
    )

    if view == "Candlestick (All)":
        show_chart(charts.price_chart(df, ticker_name), height=600)
    else:
        show_chart(charts.price_line_chart(df, ticker_name, view), height=520)

with tab_features:
    registry = load_registry()

    col_cat, col_entity, col_feat = st.columns([1, 1, 1])
    with col_cat:
        category = st.selectbox(
            "Category",
            CATEGORIES,
            format_func=lambda c: CATEGORY_LABELS[c],
            key="feat_category",
        )

    entities = get_entities_for_category(registry, category)
    entity_labels = {e: e.replace("_", " ").title() for e in entities}

    with col_entity:
        label = "Region" if category == "weather" else "Ticker"
        entity = st.selectbox(
            label,
            entities,
            format_func=lambda e: entity_labels[e],
            key="feat_entity",
        )

    features = get_features_for_category(registry, category)

    with col_feat:
        feature = st.selectbox("Feature", features, key="feat_feature")

    # Show description
    desc = get_feature_description(registry, feature)
    if desc:
        st.markdown(
            f'<p style="color: #64748b; font-size: 0.85rem;">{desc}</p>',
            unsafe_allow_html=True,
        )

    # Load and plot
    feat_df = fquery.read_parquet(category, entity, columns=["date", feature])

    if feat_df.empty:
        st.warning(f"No data found for {category}/{entity}.")
    else:
        non_null = feat_df[feature].dropna()
        st.markdown(
            f'<p style="color: #64748b; font-size: 0.85rem;">'
            f'{len(non_null):,} data points &nbsp;&bull;&nbsp; '
            f'{feat_df["date"].min()} to {feat_df["date"].max()}</p>',
            unsafe_allow_html=True,
        )
        show_chart(
            charts.feature_line_chart(feat_df, feature, entity, category),
            height=520,
        )
