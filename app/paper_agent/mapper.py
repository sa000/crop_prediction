"""Map extracted features against available data and assess feasibility.

For each feature the paper requires, classifies it into one of three buckets:
- in_store: feature already exists in the feature store
- derivable: raw data exists in the warehouse to compute it
- not_possible: required raw data is not available

Uses an AI call with a constrained data catalog to handle semantic matching
between paper descriptions and our internal data schema.
"""

import json
import logging
from pathlib import Path

import yaml

logger = logging.getLogger(__name__)

MODEL = "deepseek-chat"
MAX_TOKENS = 4096
BASE_URL = "https://api.deepseek.com"

FEATURES_DIR = Path(__file__).resolve().parents[2] / "features"
REGISTRY_PATH = FEATURES_DIR / "registry.yaml"
CONFIG_PATH = FEATURES_DIR / "config.yaml"


def build_data_catalog() -> dict:
    """Build a catalog of all available data for feasibility checks.

    Reads from the feature registry (what's in the store) and the feature
    config (what raw data and compute functions exist).

    Returns:
        Dict with feature_store, warehouse, and compute_functions sections.
    """
    # Feature store contents
    registry = {}
    if REGISTRY_PATH.exists():
        with open(REGISTRY_PATH) as f:
            registry = yaml.safe_load(f) or {}

    features_list = registry.get("features", [])
    ticker_map = registry.get("ticker_feature_map", {})
    unlinked = registry.get("unlinked_features", {})

    # Feature config for raw data awareness
    config = {}
    if CONFIG_PATH.exists():
        with open(CONFIG_PATH) as f:
            config = yaml.safe_load(f) or {}

    # Build compute function list from config
    compute_functions = set()
    for cat_conf in config.values():
        for feat in cat_conf.get("features", []):
            compute_functions.add(feat["function"])

    return {
        "feature_store": {
            "features": features_list,
            "ticker_feature_map": ticker_map,
            "unlinked_features": unlinked,
        },
        "warehouse": {
            "futures_daily": {
                "description": "Daily OHLCV price data for agricultural futures",
                "columns": ["date", "ticker", "open", "high", "low", "close", "volume"],
                "entities": {"ticker": ["ZC=F (corn)", "ZS=F (soybeans)", "ZW=F (wheat)"]},
                "note": "Close price is always available in the strategy DataFrame",
            },
            "weather_daily": {
                "description": "Daily weather observations for Corn Belt states",
                "columns": ["date", "state", "temp_max_f", "temp_min_f", "precip_in"],
                "entities": {"state": ["Iowa", "Illinois", "Nebraska"]},
                "aggregations": {
                    "corn_belt": {
                        "method": "mean of Iowa, Illinois, Nebraska",
                        "description": "Corn Belt aggregate computed by averaging across states",
                    },
                },
                "note": "Raw weather columns are NOT in the strategy DataFrame. "
                        "Must be loaded via etl.db.load_raw_data().",
            },
        },
        "compute_functions": sorted(compute_functions),
    }


