"""Feature catalog agent powered by Claude Haiku.

Builds a structured catalog context from the feature metadata Parquet,
sends it to Claude Haiku with a user question, and returns structured
JSON with an answer and matching features. No Streamlit imports.
"""

import json
import logging

import pandas as pd

logger = logging.getLogger(__name__)

MODEL = "claude-haiku-4-5-20251001"
MAX_TOKENS = 4096

SYSTEM_PROMPT = """You are a feature catalog assistant for an agricultural commodity futures \
trading platform. You help users discover and understand features available \
for alpha generation and signal derivation.

SCOPE: You ONLY answer questions about the feature catalog -- feature names, \
descriptions, statistics, date coverage, computation parameters, categories, \
and entities. If asked something outside this scope, respond with:
{{"answer": "I can only help with questions about the feature catalog. \
Try asking about available features, their descriptions, statistics, \
or coverage.", "features": []}}

RULES:
- Only reference features that exist in the catalog below
- When listing features, include ALL relevant matches
- For entity-specific questions (e.g. "corn"), filter to that entity
- Include summary statistics when asked about ranges or typical values
- Include computation parameters when asked how a feature is calculated
- Each feature entry must have EXACTLY ONE entity (not a comma-separated list)
- If a feature exists for multiple entities, return one entry per entity

Respond with ONLY valid JSON (no markdown code fences):
{{"answer": "Brief natural language answer",
 "features": [{{"name": "...", "category": "...", "entity": "...", \
"description": "..."}}]}}

CATALOG:
{catalog_context}"""


def build_catalog_context(metadata_df: pd.DataFrame) -> str:
    """Format the metadata DataFrame as structured text grouped by category.

    Args:
        metadata_df: Feature metadata with columns: name, category, entity,
            description, params, stat_min, stat_max, stat_mean, stat_std,
            available_from, freshness.

    Returns:
        Formatted catalog string for injection into the system prompt.
    """
    if metadata_df.empty:
        return "(No features available)"

    lines = []
    for category, cat_group in metadata_df.groupby("category", sort=True):
        lines.append(f"\n## {category.replace('_', ' ').title()} Features\n")

        for entity, ent_group in cat_group.groupby("entity", sort=True):
            lines.append(f"### {entity}")

            for _, row in ent_group.iterrows():
                params_str = ""
                if pd.notna(row.get("params")):
                    try:
                        params = json.loads(row["params"])
                        params_str = ", ".join(f"{k}={v}" for k, v in params.items())
                    except (json.JSONDecodeError, TypeError):
                        params_str = str(row["params"])

                stat_parts = []
                if pd.notna(row.get("stat_min")) and pd.notna(row.get("stat_max")):
                    stat_parts.append(
                        f"Range: {row['stat_min']:.2f} - {row['stat_max']:.2f}"
                    )
                if pd.notna(row.get("stat_mean")):
                    mean_str = f"Mean: {row['stat_mean']:.2f}"
                    if pd.notna(row.get("stat_std")):
                        mean_str += f" +/- {row['stat_std']:.2f}"
                    stat_parts.append(mean_str)
                stats_str = " | ".join(stat_parts)

                avail = ""
                if pd.notna(row.get("available_from")) and pd.notna(row.get("freshness")):
                    avail = f"Available: {row['available_from']} to {row['freshness']}"

                lines.append(f"- {row['name']}: {row.get('description', '')}")
                detail_parts = []
                if params_str:
                    detail_parts.append(f"Params: {params_str}")
                if stats_str:
                    detail_parts.append(stats_str)
                if detail_parts:
                    lines.append(f"  {' | '.join(detail_parts)}")
                if avail:
                    lines.append(f"  {avail}")

            lines.append("")

    return "\n".join(lines)


def ask(question: str, metadata_df: pd.DataFrame, api_key: str) -> dict:
    """Send a catalog question to Claude Haiku and return structured results.

    Args:
        question: User's natural language question about features.
        metadata_df: Feature metadata DataFrame.
        api_key: Anthropic API key.

    Returns:
        Dict with "answer" (str) and "features" (list of dicts with
        name, category, entity, description).
    """
    import anthropic

    catalog_context = build_catalog_context(metadata_df)
    system = SYSTEM_PROMPT.format(catalog_context=catalog_context)

    client = anthropic.Anthropic(api_key=api_key)

    try:
        response = client.messages.create(
            model=MODEL,
            system=system,
            messages=[{"role": "user", "content": question}],
            max_tokens=MAX_TOKENS,
        )
    except anthropic.APIError:
        logger.exception("Anthropic API error")
        return {
            "answer": "Failed to reach the AI service. Please try again.",
            "features": [],
        }

    text = response.content[0].text.strip()

    # Strip markdown code fences if present
    if text.startswith("```"):
        lines = text.split("\n")
        # Remove first line (```json) and last line (```)
        lines = [l for l in lines[1:] if l.strip() != "```"]
        text = "\n".join(lines).strip()

    try:
        result = json.loads(text)
        if "answer" not in result:
            result["answer"] = text
        if "features" not in result:
            result["features"] = []
        return result
    except (json.JSONDecodeError, TypeError):
        return {"answer": text, "features": []}
