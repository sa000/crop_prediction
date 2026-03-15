"""Generate ETL pipeline architecture diagram as PNG."""

import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch

fig, ax = plt.subplots(1, 1, figsize=(20, 14))
ax.set_xlim(0, 20)
ax.set_ylim(0, 14)
ax.axis("off")
fig.patch.set_facecolor("#0d1117")

# ── Color palette ──────────────────────────────────────────────
C_BG       = "#0d1117"
C_BORDER   = "#30363d"
C_API      = "#58a6ff"    # external APIs
C_SCRAPER  = "#bc8cff"    # scraper layer
C_LANDING  = "#f0883e"    # landing zone
C_VALIDATE = "#f778ba"    # validation
C_WAREHOUSE= "#3fb950"    # warehouse DB
C_FEATURE  = "#79c0ff"    # feature store
C_CONSUME  = "#d2a8ff"    # consumers
C_CONFIG   = "#8b949e"    # config files
C_TEXT     = "#e6edf3"
C_SUBTEXT  = "#8b949e"
C_ARROW    = "#58a6ff"
C_SECTION  = "#161b22"

def draw_box(x, y, w, h, label, sublabel=None, color=C_API, alpha=0.15, fontsize=10, sublabel_size=7.5):
    """Draw a rounded box with label."""
    rect = FancyBboxPatch(
        (x, y), w, h,
        boxstyle="round,pad=0.15",
        facecolor=color, edgecolor=color,
        alpha=alpha, linewidth=1.5, zorder=2,
    )
    ax.add_patch(rect)
    border = FancyBboxPatch(
        (x, y), w, h,
        boxstyle="round,pad=0.15",
        facecolor="none", edgecolor=color,
        alpha=0.6, linewidth=1.5, zorder=3,
    )
    ax.add_patch(border)
    ax.text(x + w / 2, y + h / 2 + (0.12 if sublabel else 0), label,
            ha="center", va="center", fontsize=fontsize,
            fontweight="bold", color=C_TEXT, zorder=4)
    if sublabel:
        ax.text(x + w / 2, y + h / 2 - 0.2, sublabel,
                ha="center", va="center", fontsize=sublabel_size,
                color=C_SUBTEXT, zorder=4, style="italic")

def draw_arrow(x1, y1, x2, y2, color=C_ARROW, style="-|>", lw=1.5):
    """Draw a curved arrow."""
    arrow = FancyArrowPatch(
        (x1, y1), (x2, y2),
        arrowstyle=style, color=color,
        linewidth=lw, mutation_scale=15,
        connectionstyle="arc3,rad=0.0",
        zorder=5, alpha=0.8,
    )
    ax.add_patch(arrow)

def draw_section(x, y, w, h, label, color=C_SECTION):
    """Draw a section background with label."""
    rect = FancyBboxPatch(
        (x, y), w, h,
        boxstyle="round,pad=0.2",
        facecolor=color, edgecolor=C_BORDER,
        alpha=0.5, linewidth=1, zorder=1,
    )
    ax.add_patch(rect)
    ax.text(x + 0.3, y + h - 0.3, label,
            ha="left", va="top", fontsize=8,
            fontweight="bold", color=C_SUBTEXT, zorder=4,
            fontstyle="italic")

# ── Title ──────────────────────────────────────────────────────
ax.text(10, 13.5, "ETL Pipeline Architecture", ha="center", va="center",
        fontsize=22, fontweight="bold", color=C_TEXT, zorder=10)
ax.text(10, 13.05, "Crop Yield Trading Strategy Platform", ha="center", va="center",
        fontsize=11, color=C_SUBTEXT, zorder=10)

# ── Section backgrounds ───────────────────────────────────────
draw_section(0.3, 10.2, 19.4, 2.5, "EXTERNAL DATA SOURCES")
draw_section(0.3, 7.4, 19.4, 2.5, "INGESTION & VALIDATION LAYER")
draw_section(0.3, 4.3, 19.4, 2.8, "STORAGE LAYER")
draw_section(0.3, 1.0, 19.4, 3.0, "FEATURE STORE & CONSUMERS")

