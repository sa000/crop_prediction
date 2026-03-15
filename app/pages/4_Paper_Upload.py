"""Paper Upload -- extract strategies from research papers.

Guided pipeline: select a paper, click Extract Strategy, and all three AI
agents execute sequentially (extract → map → generate). Results appear inline
as each step completes. Save & Run navigates directly to the backtester."""

import sys
import time
from pathlib import Path

import streamlit as st

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

st.set_page_config(
    page_title="Paper Upload | Cortex",
    page_icon=str(PROJECT_ROOT / "brain.png"),
    layout="wide",
)

from app.ai_usage import get_avg_durations
from app.paper_agent.extractor import DEMO_PAPERS, extract_strategy, load_demo_paper
from app.paper_agent.generator import generate_strategy_code, save_strategy
from app.paper_agent.mapper import map_features
from app.style import (
    inject_css, sidebar_logo,
    ACCENT, BG_CARD, BG_CARD_SOLID, BORDER, BORDER_SUBTLE,
    TEXT_PRIMARY, TEXT_SECONDARY, TEXT_DIM, TEXT_FAINT,
    GREEN, RED, AMBER, BADGE,
)

inject_css()
sidebar_logo(PROJECT_ROOT)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
ASSET_TO_TICKER = {
    "corn": "Corn",
    "zc": "Corn",
    "soybeans": "Soybeans",
    "soybean": "Soybeans",
    "zs": "Soybeans",
    "wheat": "Wheat",
    "zw": "Wheat",
}


# ---------------------------------------------------------------------------
# API key
# ---------------------------------------------------------------------------
_api_key = ""
try:
    _api_key = st.secrets["DEEPSEEK_API_KEY"]
except (KeyError, FileNotFoundError):
    pass


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _status_badge(label: str, color: str) -> str:
    """Return an HTML badge span."""
    return (
        f'<span style="background: {color}22; color: {color}; '
        f'font-size: 0.75rem; font-weight: 600; padding: 0.15rem 0.5rem; '
        f'border-radius: 4px; text-transform: uppercase;">{label}</span>'
    )


def _card(content: str, border_color: str = BORDER) -> str:
    """Wrap content in a styled card div."""
    return (
        f'<div style="background: {BG_CARD}; backdrop-filter: blur(12px); '
        f'-webkit-backdrop-filter: blur(12px); border: 1px solid {border_color}; '
        f'border-radius: 10px; padding: 1rem 1.25rem; margin-bottom: 0.75rem;">'
        f'{content}</div>'
    )


def _clear_pipeline():
    """Clear all pipeline session state."""
    for key in ("paper_spec", "paper_feasibility", "paper_code",
                "paper_saved_path", "paper_demo"):
        st.session_state.pop(key, None)


def _resolve_ticker(target_assets: list) -> str | None:
    """Map paper's target_assets list to a ticker name (Corn, Soybeans, Wheat)."""
    for asset in (target_assets or []):
        asset_lower = asset.lower()
        for key, ticker_name in ASSET_TO_TICKER.items():
            if key in asset_lower:
                return ticker_name
    return None


# ---------------------------------------------------------------------------
# Page header
# ---------------------------------------------------------------------------
st.markdown(
    f'<h1 style="font-weight: 600; font-size: 1.8rem; color: {TEXT_PRIMARY};">'
    f'Paper Upload</h1>',
    unsafe_allow_html=True,
)
st.markdown(
    f'<p style="color: {TEXT_SECONDARY}; font-size: 0.9rem; margin-bottom: 1.5rem;">'
    f'Extract a trading strategy from a research paper, map it to available data, '
    f'and generate a runnable strategy module.</p>',
    unsafe_allow_html=True,
)

if not _api_key:
    st.warning(
        "Add your DeepSeek API key to .streamlit/secrets.toml to use this feature. "
        "Example: DEEPSEEK_API_KEY = \"sk-...\""
    )
    st.stop()

# Load average durations for time estimates
avg_durations = get_avg_durations()

