"""Trade post-mortem analyst powered by Claude Haiku with web search.

Identifies the best and worst trades from a backtest, uses Claude with
web search to research what happened in commodity markets during those
periods, and returns a narrative summary with cited sources. No Streamlit
imports -- pure functions and one API entry point."""

import logging
import re

import pandas as pd

logger = logging.getLogger(__name__)

MODEL = "claude-haiku-4-5-20251001"
MAX_TOKENS = 4096

SYSTEM_PROMPT = """You are a commodities market analyst writing a post-mortem on \
{commodity} futures ({ticker}) trades.

For each trade below, search for news, USDA reports, weather events, export data, \
trade policy changes, supply/demand shifts, or any other factors that moved \
{commodity} prices during that period.

FORMAT RULES (follow exactly):
- Start each trade section with a markdown heading: ### Best Trade #1, ### Worst Trade #2, etc.
- Do NOT restate the trade details (dates, prices, P&L) -- the user already sees those. \
Jump straight into the analysis.
- Write 2-4 sentences explaining the key price drivers. Include specific numbers \
(e.g. "rainfall was 40% below the 30-year average", "USDA cut yield estimates by \
3.2 bushels/acre", "exports surged 18% month-over-month").
- CRITICAL: Every factual claim MUST have an inline source citation as a markdown link \
immediately after the claim, like: "USDA cut yield estimates by 3.2 bu/acre \
([USDA WASDE Report](url))." Do NOT list sources at the end -- weave them into \
the sentences as evidence. If you cannot find a source for a claim, do not make it.
- After all trades, add a brief "### Patterns" section noting any themes across trades.

Be factual and specific. Every claim about a market event should have a number and a source."""


def select_notable_trades(trade_log: pd.DataFrame, n: int = 2) -> pd.DataFrame:
    """Select the best and worst trades by P&L from a trade log.

    Args:
        trade_log: DataFrame with at least entry_price, exit_price, pnl columns.
        n: Number of best and worst trades to select.

    Returns:
        DataFrame with notable trades, sorted best-first then worst-first,
        with added label and pct_change columns. Empty DataFrame if no trades.
    """
    if trade_log.empty:
        return pd.DataFrame()

    available = min(n, len(trade_log))
    sorted_log = trade_log.sort_values("pnl", ascending=False)

    best = sorted_log.head(available).copy()
    worst = sorted_log.tail(available).iloc[::-1].copy()

    best["label"] = [f"Best Trade #{i + 1}" for i in range(len(best))]
    worst["label"] = [f"Worst Trade #{i + 1}" for i in range(len(worst))]

    # Drop duplicates if fewer trades than 2*n
    notable = pd.concat([best, worst]).drop_duplicates(
        subset=["entry_date", "exit_date", "pnl"]
    )

    notable["pct_change"] = (
        (notable["exit_price"] - notable["entry_price"]) / notable["entry_price"] * 100
    )

    return notable.reset_index(drop=True)


def build_trade_context(
    notable_trades: pd.DataFrame, ticker: str, commodity: str
) -> str:
    """Format notable trades into a user message for the API call.

    Args:
        notable_trades: DataFrame from select_notable_trades.
        ticker: Ticker symbol (e.g. "ZC=F").
        commodity: Commodity name (e.g. "Corn").

    Returns:
        Formatted string with trade details.
    """
    lines = [
        f"Analyze the following {commodity} futures ({ticker}) trades and explain "
        f"why prices moved during each period:\n"
    ]

    for _, row in notable_trades.iterrows():
        entry = pd.to_datetime(row["entry_date"]).strftime("%Y-%m-%d")
        exit_ = pd.to_datetime(row["exit_date"]).strftime("%Y-%m-%d")
        direction = row.get("direction", "long")
        if direction == "long":
            action_entry, action_exit = "Bought", "Sold"
        else:
            action_entry, action_exit = "Shorted", "Covered"
        lines.append(
            f"**{row['label']}** ({direction})\n"
            f"  {action_entry} on {entry} at ${row['entry_price']:.2f}\n"
            f"  {action_exit} on {exit_} at ${row['exit_price']:.2f}\n"
            f"  P&L: ${row['pnl']:,.2f} | Change: {row['pct_change']:.2f}%\n"
            f"  Holding: {int(row['holding_days'])} days\n"
        )

    return "\n".join(lines)


