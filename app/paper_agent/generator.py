"""Generate a runnable strategy module from a spec and feasibility report.

Takes the quant-approved strategy spec and feature mapping, sends them to
DeepSeek with an example strategy template, and returns complete Python source
code that follows the generate_signal interface.
"""

import json
import logging
import time
from pathlib import Path

logger = logging.getLogger(__name__)

MODEL = "deepseek-chat"
MAX_TOKENS = 4096
BASE_URL = "https://api.deepseek.com"

STRATEGIES_DIR = Path(__file__).resolve().parents[2] / "strategies"

# Load the weather_precipitation strategy as a reference template
_TEMPLATE_PATH = STRATEGIES_DIR / "weather_precipitation.py"


def _load_template() -> str:
    """Load the reference strategy template."""
    if _TEMPLATE_PATH.exists():
        return _TEMPLATE_PATH.read_text()
    return ""


def _build_generation_prompt(spec: dict, feasibility: dict) -> str:
    """Build the system prompt for strategy code generation.

    Args:
        spec: Strategy spec from the extractor (with quant edits).
        feasibility: Feasibility report from the mapper (with quant approvals).

    Returns:
        System prompt string.
    """
    template = _load_template()

    # Separate features by status
    in_store = []
    derivable = []
    for f in feasibility.get("features", []):
        if f.get("status") == "in_store" and not f.get("skipped"):
            in_store.append(f)
        elif f.get("status") == "derivable" and not f.get("skipped"):
            derivable.append(f)

    # Determine FEATURES dict contents
    ticker_categories = set()
    unlinked = []
    for f in in_store:
        cat = f.get("store_category", "")
        entity = f.get("store_entity", "")
        if cat in ("momentum", "mean_reversion"):
            ticker_categories.add(cat)
        elif cat == "weather" and entity:
            entry = {"category": "weather", "entity": entity}
            if entry not in unlinked:
                unlinked.append(entry)

    # Derivable weather features also need the weather category for date alignment
    for f in derivable:
        table = f.get("raw_table", "")
        if table == "weather_daily":
            entry = {"category": "weather", "entity": "corn_belt"}
            if entry not in unlinked:
                unlinked.append(entry)

    features_dict = {
        "ticker_categories": sorted(ticker_categories),
        "unlinked": unlinked,
    }

    return f"""\
You are a Python developer generating a trading strategy module. Write clean, \
production-quality Python code that follows the exact interface shown in the \
TEMPLATE below.

TEMPLATE (for interface reference only -- do NOT copy this strategy's logic):
```python
{template}
```

INTERFACE CONTRACT:
- Module-level constants for all thresholds (UPPER_SNAKE_CASE)
- FEATURES dict declaring what feature store data to load
- SUMMARY string (one-line description)
- generate_signal(df) function that:
  - Takes a DataFrame with Close + feature columns
  - Returns the same DataFrame with an added "signal" column (+1, -1, or 0)
  - Handles NaN by setting signal to 0
  - Calls df.copy() at the start

STRATEGY SPEC:
{json.dumps(spec, indent=2)}

FEATURE MAPPING:
Features from store (already in df):
{json.dumps(in_store, indent=2)}

Features to derive inline (need computation):
{json.dumps(derivable, indent=2)}

FEATURES DICT TO USE:
{json.dumps(features_dict, indent=2)}

RULES:
- For "in_store" features, use the column name from store_column directly \
(it is already in the DataFrame).
- For "derivable" features, add a helper function that loads raw data using \
etl.db.load_raw_data(table, entity_col, entity_val) and computes the feature. \
Import: "from etl.db import load_raw_data". Call the helper at the top of \
generate_signal and assign the result onto df as a new column.
- Add "import pandas as pd" if needed for derivable features.
- Use the signal_rules from the spec for the signal logic.
- Add a module docstring attributing the paper and noting any derivations or \
approximations.
- Do NOT include any if __name__ == "__main__" block.
- Do NOT add comments saying "AI-generated" or similar.
- Output ONLY the Python code, no markdown fences or explanations.

CRITICAL DATA CONVENTIONS (follow exactly):
- The input df has a DatetimeIndex named "date". It does NOT have a "date" column. \
To join derived data, set the derived Series index to datetime and assign directly: \
df["new_col"] = derived_series (pandas aligns on index automatically). \
Do NOT use pd.merge(df, ..., on="date") because "date" is the index, not a column.
- Weather states in the database are capitalized: "Iowa", "Illinois", "Nebraska". \
Always use capitalized state names with load_raw_data.
- For Corn Belt aggregation: load each state, set_index to datetime date, \
concat on axis=1, then .mean(axis=1).
- Rolling windows must use the default min_periods (equal to window size) to ensure \
point-in-time correctness. Do NOT use min_periods=1.
- POINT-IN-TIME LAG RULES:
  1. Features from the feature store (columns already in the input df) are \
already point-in-time. The feature pipeline shifts all features by 1 day, \
so on date T the value reflects data through T-1. Do NOT shift them again.
  2. Derived features computed inline from raw warehouse data (via load_raw_data) \
bypass the feature pipeline and are NOT shifted. You MUST shift these by 1 day \
using .shift(1) before use in signal logic. Add a comment explaining the lag.
  3. Price features (Close, SMA, RSI, etc.) do NOT need a lag because the close \
price at day T is the exact moment the signal is generated.
- The backtest engine does NOT add a position lag. Signals execute on the same day \
they are computed. The feature pipeline's 1-day shift is the only lag in the system."""


