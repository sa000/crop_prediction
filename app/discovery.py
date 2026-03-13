"""Strategy auto-discovery for the Streamlit app.

Scans the strategies/ directory for Python modules that expose a
generate_signal function, making them available for selection in the UI."""

import importlib
import inspect
import logging
from pathlib import Path
from types import ModuleType

logger = logging.getLogger(__name__)

STRATEGIES_DIR = Path(__file__).resolve().parents[1] / "strategies"
EXCLUDED_FILES = {"__init__.py", "backtest.py", "analytics.py"}


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
        if name.isupper() and not name.startswith("_"):
            if isinstance(value, (int, float, str, bool)):
                parameters[name] = value

    return {"description": description, "parameters": parameters}
