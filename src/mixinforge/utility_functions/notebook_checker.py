"""Detection utilities for Jupyter/IPython notebook environments.

Provides a function to determine whether code is running inside a
Jupyter notebook or IPython interactive shell.
"""
from __future__ import annotations

from functools import cache

__all__ = ['is_executed_in_notebook', 'reset_notebook_detection']


@cache
def is_executed_in_notebook() -> bool:
    """Return whether code is running inside a Jupyter/IPython notebook.

    Uses a lightweight heuristic checking for IPython presence and specific
    attributes. Cached to avoid repeated imports.

    Returns:
        True if running inside a notebook.
    """

    try:
        from IPython import get_ipython
        ipython = get_ipython()
        return ipython is not None and hasattr(ipython, "set_custom_exc")
    except Exception:
        return False


def reset_notebook_detection() -> None:
    """Clear the cached result of is_executed_in_notebook().

    Forces re-detection on next call (useful for testing).
    """
    is_executed_in_notebook.cache_clear()