def generate_strategy_code(spec: dict, feasibility: dict, api_key: str) -> str:
    """Generate a strategy module from the spec and feasibility report.

    Args:
        spec: Strategy spec from the extractor (with quant edits).
        feasibility: Feasibility report from the mapper (with quant approvals).
        api_key: DeepSeek API key.

    Returns:
        Complete Python source code as a string, or an error message
        prefixed with "ERROR: ".
    """
    from openai import OpenAI, APIError

    system_prompt = _build_generation_prompt(spec, feasibility)

    client = OpenAI(api_key=api_key, base_url=BASE_URL)

    t0 = time.monotonic()
    try:
        response = client.chat.completions.create(
            model=MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": "Generate the strategy module now."},
            ],
            max_tokens=MAX_TOKENS,
        )
    except APIError:
        logger.exception("DeepSeek API error during code generation")
        return "ERROR: Failed to reach the AI service. Please try again."
    duration = time.monotonic() - t0

    try:
        from app.ai_usage import log_usage
        usage = response.usage
        log_usage("deepseek", MODEL, "paper_generator",
                  usage.prompt_tokens, usage.completion_tokens,
                  duration_s=round(duration, 2))
    except Exception:
        pass

    code = response.choices[0].message.content.strip()

    # Strip markdown code fences if present
    if code.startswith("```"):
        lines = code.split("\n")
        lines = [line for line in lines[1:] if line.strip() != "```"]
        code = "\n".join(lines).strip()

    # Validate syntax
    try:
        compile(code, "<generated>", "exec")
    except SyntaxError as e:
        logger.error("Generated code has syntax error: %s", e)
        return f"ERROR: Generated code has a syntax error on line {e.lineno}: {e.msg}"

    return code


def save_strategy(code: str, name: str) -> Path:
    """Save generated strategy code to the strategies directory.

    Args:
        code: Python source code string.
        name: Strategy name (will be snake_cased for the filename).

    Returns:
        Path to the saved file.
    """
    slug = name.lower().replace(" ", "_").replace("-", "_")
    # Remove non-alphanumeric chars except underscores
    slug = "".join(c for c in slug if c.isalnum() or c == "_")
    path = STRATEGIES_DIR / f"{slug}.py"

    path.write_text(code)
    logger.info("Saved strategy to %s", path)
    return path
