"""Paper Upload -- extract strategies from research papers.

Four-step pipeline using tabs: select a paper, extract strategy and check
data feasibility, review generated code, and save as a runnable strategy
module. Users can navigate freely between completed steps."""

import sys
from pathlib import Path

import streamlit as st

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.paper_agent.extractor import DEMO_PAPERS, extract_strategy, load_demo_paper
from app.paper_agent.generator import generate_strategy_code, save_strategy
from app.paper_agent.mapper import map_features
from app.style import (
    inject_css, sidebar_logo,
    ACCENT, ACCENT_DIM, BG_CARD, BG_CARD_SOLID, BORDER, BORDER_SUBTLE,
    TEXT_PRIMARY, TEXT_SECONDARY, TEXT_DIM, TEXT_FAINT,
    GREEN, RED, AMBER, BADGE,
)

inject_css()
sidebar_logo()

# ---------------------------------------------------------------------------
# API key
# ---------------------------------------------------------------------------
_api_key = ""
try:
    _api_key = st.secrets["DEEPSEEK_API_KEY"]
except (KeyError, FileNotFoundError):
    pass


# ---------------------------------------------------------------------------
# Demo paper feasibility labels
# ---------------------------------------------------------------------------
DEMO_FEASIBILITY = {
    "Demo 1: Precipitation Stress Signals (derivable)": True,
    "Demo 2: Soil Moisture & NDVI (not possible)": False,
}

DEMO_DISPLAY_NAMES = {}
for key in DEMO_PAPERS:
    is_feasible = DEMO_FEASIBILITY.get(key, None)
    if is_feasible is True:
        DEMO_DISPLAY_NAMES[key] = f"{key}  --  Feasible"
    elif is_feasible is False:
        DEMO_DISPLAY_NAMES[key] = f"{key}  --  Not Feasible"
    else:
        DEMO_DISPLAY_NAMES[key] = key

DISPLAY_TO_KEY = {v: k for k, v in DEMO_DISPLAY_NAMES.items()}


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


def _step_label(num: int, title: str, done: bool) -> str:
    """Build a tab label with a completion indicator."""
    check = "  [done]" if done else ""
    return f"Step {num}: {title}{check}"


def _clear_downstream(from_step: int):
    """Clear session state for all steps after from_step."""
    keys_by_step = {
        1: ["paper_spec", "paper_feasibility"],
        2: ["paper_code"],
        3: ["paper_saved_path"],
    }
    for step in range(from_step, 4):
        for key in keys_by_step.get(step, []):
            st.session_state.pop(key, None)


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

# ---------------------------------------------------------------------------
# Determine which steps are complete
# ---------------------------------------------------------------------------
has_spec = "paper_spec" in st.session_state
has_feasibility = "paper_feasibility" in st.session_state
has_code = "paper_code" in st.session_state
has_saved = "paper_saved_path" in st.session_state

# ---------------------------------------------------------------------------
# Tabs for each step
# ---------------------------------------------------------------------------
tab1, tab2, tab3, tab4 = st.tabs([
    _step_label(1, "Select Paper", has_spec),
    _step_label(2, "Strategy & Feasibility", has_spec and has_feasibility),
    _step_label(3, "Review Code", has_code),
    _step_label(4, "Saved", has_saved),
])