def _build_mapping_prompt(spec: dict, catalog: dict) -> str:
    """Build the system prompt for the AI mapping call.

    Args:
        spec: Strategy spec from the extractor.
        catalog: Data catalog from build_data_catalog().

    Returns:
        System prompt string.
    """
    catalog_text = json.dumps(catalog, indent=2, default=str)

    features_text = json.dumps(spec["required_features"], indent=2)

    return f"""\
You are a data engineer mapping research paper features to a trading platform's \
available data. You have access to a DATA CATALOG describing what data exists.

DATA CATALOG:
{catalog_text}

PAPER'S REQUIRED FEATURES:
{features_text}

For EACH required feature, classify it as one of:
1. "in_store" -- the feature already exists in the feature store (exact or very \
close match in computation and parameters)
2. "derivable" -- the feature does NOT exist in the store, but the raw data \
needed to compute it IS available in the warehouse tables
3. "not_possible" -- the raw data needed does NOT exist anywhere in our system

RULES:
- For "in_store": identify the exact feature name, category, and entity. \
When the feature store has a feature with the same computation type and parameters, \
that is an exact match. Include the column name as it appears in the strategy \
DataFrame (for unlinked/weather features this is prefixed with entity name, \
e.g. "corn_belt_precip_anomaly_30d").
- For "derivable": identify which raw table and column to use, and write a \
short Python code snippet showing how to derive it. Use \
etl.db.load_raw_data(table, entity_col, entity_val) to load raw data. \
For Corn Belt aggregation, load each state and average them.
- For "not_possible": explain what raw data is missing and why we cannot \
compute this feature.
- Be conservative: only mark "in_store" if the computation truly matches. \
A 7-day rolling sum is NOT the same as an 8-day rolling sum -- the 8-day \
version should be "derivable" since we have the raw daily data.

Respond with ONLY valid JSON (no markdown code fences):
{{
    "features": [
        {{
            "paper_feature": "name from the paper",
            "status": "in_store | derivable | not_possible",
            "store_feature": "feature name if in_store, else null",
            "store_column": "column name in strategy DataFrame if in_store, else null",
            "store_category": "category if in_store, else null",
            "store_entity": "entity if in_store, else null",
            "match_reason": "why this is a match if in_store, else null",
            "raw_table": "table name if derivable, else null",
            "raw_column": "column name if derivable, else null",
            "derivation": "human-readable derivation description if derivable, else null",
            "derivation_code": "Python code snippet if derivable, else null",
            "reason": "explanation if not_possible, else null"
        }}
    ]
}}"""


def map_features(spec: dict, api_key: str) -> dict:
    """Classify each required feature and produce a feasibility report.

    Args:
        spec: Strategy spec from the extractor.
        api_key: DeepSeek API key.

    Returns:
        Feasibility report dict with features list and summary counts.
    """
    from openai import OpenAI, APIError

    catalog = build_data_catalog()
    system_prompt = _build_mapping_prompt(spec, catalog)

    client = OpenAI(api_key=api_key, base_url=BASE_URL)

    try:
        response = client.chat.completions.create(
            model=MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": "Map each feature now."},
            ],
            max_tokens=MAX_TOKENS,
        )
    except APIError:
        logger.exception("DeepSeek API error during mapping")
        return {"error": "Failed to reach the AI service. Please try again."}

    try:
        from app.ai_usage import log_usage
        usage = response.usage
        log_usage("deepseek", MODEL, "paper_mapper",
                  usage.prompt_tokens, usage.completion_tokens)
    except Exception:
        pass

    text = response.choices[0].message.content.strip()

    if text.startswith("```"):
        lines = text.split("\n")
        lines = [line for line in lines[1:] if line.strip() != "```"]
        text = "\n".join(lines).strip()

    try:
        result = json.loads(text)
    except (json.JSONDecodeError, TypeError):
        logger.error("Failed to parse mapping response: %s", text[:200])
        return {"error": "AI returned invalid JSON. Try re-mapping."}

    features = result.get("features", [])

    store_count = sum(1 for f in features if f.get("status") == "in_store")
    derivable_count = sum(1 for f in features if f.get("status") == "derivable")
    not_possible_count = sum(1 for f in features if f.get("status") == "not_possible")

    # Feasible if all signal-role features are resolved (in_store or derivable)
    signal_features = [
        rf for rf in spec.get("required_features", [])
        if rf.get("role") == "signal"
    ]
    signal_names = {sf["name"] for sf in signal_features}

    feasible = True
    for f in features:
        if f["paper_feature"] in signal_names and f.get("status") == "not_possible":
            feasible = False
            break

    # If ANY feature is not_possible and there are no signal-role distinctions,
    # mark as not feasible
    if not signal_names and not_possible_count > 0:
        feasible = False

    return {
        "features": features,
        "feasible": feasible,
        "store_count": store_count,
        "derivable_count": derivable_count,
        "not_possible_count": not_possible_count,
        "catalog": catalog,
    }