def parse_response(response) -> dict:
    """Extract narrative text and split into per-trade sections.

    Splits the full narrative on ### headings so each trade (and a
    Patterns section) gets its own text block keyed by label.

    Args:
        response: Anthropic Messages response object.

    Returns:
        Dict with:
        - narrative: full text (str)
        - sections: dict mapping label -> text (e.g. "Best Trade #1" -> "...")
        - citations: list of dicts with title, url
        - section_citations: dict mapping section key -> list of citation dicts
    """
    # Collect all search result URLs and narrative text
    narrative_parts = []
    all_search_results = []

    for block in response.content:
        logger.debug("Post-mortem: response block type=%s", block.type)

        if block.type == "web_search_tool_result":
            if hasattr(block, "content") and block.content:
                for item in block.content:
                    url = getattr(item, "url", None)
                    title = getattr(item, "title", "")
                    if url:
                        all_search_results.append({"title": title, "url": url})

        elif block.type == "text":
            narrative_parts.append(block.text)

    full_narrative = "\n".join(narrative_parts)

    # Deduplicate search results
    seen_urls = set()
    unique_results = []
    for r in all_search_results:
        if r["url"] not in seen_urls:
            seen_urls.add(r["url"])
            unique_results.append(r)

    # Split on ### headings into per-trade sections
    sections = {}
    parts = re.split(r"(?=^###\s+)", full_narrative, flags=re.MULTILINE)
    for part in parts:
        part = part.strip()
        if not part:
            continue
        heading_match = re.match(r"^###\s+(.+?)(?:\n|$)", part)
        if heading_match:
            key = heading_match.group(1).strip()
            body = part[heading_match.end():].strip()
            sections[key] = body
        else:
            if part:
                sections["_preamble"] = part

    # Match citations to sections by keyword relevance
    STOP_WORDS = {
        "the", "a", "an", "and", "or", "but", "in", "on", "at", "to",
        "for", "of", "with", "by", "from", "as", "is", "was", "were",
        "are", "be", "been", "being", "have", "has", "had", "do", "does",
        "did", "will", "would", "could", "should", "may", "might", "can",
        "this", "that", "these", "those", "it", "its", "not", "no",
        "than", "more", "also", "which", "what", "when", "where", "how",
        "all", "each", "every", "both", "few", "some", "any", "most",
        "per", "up", "down", "out", "into", "over", "after", "before",
    }

    section_citations = {}
    for key, body in sections.items():
        if key == "_preamble":
            section_citations[key] = []
            continue

        words = set(
            w.lower() for w in re.findall(r"[A-Za-z]{3,}", body)
        ) - STOP_WORDS

        scored = []
        for r in unique_results:
            title_words = set(
                w.lower() for w in re.findall(r"[A-Za-z]{3,}", r["title"])
            )
            overlap = len(words & title_words)
            if overlap > 0:
                scored.append((overlap, r))

        scored.sort(key=lambda x: x[0], reverse=True)
        section_citations[key] = [r for _, r in scored[:5]]

    # Also extract markdown links from section text
    for key, body in sections.items():
        seen = {c["url"] for c in section_citations.get(key, [])}
        for match in re.finditer(r"\[([^\]]+)\]\((https?://[^\)]+)\)", body):
            title, url = match.group(1), match.group(2)
            if url not in seen:
                section_citations.setdefault(key, []).append(
                    {"title": title, "url": url}
                )
                seen.add(url)

    logger.info(
        "Post-mortem: parsed %d sections: %s, %d search results",
        len(sections), list(sections.keys()), len(unique_results),
    )
    for key, cites in section_citations.items():
        logger.info(
            "Post-mortem: section '%s' has %d citations", key, len(cites),
        )

    return {
        "narrative": full_narrative,
        "sections": sections,
        "section_citations": section_citations,
        "citations": unique_results,
    }


def analyze_trades(
    trade_log: pd.DataFrame, ticker: str, commodity: str, api_key: str
) -> dict:
    """Run AI post-mortem analysis on the best and worst trades.

    Selects notable trades, builds context, calls Claude Haiku with web search
    to research market events, and returns a narrative with sources.

    Args:
        trade_log: Full trade log DataFrame from a backtest.
        ticker: Ticker symbol (e.g. "ZC=F").
        commodity: Commodity name (e.g. "Corn").
        api_key: Anthropic API key.

    Returns:
        Dict with narrative (str), citations (list), trades (DataFrame),
        and error (str or None).
    """
    import anthropic

    logger.info("Post-mortem: selecting notable trades from %d total", len(trade_log))
    notable = select_notable_trades(trade_log)
    if notable.empty:
        logger.warning("Post-mortem: no trades to analyze")
        return {
            "narrative": "",
            "sections": {},
            "section_citations": {},
            "citations": [],
            "trades": notable,
            "error": "No trades to analyze.",
        }

    logger.info("Post-mortem: selected %d notable trades", len(notable))

    context = build_trade_context(notable, ticker, commodity)
    system = SYSTEM_PROMPT.format(commodity=commodity, ticker=ticker)

    client = anthropic.Anthropic(api_key=api_key)

    logger.info(
        "Post-mortem: calling Claude (%s) with web search for %s", MODEL, commodity,
    )
    try:
        response = client.messages.create(
            model=MODEL,
            system=system,
            messages=[{"role": "user", "content": context}],
            max_tokens=MAX_TOKENS,
            tools=[{"type": "web_search_20250305", "name": "web_search"}],
        )
    except anthropic.APIError as e:
        logger.exception("Post-mortem: Anthropic API error during trade analysis")
        return {
            "narrative": "",
            "sections": {},
            "section_citations": {},
            "citations": [],
            "trades": notable,
            "error": f"API error: {e.message}",
        }
    except Exception as e:
        logger.exception("Post-mortem: unexpected error during trade analysis")
        return {
            "narrative": "",
            "sections": {},
            "section_citations": {},
            "citations": [],
            "trades": notable,
            "error": f"Unexpected error: {e}",
        }

    # Log token usage
    try:
        from app.ai_usage import log_usage
        usage = response.usage
        log_usage("anthropic", MODEL, "trade_postmortem",
                  usage.input_tokens, usage.output_tokens)
    except Exception:
        logger.debug("Could not log AI usage", exc_info=True)

    logger.info("Post-mortem: parsing API response")
    parsed = parse_response(response)

    logger.info(
        "Post-mortem: complete -- narrative %d chars, %d citations",
        len(parsed["narrative"]), len(parsed["citations"]),
    )

    return {
        "narrative": parsed["narrative"],
        "sections": parsed["sections"],
        "section_citations": parsed["section_citations"],
        "citations": parsed["citations"],
        "trades": notable,
        "error": None,
    }