# ---------------------------------------------------------------------------
# Step 1: Select Paper
# ---------------------------------------------------------------------------
st.markdown(
    f'<p style="color: {TEXT_DIM}; font-size: 0.7rem; font-weight: 700; '
    f'text-transform: uppercase; letter-spacing: 0.08em; margin-bottom: 0.3rem;">'
    f'Step 1: Select Paper</p>',
    unsafe_allow_html=True,
)

demo_keys = list(DEMO_PAPERS.keys())
selected_demo = st.selectbox(
    "Demo Paper",
    demo_keys,
    label_visibility="collapsed",
)

# Clear results when user switches papers
if st.session_state.get("paper_demo") != selected_demo:
    _clear_pipeline()

paper_text = load_demo_paper(selected_demo)
with st.expander("Paper Preview", expanded=False):
    st.markdown(
        f'<div style="color: {TEXT_SECONDARY}; font-size: 0.85rem; '
        f'line-height: 1.7; white-space: pre-wrap; font-family: inherit;">'
        f'{paper_text}</div>',
        unsafe_allow_html=True,
    )

# Time estimate (sum all 3 agents)
total_estimate = sum(
    avg_durations.get(k, 0)
    for k in ("paper_extractor", "paper_mapper", "paper_generator")
)
if total_estimate > 0:
    st.markdown(
        f'<p style="color: {TEXT_DIM}; font-size: 0.78rem;">'
        f'Estimated time: ~{total_estimate:.0f}s based on previous runs</p>',
        unsafe_allow_html=True,
    )

# ---------------------------------------------------------------------------
# Extract Strategy button
# ---------------------------------------------------------------------------
has_results = "paper_spec" in st.session_state

col_run, col_spacer = st.columns([1, 3])
with col_run:
    run_label = "Re-extract Strategy" if has_results else "Extract Strategy"
    run_clicked = st.button(run_label, type="primary", width="stretch")

if run_clicked:
    _clear_pipeline()

    def _fmt_estimate(key: str) -> str:
        """Format an estimated time string from avg_durations, or empty."""
        avg = avg_durations.get(key, 0)
        if avg > 0:
            return f" (est. ~{avg:.0f}s)"
        return ""

    with st.status("Extracting strategy...", expanded=True) as status:
        # --- Agent 1: Extraction ---
        est1 = _fmt_estimate("paper_extractor")
        st.write(f"**Agent 1:** Extracting strategy spec from paper...{est1}")
        t0 = time.monotonic()
        spec = extract_strategy(paper_text, _api_key)
        elapsed1 = time.monotonic() - t0
        if spec.get("error"):
            status.update(label="Extraction failed", state="error")
            st.error(spec["error"])
            st.stop()

        resolved = _resolve_ticker(spec.get("target_assets", []))
        ticker_str = f" ({resolved})" if resolved else ""
        st.write(
            f"Extracted: **{spec.get('title', 'Untitled')}**{ticker_str} "
            f"— {elapsed1:.1f}s"
        )
        thesis = spec.get("thesis", "")
        if thesis:
            st.write(f"*{thesis}*")

        # --- Feasibility definition ---
        st.write("---")
        st.write(
            "Next we determine if this strategy is **feasible** — whether we "
            "already have the required features in our store or can derive them "
            "from raw data in our warehouse."
        )

        # --- Agent 2: Feature Mapping ---
        est2 = _fmt_estimate("paper_mapper")
        st.write(f"**Agent 2:** Mapping features against data catalog...{est2}")
        t0 = time.monotonic()
        feasibility = map_features(spec, _api_key)
        elapsed2 = time.monotonic() - t0
        if feasibility.get("error"):
            status.update(label="Feasibility check failed", state="error")
            st.error(feasibility["error"])
            st.stop()

        st.write(f"Mapping complete — {elapsed2:.1f}s")

        # Show individual feature breakdown
        feat_status_map = {}
        for f in feasibility.get("features", []):
            feat_status_map[f.get("paper_feature", "")] = f

        for feat in spec.get("required_features", []):
            feat_name = feat["name"]
            finfo = feat_status_map.get(feat_name, {})
            fstatus = finfo.get("status", "unknown")

            if fstatus == "in_store":
                col_name = finfo.get("store_column",
                                     finfo.get("store_feature", ""))
                st.write(f"  ✓ **{feat_name}** — in store (`{col_name}`)")
            elif fstatus == "derivable":
                raw_t = finfo.get("raw_table", "")
                raw_c = finfo.get("raw_column", "")
                st.write(f"  ✓ **{feat_name}** — derivable from `{raw_t}.{raw_c}`")
            elif fstatus == "not_possible":
                reason = finfo.get("reason", "data not available")
                st.write(f"  ✗ **{feat_name}** — missing ({reason})")
            else:
                st.write(f"  ? **{feat_name}** — unknown status")

        is_feasible = feasibility.get("feasible", False)

        if is_feasible:
            st.write("**Result: Feasible** — all features available or derivable")
        else:
            st.write("**Result: Not Feasible** — some required data is missing")

        st.session_state["paper_spec"] = spec
        st.session_state["paper_feasibility"] = feasibility
        st.session_state["paper_demo"] = selected_demo

        # --- Agent 3: Code Generation (only if feasible) ---
        if is_feasible:
            st.write("---")
            est3 = _fmt_estimate("paper_generator")
            st.write(f"**Agent 3:** Generating strategy code...{est3}")
            t0 = time.monotonic()
            code = generate_strategy_code(spec, feasibility, _api_key)
            elapsed3 = time.monotonic() - t0
            if code.startswith("ERROR:"):
                status.update(label="Code generation failed", state="error")
                st.error(code)
                st.stop()
            st.session_state["paper_code"] = code
            st.write(f"Strategy code generated — {elapsed3:.1f}s")

        total_elapsed = elapsed1 + elapsed2 + (elapsed3 if is_feasible else 0)
        label = (
            f"Extraction complete — {total_elapsed:.0f}s total"
            if is_feasible
            else f"Extraction complete — not feasible ({elapsed1 + elapsed2:.0f}s)"
        )
        status.update(label=label, state="complete")

    st.rerun()