# ===== TAB 1: Select Paper ================================================
with tab1:
    selected_display = st.selectbox(
        "Demo Paper",
        list(DEMO_DISPLAY_NAMES.values()),
        label_visibility="collapsed",
        format_func=lambda x: x,
    )
    selected_demo = DISPLAY_TO_KEY[selected_display]

    is_feasible = DEMO_FEASIBILITY.get(selected_demo)
    if is_feasible is True:
        st.markdown(
            f'<span style="color: {GREEN}; font-size: 0.82rem; font-weight: 600;">'
            f'Feasible</span>'
            f'<span style="color: {TEXT_DIM}; font-size: 0.82rem;">'
            f' -- we have all the required data in our warehouse</span>',
            unsafe_allow_html=True,
        )
    elif is_feasible is False:
        st.markdown(
            f'<span style="color: {RED}; font-size: 0.82rem; font-weight: 600;">'
            f'Not Feasible</span>'
            f'<span style="color: {TEXT_DIM}; font-size: 0.82rem;">'
            f' -- requires data sources we don\'t have (e.g. satellite imagery)</span>',
            unsafe_allow_html=True,
        )

    st.markdown(
        f'<div style="background: {BG_CARD}; border: 1px solid {BORDER}; '
        f'border-radius: 8px; padding: 0.75rem 1rem; margin: 0.5rem 0 1rem 0;">'
        f'<div style="color: {TEXT_DIM}; font-size: 0.78rem; line-height: 1.6;">'
        f'<span style="color: {GREEN}; font-weight: 600;">Feasible</span> = '
        f'all features can be built from data already in our warehouse '
        f'(price, weather, pre-computed features). '
        f'<span style="color: {RED}; font-weight: 600;">Not Feasible</span> = '
        f'the paper requires external data we don\'t have '
        f'(e.g. soil moisture sensors, NDVI satellite data).'
        f'</div></div>',
        unsafe_allow_html=True,
    )

    paper_text = load_demo_paper(selected_demo)
    with st.expander("Paper Preview", expanded=False):
        st.markdown(
            f'<div style="color: {TEXT_SECONDARY}; font-size: 0.85rem; '
            f'line-height: 1.7; white-space: pre-wrap; font-family: inherit;">'
            f'{paper_text}</div>',
            unsafe_allow_html=True,
        )

    col_extract, col_spacer = st.columns([1, 3])
    with col_extract:
        extract_clicked = st.button(
            "Extract & Analyze",
            type="primary",
            width="stretch",
        )

    if extract_clicked:
        # Clear old results if user re-extracts
        _clear_downstream(1)

        with st.status("Extracting strategy from paper...", expanded=True) as status:
            st.write("Sending paper text to AI for extraction...")
            spec = extract_strategy(paper_text, _api_key)
            if spec.get("error"):
                status.update(label="Extraction failed", state="error")
                st.error(spec["error"])
            else:
                st.write(f"Extracted: **{spec.get('title', 'Untitled')}**")
                st.write("Checking data feasibility...")
                feasibility = map_features(spec, _api_key)
                if feasibility.get("error"):
                    status.update(label="Feasibility check failed", state="error")
                    st.error(feasibility["error"])
                else:
                    st.session_state["paper_spec"] = spec
                    st.session_state["paper_feasibility"] = feasibility
                    st.session_state["paper_demo"] = selected_demo
                    n_ok = feasibility.get("store_count", 0) + feasibility.get("derivable_count", 0)
                    n_miss = feasibility.get("not_possible_count", 0)
                    st.write(f"Features: {n_ok} available, {n_miss} missing")
                    status.update(label="Extraction complete", state="complete")
                    st.toast("Switch to Step 2 to review results")

# ===== TAB 2: Strategy & Data Feasibility ==================================
with tab2:
    if not has_spec or not has_feasibility:
        st.markdown(
            f'<p style="color: {TEXT_FAINT}; margin-top: 1rem;">'
            f'Complete Step 1 first -- select a paper and click Extract & Analyze.</p>',
            unsafe_allow_html=True,
        )
    else:
        spec = st.session_state["paper_spec"]
        feasibility = st.session_state["paper_feasibility"]

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

        # Overall feasibility banner
        if feasibility.get("feasible"):
            banner_color = GREEN
            banner_label = "FEASIBLE"
            banner_text = "All required features are available. You can generate this strategy."
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
            status = finfo.get("status", "unknown")

            with st.container(border=True):
                # Header: badge + name + role
                if status == "in_store":
                    badge_html = _status_badge("In Store", GREEN)
                elif status == "derivable":
                    badge_html = _status_badge("Derivable", ACCENT)
                elif status == "not_possible":
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

                # Formula (LaTeX) if present
                formula = feat.get("formula", "")
                if formula:
                    st.latex(formula)

                # Computation description
                computation = feat.get("computation", "")
                if computation:
                    st.markdown(f"*{computation}*")

                # Data status detail
                if status == "in_store":
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
                elif status == "derivable":
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
                elif status == "not_possible":
                    reason = finfo.get("reason",
                                       "Required data not available.")
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

        # Confidence notes
        notes = spec.get("confidence_notes", "")
        if notes:
            st.markdown(
                _card(
                    f'<p style="color: {AMBER}; font-size: 0.85rem; margin: 0;">'
                    f'AI Note: {notes}</p>',
                    border_color=f"{AMBER}33",
                ),
                unsafe_allow_html=True,
            )

        # Not feasible warning or generate button
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
        else:
            col_gen, col_spacer3 = st.columns([1, 3])
            with col_gen:
                gen_clicked = st.button(
                    "Generate Strategy",
                    type="primary",
                    width="stretch",
                )

            if gen_clicked:
                _clear_downstream(2)
                with st.status("Generating strategy code...", expanded=True) as status:
                    st.write("Building strategy module from spec...")
                    code = generate_strategy_code(spec, feasibility, _api_key)
                    if code.startswith("ERROR:"):
                        status.update(label="Code generation failed", state="error")
                        st.error(code)
                    else:
                        st.session_state["paper_code"] = code
                        status.update(label="Code generated", state="complete")
                        st.toast("Switch to Step 3 to review and edit")