# ═══════════════════════════════════════════════════════════════
# ROW 1: External APIs (y ~= 11.2)
# ═══════════════════════════════════════════════════════════════
draw_box(1.5, 11.0, 3.5, 1.2, "Yahoo Finance API", "OHLCV Futures Data", C_API)
draw_box(8.2, 11.0, 3.5, 1.2, "Open-Meteo API", "Temp / Precipitation", C_API)
draw_box(15.0, 11.0, 3.5, 1.2, "Config Files", "config.yaml / pipeline.yaml", C_CONFIG)

# ═══════════════════════════════════════════════════════════════
# ROW 2: Scrapers + Validation (y ~= 8.2)
# ═══════════════════════════════════════════════════════════════
draw_box(1.0, 8.2, 3.0, 1.2, "yahoo_finance.py", "Corn, Soybeans, Wheat", C_SCRAPER)
draw_box(4.8, 8.2, 3.0, 1.2, "open_meteo.py", "IA, IL, NE weather", C_SCRAPER)
draw_box(8.8, 8.2, 3.2, 1.2, "validate.py", "Clean / Reject split", C_VALIDATE)
draw_box(12.8, 8.2, 3.0, 1.0, "checks/", "generic, futures, weather", C_VALIDATE, sublabel_size=7)
draw_box(16.5, 8.2, 2.8, 1.0, "pipeline.yaml", "Thresholds & rules", C_CONFIG)

# ═══════════════════════════════════════════════════════════════
# ROW 3: Storage (y ~= 5.2)
# ═══════════════════════════════════════════════════════════════
draw_box(1.0, 5.2, 3.5, 1.4, "Landing Zone", "warehouse/landing/\nImmutable CSVs", C_LANDING, fontsize=10, sublabel_size=7.5)

draw_box(5.8, 5.0, 4.5, 1.8, "warehouse.db", "futures_daily  |  weather_daily\nvalidation_log  |  data_catalog\nfeature_catalog  |  strategies", C_WAREHOUSE, fontsize=11, sublabel_size=7.5)

draw_box(11.5, 5.2, 3.5, 1.4, "app.db", "backtest_runs\nshared_analyses | ai_usage", C_CONSUME, fontsize=10, sublabel_size=7.5)

draw_box(16.0, 5.2, 3.2, 1.4, "run_pipeline.py", "Orchestrator\n--rebuild mode", C_SCRAPER, fontsize=9, sublabel_size=7.5)

# Labels for DB separation
ax.text(8.05, 4.55, "Rebuildable (deleted on --rebuild)", ha="center", va="center",
        fontsize=6.5, color=C_WAREHOUSE, zorder=6, style="italic")
ax.text(13.25, 4.75, "Permanent (never deleted)", ha="center", va="center",
        fontsize=6.5, color=C_CONSUME, zorder=6, style="italic")

# ═══════════════════════════════════════════════════════════════
# ROW 4: Feature Store & Consumers (y ~= 2.0)
# ═══════════════════════════════════════════════════════════════
draw_box(1.0, 2.2, 3.0, 1.2, "features/pipeline.py", "Incremental / Rebuild", C_FEATURE)
draw_box(4.8, 1.5, 3.8, 2.2, "Feature Store", "Parquet files\nmomentum/ | mean_reversion/\nweather/ | metadata.parquet", C_FEATURE, fontsize=10, sublabel_size=7.5)

draw_box(9.5, 2.8, 2.8, 1.0, "Strategies", "generate_signal()", C_CONSUME, fontsize=9)
draw_box(9.5, 1.5, 2.8, 1.0, "Backtest Engine", "backtest.py", C_CONSUME, fontsize=9)

draw_box(13.2, 2.8, 3.0, 1.0, "Streamlit App", "5 pages + AI agents", C_CONSUME, fontsize=9)
draw_box(13.2, 1.5, 3.0, 1.0, "Data Explorer", "DuckDB queries", C_CONSUME, fontsize=9)