# ---------------------------------------------------------------------------
# Results display (shown after pipeline completes)
# ---------------------------------------------------------------------------
if not has_results:
    st.stop()

spec = st.session_state["paper_spec"]
feasibility = st.session_state["paper_feasibility"]
resolved_ticker = _resolve_ticker(spec.get("target_assets", []))

# ---------------------------------------------------------------------------
# Step 2: Strategy Spec
# ---------------------------------------------------------------------------
st.markdown("---")
st.markdown(
    f'<p style="color: {TEXT_DIM}; font-size: 0.7rem; font-weight: 700; '
    f'text-transform: uppercase; letter-spacing: 0.08em; margin-bottom: 0.3rem;">'
    f'Step 2: Strategy Spec</p>',
    unsafe_allow_html=True,
)

# Editable title
spec["title"] = st.text_input("Strategy Name", value=spec.get("title", ""))

# Thesis
st.markdown(
    f'<p style="color: {TEXT_DIM}; font-size: 0.8rem; margin-bottom: 0.25rem;">'
    f'Thesis</p>',
    unsafe_allow_html=True,
)
st.markdown(
    _card(f'<p style="color: {TEXT_SECONDARY}; font-size: 0.88rem; margin: 0;">'
          f'{spec.get("thesis", "")}</p>'),
    unsafe_allow_html=True,
)

# Target ticker and assets
target_parts = []
if resolved_ticker:
    target_parts.append(f'<span style="color: {TEXT_PRIMARY}; font-weight: 600;">'
                        f'{resolved_ticker}</span>')
target_assets_raw = spec.get("target_assets", [])
if target_assets_raw:
    assets_str = ", ".join(target_assets_raw)
    target_parts.append(f'<span style="color: {TEXT_SECONDARY}; font-size: 0.82rem;">'
                        f'({assets_str})</span>')
if target_parts:
    st.markdown(
        f'<p style="color: {TEXT_DIM}; font-size: 0.8rem;">Target: '
        f'{" ".join(target_parts)}</p>',
        unsafe_allow_html=True,
    )