# ===== TAB 3: Review & Edit Code ==========================================
with tab3:
    if not has_code:
        st.markdown(
            f'<p style="color: {TEXT_FAINT}; margin-top: 1rem;">'
            f'Complete Step 2 first -- review the strategy and click Generate.</p>',
            unsafe_allow_html=True,
        )
    else:
        spec = st.session_state["paper_spec"]

        slug = spec.get("title", "strategy").lower().replace(" ", "_").replace("-", "_")
        slug = "".join(c for c in slug if c.isalnum() or c == "_")
        st.markdown(
            f'<p style="color: {TEXT_DIM}; font-size: 0.8rem;">'
            f'Will save to: <code>strategies/{slug}.py</code></p>',
            unsafe_allow_html=True,
        )

        edited_code = st.text_area(
            "Strategy Code",
            value=st.session_state["paper_code"],
            height=500,
            label_visibility="collapsed",
            key="code_editor",
        )

        st.session_state["paper_code"] = edited_code

        # Syntax check
        try:
            compile(edited_code, "<editor>", "exec")
            st.markdown(
                f'<p style="color: {GREEN}; font-size: 0.8rem;">Syntax OK</p>',
                unsafe_allow_html=True,
            )
            syntax_ok = True
        except SyntaxError as e:
            st.error(f"Syntax error on line {e.lineno}: {e.msg}")
            syntax_ok = False

        col_save, col_spacer4 = st.columns([1, 3])
        with col_save:
            save_clicked = st.button(
                "Save Strategy",
                type="primary",
                width="stretch",
                disabled=not syntax_ok,
            )

        if save_clicked:
            try:
                path = save_strategy(edited_code, spec.get("title", "paper_strategy"))
                st.session_state["paper_saved_path"] = str(path)
                st.toast("Strategy saved -- see Step 4")
                st.rerun()
            except FileExistsError as e:
                st.error(str(e))

# ===== TAB 4: Saved ========================================================
with tab4:
    if not has_saved:
        st.markdown(
            f'<p style="color: {TEXT_FAINT}; margin-top: 1rem;">'
            f'Complete Step 3 first -- review the code and click Save.</p>',
            unsafe_allow_html=True,
        )
    else:
        spec = st.session_state["paper_spec"]
        feasibility = st.session_state.get("paper_feasibility", {})

        log_parts = []
        for f in feasibility.get("features", []):
            s = f.get("status", "")
            if s == "in_store":
                log_parts.append(
                    f'<div style="color: {TEXT_SECONDARY}; font-size: 0.8rem;">'
                    f'From store: {f.get("store_column", f.get("store_feature", ""))}</div>'
                )
            elif s == "derivable":
                log_parts.append(
                    f'<div style="color: {TEXT_SECONDARY}; font-size: 0.8rem;">'
                    f'Derived: {f.get("paper_feature", "")} '
                    f'({f.get("derivation", "")})</div>'
                )
            elif s == "not_possible":
                log_parts.append(
                    f'<div style="color: {RED}; font-size: 0.8rem;">'
                    f'Skipped: {f.get("paper_feature", "")}</div>'
                )

        log_html = "".join(log_parts)

        st.markdown(
            _card(
                f'<div style="color: {GREEN}; font-weight: 600; font-size: 1rem; '
                f'margin-bottom: 0.75rem;">Strategy saved to the Backtester.</div>'
                f'<div style="color: {TEXT_SECONDARY}; font-size: 0.88rem; '
                f'margin-bottom: 0.75rem;">'
                f'Select "{spec.get("title", "")}" from the sidebar to backtest it.</div>'
                f'<div style="border-top: 1px solid {BORDER_SUBTLE}; padding-top: 0.5rem; '
                f'margin-top: 0.5rem;">'
                f'<div style="color: {TEXT_DIM}; font-size: 0.75rem; font-weight: 600; '
                f'margin-bottom: 0.3rem;">Generation Log</div>'
                f'<div style="color: {TEXT_SECONDARY}; font-size: 0.8rem;">'
                f'Source: {st.session_state.get("paper_demo", "uploaded paper")}</div>'
                f'{log_html}'
                f'</div>',
                border_color=f"{GREEN}33",
            ),
            unsafe_allow_html=True,
        )

        st.page_link(
            "pages/1_Backtester.py",
            label="Go to Backtester",
            width="content",
        )
