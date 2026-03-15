"""Extract strategy specifications from research paper text.

Sends paper text to DeepSeek with a structured extraction prompt. Returns a
strategy spec dict describing features, signal rules, and parameters as
the paper describes them -- without mapping to our internal categories.
"""

import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

MODEL = "deepseek-chat"
MAX_TOKENS = 4096
BASE_URL = "https://api.deepseek.com"

DEMOS_DIR = Path(__file__).resolve().parent / "demos"

DEMO_PAPERS = {
    "Demo 1: Precipitation Stress Signals (derivable)": "demo_1_derivable.txt",
    "Demo 2: Soil Moisture & NDVI (not possible)": "demo_2_not_possible.txt",
}

SYSTEM_PROMPT = """\
You are a quantitative research analyst. Given the text of a research paper \
describing a trading strategy for agricultural commodity futures, extract the \
strategy into structured JSON.

RULES:
- Only extract what the paper explicitly describes. Do not invent features or rules.
- Describe features in terms of what raw data they need and what computation \
  is applied. Do NOT classify them into internal system categories.
- If the paper is ambiguous about a parameter or rule, note it in confidence_notes.
- If the paper describes multiple strategies, extract the single most clearly \
  defined one.

Respond with ONLY valid JSON (no markdown code fences):
{
    "title": "strategy name derived from the paper",
    "thesis": "1-3 sentence summary of the trading thesis",
    "required_features": [
        {
            "name": "short descriptive name for this feature",
            "description": "what this feature represents",
            "raw_data_needed": "what underlying raw data is required (e.g. daily precipitation, closing price)",
            "computation": "how the feature is computed from raw data (e.g. 8-day rolling sum)",
            "formula": "LaTeX formula WITHOUT dollar-sign delimiters (e.g. P_{8d}(t) = \\sum_{i=0}^{7} \\text{precip}(t-i)). Use LaTeX syntax: subscripts with _{}, superscripts with ^{}, \\text{} for words, \\frac{}{} for fractions, \\sigma for sigma, \\mu for mu, etc. Leave empty string if no formula applies.",
            "parameters": {"window": 8},
            "role": "signal or filter or exit"
        }
    ],
    "signal_rules": [
        {
            "condition": "LaTeX formula for the condition WITHOUT dollar-sign delimiters (e.g. Z_{30d} < -1.5 \\;\\text{AND}\\; P_{8d} < 0.2). Use subscripts, operators, and \\text{AND}/\\text{OR} for logic.",
            "signal": 1,
            "rationale": "why this condition triggers this signal"
        }
    ],
    "parameters": {
        "param_name": "value (use numbers not strings for numeric values)"
    },
    "target_assets": ["corn futures"],
    "confidence_notes": "any caveats, ambiguities, or concerns about the extraction"
}"""


def load_demo_paper(demo_key: str) -> str:
    """Load a built-in demo paper by its display name.

    Args:
        demo_key: Key from DEMO_PAPERS dict.

    Returns:
        Paper text as a string.

    Raises:
        FileNotFoundError: If the demo file does not exist.
    """
    filename = DEMO_PAPERS[demo_key]
    path = DEMOS_DIR / filename
    return path.read_text()


def extract_strategy(paper_text: str, api_key: str) -> dict:
    """Send paper text to DeepSeek and return a structured strategy spec.

    Args:
        paper_text: Full text of the research paper.
        api_key: DeepSeek API key.

    Returns:
        Strategy spec dict with title, thesis, required_features,
        signal_rules, parameters, target_assets, confidence_notes.
    """
    from openai import OpenAI, APIError

    client = OpenAI(api_key=api_key, base_url=BASE_URL)

    try:
        response = client.chat.completions.create(
            model=MODEL,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": paper_text},
            ],
            max_tokens=MAX_TOKENS,
        )
    except APIError:
        logger.exception("DeepSeek API error during extraction")
        return {"error": "Failed to reach the AI service. Please try again."}

    try:
        from app.ai_usage import log_usage
        usage = response.usage
        log_usage("deepseek", MODEL, "paper_extractor",
                  usage.prompt_tokens, usage.completion_tokens)
    except Exception:
        pass

    text = response.choices[0].message.content.strip()

    # Strip markdown code fences if present
    if text.startswith("```"):
        lines = text.split("\n")
        lines = [line for line in lines[1:] if line.strip() != "```"]
        text = "\n".join(lines).strip()

    try:
        result = json.loads(text)
        # Validate required keys
        for key in ("title", "required_features", "signal_rules"):
            if key not in result:
                return {"error": f"Extraction missing required field: {key}"}
        return result
    except (json.JSONDecodeError, TypeError):
        logger.error("Failed to parse extraction response: %s", text[:200])
        return {"error": "AI returned invalid JSON. Try re-extracting."}
