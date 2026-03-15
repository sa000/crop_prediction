"""Data Explorer -- browse engineered features and raw data sources.

Two tabs: Features (browse and analyze engineered features with stats,
seasonality, and distributions) and Data Catalog (raw data source
inventory with quality metrics and exploration)."""

import sys
from pathlib import Path

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components
import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app import catalog_agent, charts
from app.style import (
    inject_css, sidebar_logo,
    BG_CARD_SOLID, BORDER, TEXT_PRIMARY, TEXT_SECONDARY, TEXT_DIM, GREEN, RED,
)
from etl.db import load_raw_data, source_summary
from features import query as fquery
from features import store

inject_css()
sidebar_logo(PROJECT_ROOT)

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
    <div style="background: {BG_CARD_SOLID}; border-radius: 10px;
                border: 1px solid {BORDER}; padding: 4px;">
        {html}
    </div>
    """
    components.html(wrapper, height=height, scrolling=False)


@st.cache_data(ttl=300)
def load_registry():
    """Load and cache the feature registry."""
    return fquery.load_registry()


@st.cache_data(ttl=300)
def load_scraper_config():
    """Load scraper config for data source metadata."""
    config_path = PROJECT_ROOT / "etl" / "scrapers" / "config.yaml"
    with open(config_path) as f:
        return yaml.safe_load(f)


@st.cache_data(ttl=300)
def get_source_stats(table, entity_col, entity_val):
    """Cached wrapper for source_summary."""
    return source_summary(table, entity_col, entity_val)


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


def get_feature_metadata(feature_name: str, category: str, entity: str) -> dict:
    """Look up a feature's metadata from metadata.parquet.

    Args:
        feature_name: Feature name.
        category: Feature category.
        entity: Entity name.

    Returns:
        Dict with stat_mean, stat_std, stat_min, stat_max, null_pct,
        freshness, available_from, source_table. Empty dict if not found.
    """
    metadata = store.read_metadata()
    if metadata.empty:
        return {}
    match = metadata[
        (metadata["name"] == feature_name)
        & (metadata["category"] == category)
        & (metadata["entity"] == entity)
    ]
    if match.empty:
        return {}
    return match.iloc[0].to_dict()


def render_feature_stats(feat_df, feature, meta):
    """Render summary stats card, seasonality chart, and histogram for a feature."""
    values = feat_df[feature].dropna()
    if values.empty:
        return

    # Compute skew and kurtosis on the fly
    skew = values.skew()
    kurtosis = values.kurtosis()

    # Pull pre-computed stats from metadata, fall back to computed
    mean_val = meta.get("stat_mean", values.mean())
    std_val = meta.get("stat_std", values.std())
    null_pct = meta.get("null_pct", 0.0)
    freshness = meta.get("freshness", "N/A")
    available_from = meta.get("available_from", "N/A")
    source_table = meta.get("source_table", "N/A")

    # Stats card
    st.markdown(
        f'<p style="color: {TEXT_SECONDARY}; font-size: 0.75rem; margin-top: 1rem;">'
        f'Source: {source_table} &nbsp;|&nbsp; '
        f'Latest: {freshness} &nbsp;|&nbsp; '
        f'Available from: {available_from}</p>',
        unsafe_allow_html=True,
    )

    cols = st.columns(6)
    cols[0].metric("Mean", f"{mean_val:.4f}")
    cols[1].metric("Std Dev", f"{std_val:.4f}")
    cols[2].metric("Skew", f"{skew:.3f}")
    cols[3].metric("Kurtosis", f"{kurtosis:.3f}")
    cols[4].metric("Null %", f"{null_pct:.1f}%")
    cols[5].metric("Observations", f"{len(values):,}")

    # Seasonality and distribution side by side
    col_season, col_dist = st.columns(2)

    with col_season:
        entity_label = feature.replace("_", " ").title()
        show_chart(
            charts.seasonality_chart(
                feat_df, "date", feature,
                f"Seasonality \u2014 {entity_label}",
            ),
            height=420,
        )

    with col_dist:
        show_chart(
            charts.distribution_chart(
                values,
                f"Distribution \u2014 {feature}",
                mean_val,
                std_val,
            ),
            height=420,
        )


# ---------------------------------------------------------------------------
# Page header
# ---------------------------------------------------------------------------

st.markdown(
    f'<h1 style="font-weight: 600; font-size: 1.8rem; color: {TEXT_PRIMARY};">'
    f'Data Explorer</h1>',
    unsafe_allow_html=True,
)

tab_features, tab_catalog = st.tabs(["Features", "Data Catalog"])


# ===========================================================================
# TAB 1: FEATURES
# ===========================================================================

with tab_features:
    registry = load_registry()

    # --- AI Catalog Agent ---
    has_api_key = False
    try:
        api_key = st.secrets["DEEPSEEK_API_KEY"]
        if api_key:
            has_api_key = True
    except (KeyError, FileNotFoundError):
        pass

    if has_api_key:
        question = st.text_input(
            "Ask about features",
            placeholder="e.g. What weather data do we have?",
            key="catalog_question",
        )

        if question:
            metadata_df = store.read_metadata()
            if metadata_df.empty:
                st.warning(
                    "Feature metadata not found. "
                    "Run `python -m features.pipeline --rebuild` first."
                )
            else:
                with st.spinner("Searching catalog..."):
                    result = catalog_agent.ask(question, metadata_df, api_key)
                st.session_state["agent_result"] = result

        if "agent_result" in st.session_state:
            result = st.session_state["agent_result"]
            st.markdown(
                f'<p style="color: {TEXT_PRIMARY}; font-size: 0.95rem;">'
                f'{result["answer"]}</p>',
                unsafe_allow_html=True,
            )

            if result["features"]:
                results_df = pd.DataFrame(result["features"])
                display_cols = [
                    c for c in ["name", "category", "entity", "description"]
                    if c in results_df.columns
                ]
                if display_cols:
                    event = st.dataframe(
                        results_df[display_cols],
                        on_select="rerun",
                        selection_mode="single-row",
                        hide_index=True,
                        key="agent_results_table",
                    )

                    selected_rows = event.selection.rows
                    if selected_rows:
                        sel = results_df.iloc[selected_rows[0]]
                        sel_name = sel.get("name", "")

                        raw_cat = sel.get("category", "").lower()
                        raw_cat = raw_cat.replace(" features", "")
                        sel_cat = raw_cat.replace(" ", "_")

                        sel_entity = sel.get("entity", "").lower().strip()

                        if sel_cat and sel_entity and sel_name:
                            sel_df = fquery.read_parquet(
                                sel_cat, sel_entity,
                                columns=["date", sel_name],
                            )
                            if not sel_df.empty:
                                show_chart(
                                    charts.feature_line_chart(
                                        sel_df, sel_name, sel_entity, sel_cat
                                    ),
                                    height=520,
                                )
                                meta = get_feature_metadata(
                                    sel_name, sel_cat, sel_entity
                                )
                                render_feature_stats(sel_df, sel_name, meta)
                            else:
                                st.warning(
                                    f"No data for {sel_cat}/{sel_entity}/{sel_name}."
                                )
    else:
        st.info(
            "Add your Anthropic API key to `.streamlit/secrets.toml` "
            "to enable the AI feature catalog assistant."
        )

    # --- Manual dropdowns ---
    st.divider()
    st.markdown(
        f'<p style="color: {TEXT_DIM}; font-size: 0.85rem;">Or browse manually</p>',
        unsafe_allow_html=True,
    )

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
            f'<p style="color: {TEXT_DIM}; font-size: 0.85rem;">{desc}</p>',
            unsafe_allow_html=True,
        )

    # Load and plot
    feat_df = fquery.read_parquet(category, entity, columns=["date", feature])

    if feat_df.empty:
        st.warning(f"No data found for {category}/{entity}.")
    else:
        non_null = feat_df[feature].dropna()
        st.markdown(
            f'<p style="color: {TEXT_DIM}; font-size: 0.85rem;">'
            f'{len(non_null):,} data points &nbsp;&bull;&nbsp; '
            f'{feat_df["date"].min()} to {feat_df["date"].max()}</p>',
            unsafe_allow_html=True,
        )
        show_chart(
            charts.feature_line_chart(feat_df, feature, entity, category),
            height=520,
        )

        # Summary stats, seasonality, distribution
        meta = get_feature_metadata(feature, category, entity)
        render_feature_stats(feat_df, feature, meta)


# ===========================================================================
# TAB 2: DATA CATALOG
# ===========================================================================

with tab_catalog:
    config = load_scraper_config()
    registry = load_registry()

    st.markdown(
        f'<p style="color: {TEXT_SECONDARY}; font-size: 0.85rem; margin-bottom: 1.5rem;">'
        f'Raw data sources ingested into the warehouse</p>',
        unsafe_allow_html=True,
    )

    # --- Futures ---
    st.markdown("### Futures (Yahoo Finance)")

    futures_tickers = config.get("yahoo_finance", {}).get("tickers", [])
    ticker_feature_map = registry.get("ticker_feature_map", {})

    for ticker_info in futures_tickers:
        symbol = ticker_info["symbol"]
        name = ticker_info["name"]
        stats = get_source_stats("futures_daily", "ticker", symbol)

        derived = []
        for cat, feats in ticker_feature_map.get(name, {}).items():
            derived.extend(feats)

        with st.expander(f"{name.title()} ({symbol})", expanded=False):
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Rows", f"{stats['row_count']:,}")
            c2.metric("From", stats["min_date"] or "N/A")
            c3.metric("To", stats["max_date"] or "N/A")
            c4.metric("Source", "Yahoo Finance")

            # Null percentages
            null_data = stats["null_pct"]
            if null_data:
                null_cols = st.columns(len(null_data))
                for col_widget, (col_name, pct) in zip(null_cols, null_data.items()):
                    color = GREEN if pct == 0 else RED
                    col_widget.markdown(
                        f'<p style="color: {TEXT_SECONDARY}; font-size: 0.75rem;">'
                        f'{col_name}</p>'
                        f'<p style="color: {color}; font-size: 0.9rem; '
                        f'font-weight: 600;">{pct:.1f}% null</p>',
                        unsafe_allow_html=True,
                    )

            # Derived features
            if derived:
                st.markdown(
                    f'<p style="color: {TEXT_SECONDARY}; font-size: 0.75rem; '
                    f'margin-top: 0.5rem;">Derived features: '
                    f'{", ".join(derived)}</p>',
                    unsafe_allow_html=True,
                )

    # --- Weather ---
    st.markdown("### Weather (Open-Meteo)")

    weather_locations = config.get("open_meteo", {}).get("locations", [])
    unlinked = registry.get("unlinked_features", {}).get("weather", {})

    for loc in weather_locations:
        state = loc["state"]
        state_key = state.lower()
        stats = get_source_stats("weather_daily", "state", state)

        derived = unlinked.get(state_key, [])

        with st.expander(
            f"{state} ({loc['lat']}, {loc['lon']})", expanded=False
        ):
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Rows", f"{stats['row_count']:,}")
            c2.metric("From", stats["min_date"] or "N/A")
            c3.metric("To", stats["max_date"] or "N/A")
            c4.metric("Source", "Open-Meteo")

            # Null percentages
            null_data = stats["null_pct"]
            if null_data:
                null_cols = st.columns(len(null_data))
                for col_widget, (col_name, pct) in zip(null_cols, null_data.items()):
                    color = GREEN if pct == 0 else RED
                    col_widget.markdown(
                        f'<p style="color: {TEXT_SECONDARY}; font-size: 0.75rem;">'
                        f'{col_name}</p>'
                        f'<p style="color: {color}; font-size: 0.9rem; '
                        f'font-weight: 600;">{pct:.1f}% null</p>',
                        unsafe_allow_html=True,
                    )

            if derived:
                st.markdown(
                    f'<p style="color: {TEXT_SECONDARY}; font-size: 0.75rem; '
                    f'margin-top: 0.5rem;">Derived features: '
                    f'{", ".join(derived)}</p>',
                    unsafe_allow_html=True,
                )

    # --- Raw Data Exploration ---
    st.divider()
    st.markdown("### Explore Raw Data")

    col_src, col_ent, col_field = st.columns(3)

    with col_src:
        source_type = st.selectbox(
            "Source",
            ["Futures", "Weather"],
            key="catalog_source",
        )

    if source_type == "Futures":
        entity_options = {t["name"].title(): t for t in futures_tickers}
        table = "futures_daily"
        entity_col = "ticker"
    else:
        entity_options = {loc["state"]: loc for loc in weather_locations}
        table = "weather_daily"
        entity_col = "state"

    with col_ent:
        entity_name = st.selectbox(
            "Entity",
            list(entity_options.keys()),
            key="catalog_entity",
        )

    entity_info = entity_options[entity_name]

    if source_type == "Futures":
        entity_val = entity_info["symbol"]
        data_columns = ["open", "high", "low", "close", "volume"]
    else:
        entity_val = entity_info["state"]
        data_columns = ["temp_max_f", "temp_min_f", "precip_in"]

    with col_field:
        field = st.selectbox("Column", data_columns, key="catalog_field")

    raw_df = load_raw_data(table, entity_col, entity_val)

    if raw_df.empty:
        st.warning(f"No data for {entity_name}.")
    else:
        values = raw_df[field].dropna()
        mean_val = values.mean()
        std_val = values.std()

        st.markdown(
            f'<p style="color: {TEXT_SECONDARY}; font-size: 0.85rem;">'
            f'{len(values):,} data points &nbsp;&bull;&nbsp; '
            f'{raw_df["date"].min().date()} to {raw_df["date"].max().date()}</p>',
            unsafe_allow_html=True,
        )

        col_season, col_dist = st.columns(2)

        with col_season:
            show_chart(
                charts.seasonality_chart(
                    raw_df, "date", field,
                    f"Seasonality \u2014 {entity_name} {field}",
                ),
                height=420,
            )

        with col_dist:
            show_chart(
                charts.distribution_chart(
                    values,
                    f"Distribution \u2014 {entity_name} {field}",
                    mean_val,
                    std_val,
                ),
                height=420,
            )