# ---------------------------------------------------------------------------
# Step 3: Feasibility
# ---------------------------------------------------------------------------
st.markdown("---")
st.markdown(
    f'<p style="color: {TEXT_DIM}; font-size: 0.7rem; font-weight: 700; '
    f'text-transform: uppercase; letter-spacing: 0.08em; margin-bottom: 0.3rem;">'
    f'Step 3: Feasibility</p>',
    unsafe_allow_html=True,
)

# Overall feasibility banner
if feasibility.get("feasible"):
    banner_color = GREEN
    banner_label = "FEASIBLE"
    banner_text = ("We have the data for this strategy or can derive the required "
                   "features from our warehouse.")
else:
    banner_color = RED
    banner_label = "NOT FEASIBLE"
    banner_text = "Some required data is missing. This strategy cannot be generated."

st.markdown(
    f'<div style="display: flex; align-items: center; gap: 0.75rem; '
    f'padding: 0.6rem 1rem; border-radius: 8px; '
    f'border: 1px solid {banner_color}33; margin-bottom: 1rem;">'
    f'{_status_badge(banner_label, banner_color)}'
    f'<span style="color: {TEXT_SECONDARY}; font-size: 0.85rem;">{banner_text}</span>'
    f'<span style="color: {TEXT_DIM}; font-size: 0.8rem; margin-left: auto;">'
    f'{feasibility.get("store_count", 0)} in store '
    f'&bull; {feasibility.get("derivable_count", 0)} derivable '
    f'&bull; {feasibility.get("not_possible_count", 0)} missing</span>'
    f'</div>',
    unsafe_allow_html=True,
)

# Required features with inline feasibility status
st.markdown(
    f'<p style="color: {TEXT_DIM}; font-size: 0.8rem; margin-bottom: 0.25rem;">'
    f'Required Features</p>',
    unsafe_allow_html=True,
)

feat_status_map = {}
for f in feasibility.get("features", []):
    feat_status_map[f.get("paper_feature", "")] = f

for feat in spec.get("required_features", []):
    feat_name = feat["name"]
    finfo = feat_status_map.get(feat_name, {})
    fstatus = finfo.get("status", "unknown")

    with st.container(border=True):
        if fstatus == "in_store":
            badge_html = _status_badge("In Store", GREEN)
        elif fstatus == "derivable":
            badge_html = _status_badge("Derivable", ACCENT)
        elif fstatus == "not_possible":
            badge_html = _status_badge("Missing", RED)
        else:
            badge_html = _status_badge("Unknown", TEXT_DIM)

        role_text = feat.get("role", "")
        st.markdown(
            f'{badge_html} &nbsp; '
            f'<span style="color: {TEXT_PRIMARY}; font-weight: 600; '
            f'font-size: 0.95rem;">{feat_name}</span>'
            f'<span style="color: {TEXT_DIM}; font-size: 0.72rem; '
            f'text-transform: uppercase; margin-left: 0.5rem;">'
            f'{role_text}</span>',
            unsafe_allow_html=True,
        )

        formula = feat.get("formula", "")
        if formula:
            st.latex(formula)

        computation = feat.get("computation", "")
        if computation:
            st.markdown(f"*{computation}*")

        if fstatus == "in_store":
            store_col = finfo.get("store_column",
                                  finfo.get("store_feature", ""))
            store_cat = finfo.get("store_category", "")
            store_ent = finfo.get("store_entity", "")
            st.markdown(
                f'<span style="color: {TEXT_DIM}; font-size: 0.8rem;">'
                f'Mapped to </span>'
                f'<span style="color: {GREEN}; font-size: 0.8rem; '
                f'font-weight: 500;">{store_col}</span>'
                f'<span style="color: {TEXT_DIM}; font-size: 0.8rem;">'
                f' ({store_cat}/{store_ent})</span>',
                unsafe_allow_html=True,
            )
        elif fstatus == "derivable":
            raw_table = finfo.get("raw_table", "")
            raw_col = finfo.get("raw_column", "")
            derivation = finfo.get("derivation", "")
            st.markdown(
                f'<span style="color: {TEXT_DIM}; font-size: 0.8rem;">'
                f'From </span>'
                f'<span style="color: {ACCENT}; font-size: 0.8rem; '
                f'font-weight: 500;">{raw_table}.{raw_col}</span>'
                f'<span style="color: {TEXT_DIM}; font-size: 0.8rem;">'
                f' -- {derivation}</span>',
                unsafe_allow_html=True,
            )
            if finfo.get("derivation_code"):
                with st.expander("Derivation Code", expanded=False):
                    st.code(finfo["derivation_code"], language="python")
        elif fstatus == "not_possible":
            reason = finfo.get("reason", "Required data not available.")
            st.markdown(
                f'<span style="color: {RED}; font-size: 0.8rem;">'
                f'{reason}</span>',
                unsafe_allow_html=True,
            )