draw_box(17.0, 2.0, 2.2, 1.5, "query.py", "DuckDB SQL\nover Parquet", C_FEATURE, fontsize=9, sublabel_size=7)

# ═══════════════════════════════════════════════════════════════
# ARROWS
# ═══════════════════════════════════════════════════════════════

# APIs → Scrapers
draw_arrow(3.25, 11.0, 2.5, 9.4, C_API)
draw_arrow(9.95, 11.0, 6.3, 9.4, C_API)

# Config → Scrapers
draw_arrow(15.0, 11.5, 4.0, 9.2, C_CONFIG, lw=1.0)
draw_arrow(15.0, 11.3, 7.8, 9.2, C_CONFIG, lw=1.0)

# Scrapers → Landing
draw_arrow(2.5, 8.2, 2.5, 6.6, C_SCRAPER)
draw_arrow(6.3, 8.2, 3.5, 6.6, C_SCRAPER)

# Landing → Validation
draw_arrow(4.5, 5.9, 8.8, 8.8, C_LANDING, lw=1.2)

# Validation → Warehouse
draw_arrow(10.0, 8.2, 8.05, 6.8, C_VALIDATE)

# Checks → Validation
draw_arrow(12.8, 8.7, 12.0, 8.7, C_VALIDATE, lw=1.0)

# Pipeline config → Checks
draw_arrow(16.5, 8.7, 15.8, 8.7, C_CONFIG, lw=1.0)

# run_pipeline → warehouse
draw_arrow(17.6, 5.2, 10.3, 5.9, C_SCRAPER, lw=1.0)

# warehouse.db → features pipeline
draw_arrow(5.8, 5.5, 4.0, 3.2, C_WAREHOUSE)

# features pipeline → feature store
draw_arrow(4.0, 2.8, 4.8, 2.8, C_FEATURE)

# feature store → strategies
draw_arrow(8.6, 3.1, 9.5, 3.2, C_FEATURE, lw=1.2)

# feature store → query.py
draw_arrow(8.6, 2.3, 17.0, 2.6, C_FEATURE, lw=1.0)

# strategies → backtest
draw_arrow(10.9, 2.8, 10.9, 2.5, C_CONSUME, lw=1.0)

# backtest → app
draw_arrow(12.3, 2.0, 13.2, 2.0, C_CONSUME, lw=1.0)

# strategies → app
draw_arrow(12.3, 3.3, 13.2, 3.3, C_CONSUME, lw=1.0)

# warehouse → app.db (for app reads)
draw_arrow(10.3, 5.5, 11.5, 5.6, C_WAREHOUSE, lw=1.0)

# app.db → Streamlit
draw_arrow(13.25, 5.2, 14.5, 3.8, C_CONSUME, lw=1.0)

# query.py → data explorer
draw_arrow(17.0, 2.5, 16.2, 2.0, C_FEATURE, lw=1.0)

# ── Legend ─────────────────────────────────────────────────────
legend_y = 0.4
legend_items = [
    (C_API, "External API"),
    (C_SCRAPER, "Scraper / Runner"),
    (C_LANDING, "Landing Zone"),
    (C_VALIDATE, "Validation"),
    (C_WAREHOUSE, "Warehouse DB"),
    (C_FEATURE, "Feature Store"),
    (C_CONSUME, "Consumers / App"),
    (C_CONFIG, "Configuration"),
]
for i, (color, label) in enumerate(legend_items):
    lx = 1.5 + i * 2.3
    rect = FancyBboxPatch(
        (lx, legend_y), 0.3, 0.3,
        boxstyle="round,pad=0.05",
        facecolor=color, edgecolor=color,
        alpha=0.4, linewidth=1, zorder=2,
    )
    ax.add_patch(rect)
    ax.text(lx + 0.45, legend_y + 0.15, label, ha="left", va="center",
            fontsize=7, color=C_SUBTEXT, zorder=4)

plt.tight_layout(pad=0.5)
plt.savefig("docs/etl_architecture.png", dpi=200, facecolor=C_BG,
            bbox_inches="tight", pad_inches=0.3)
print("Saved → docs/etl_architecture.png")
