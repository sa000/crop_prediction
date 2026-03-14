"""Strategy auto-discovery for the Streamlit app.

Scans the strategies/ directory for Python modules that expose a
generate_signal function, making them available for selection in the UI.
Syncs discovered strategies to the SQLite strategies table."""

import importlib
import inspect
import logging
import sqlite3
from pathlib import Path
from types import ModuleType

from etl.db import upsert_strategy, delete_strategy, list_strategies

logger = logging.getLogger(__name__)

STRATEGIES_DIR = Path(__file__).resolve().parents[1] / "strategies"
EXCLUDED_FILES = {"__init__.py", "backtest.py", "analytics.py", "robustness.py"}


def discover_strategies() -> dict[str, ModuleType]:
    """Find all strategy modules in the strategies/ directory.

    Imports each .py file (excluding infrastructure modules), checks for a
    callable generate_signal attribute, and returns a mapping of display
    names to loaded modules.

    Returns:
        Dict mapping display name to strategy module.
    """
    strategies = {}

    for path in sorted(STRATEGIES_DIR.glob("*.py")):
        if path.name in EXCLUDED_FILES:
            continue

        module_name = f"strategies.{path.stem}"
        try:
            module = importlib.import_module(module_name)
        except Exception:
            logger.warning("Failed to import %s", module_name, exc_info=True)
            continue

        if not callable(getattr(module, "generate_signal", None)):
            logger.debug("Skipping %s -- no generate_signal function", module_name)
            continue

        display_name = path.stem.replace("_", " ").title()
        strategies[display_name] = module
        logger.debug("Discovered strategy: %s", display_name)

    logger.info("Discovered %d strategies", len(strategies))
    return strategies


def get_strategy_metadata(module: ModuleType) -> dict:
    """Extract metadata from a strategy module.

    Pulls the module docstring and any module-level uppercase constants
    (typically threshold parameters).

    Args:
        module: An imported strategy module.

    Returns:
        Dict with 'description' (str) and 'parameters' (dict of name -> value).
    """
    description = inspect.getdoc(module) or ""

    parameters = {}
    for name, value in vars(module).items():
        if name == "SUMMARY":
            continue
        if name.isupper() and not name.startswith("_"):
            if isinstance(value, (int, float, str, bool)):
                parameters[name] = value

    summary = getattr(module, "SUMMARY", "")
    features_config = getattr(module, "FEATURES", None)
    return {"description": description, "summary": summary, "parameters": parameters, "features": features_config}


def sync_strategies_to_db(conn: sqlite3.Connection) -> dict[str, ModuleType]:
    """Discover strategies from filesystem and sync to SQLite.

    Imports all strategy modules, extracts metadata, upserts each into
    the strategies table, and removes DB rows for modules no longer on disk.

    Args:
        conn: An open SQLite connection.

    Returns:
        Dict mapping display name to strategy module.
    """
    strategies = discover_strategies()

    db_module_names = set()
    for name, module in strategies.items():
        meta = get_strategy_metadata(module)
        module_name = module.__name__
        db_module_names.add(module_name)
        upsert_strategy(
            conn,
            name=name,
            module_name=module_name,
            description=meta["description"],
            summary=meta["summary"],
            features_config=meta["features"],
            parameters=meta["parameters"],
        )

    # Remove DB rows for strategies no longer on disk
    existing = list_strategies(conn)
    for row in existing:
        if row["module_name"] not in db_module_names:
            delete_strategy(conn, row["name"])
            logger.info("Removed stale strategy from DB: %s", row["name"])

    logger.info("Synced %d strategies to DB", len(strategies))
    return strategies