# Signal rules
st.markdown(
    f'<p style="color: {TEXT_DIM}; font-size: 0.8rem; margin-bottom: 0.25rem;">'
    f'Signal Rules</p>',
    unsafe_allow_html=True,
)

for rule in spec.get("signal_rules", []):
    signal_val = rule.get("signal", 0)
    if signal_val == 1:
        sig_color = GREEN
        sig_label = "+1 LONG"
    elif signal_val == -1:
        sig_color = RED
        sig_label = "-1 SHORT"
    else:
        sig_color = TEXT_DIM
        sig_label = "0 FLAT"

    with st.container(border=True):
        col_signal, col_condition = st.columns([1, 4])
        with col_signal:
            st.markdown(
                f'<span style="color: {sig_color}; font-weight: 700; '
                f'font-size: 1rem;">{sig_label}</span>',
                unsafe_allow_html=True,
            )
        with col_condition:
            condition = rule.get("condition", "")
            st.latex(condition)

        rationale = rule.get("rationale", "")
        if rationale:
            st.markdown(f"*{rationale}*")

# Parameters
params = spec.get("parameters", {})
if params:
    st.markdown(
        f'<p style="color: {TEXT_DIM}; font-size: 0.8rem; margin-bottom: 0.25rem;">'
        f'Parameters</p>',
        unsafe_allow_html=True,
    )
    params_html = "".join(
        f'<div style="display: inline-block; margin-right: 1.5rem;">'
        f'<span style="color: {TEXT_DIM}; font-size: 0.8rem;">{k}:</span> '
        f'<span style="color: {TEXT_PRIMARY}; font-weight: 600;">{v}</span></div>'
        for k, v in params.items()
    )
    st.markdown(_card(params_html), unsafe_allow_html=True)

# Not feasible: stop here
if not feasibility.get("feasible"):
    st.markdown(
        _card(
            f'<p style="color: {RED}; font-size: 0.95rem; margin: 0; font-weight: 600;">'
            f'Cannot proceed -- this strategy requires data we do not have.</p>'
            f'<p style="color: {TEXT_SECONDARY}; font-size: 0.85rem; margin: 0.5rem 0 0 0;">'
            f'The features marked "Missing" above require raw data sources '
            f'that are not in our warehouse. To proceed, those data sources would '
            f'need to be added to the ETL pipeline first.</p>',
            border_color=f"{RED}44",
        ),
        unsafe_allow_html=True,
    )
    st.stop()

# ---------------------------------------------------------------------------
# Step 4: Save & Run
# ---------------------------------------------------------------------------
st.markdown("---")

col_save, col_spacer4 = st.columns([1, 3])
with col_save:
    save_clicked = st.button(
        "Save & Run",
        type="primary",
        width="stretch",
    )

if save_clicked:
    code = st.session_state.get("paper_code", "")
    save_strategy(code, spec.get("title", "paper_strategy"))

    # Derive display name using same slug→title logic as discovery.py
    _slug = spec["title"].lower().replace(" ", "_").replace("-", "_")
    _slug = "".join(c for c in _slug if c.isalnum() or c == "_")
    _display = _slug.replace("_", " ").title()

    # Navigate to backtester with auto-run
    st.session_state["paper_auto_run"] = {
        "strategy_name": _display,
        "ticker_name": resolved_ticker or "Corn",
    }
    st.switch_page("pages/1_Strategy_Backtester.py")
