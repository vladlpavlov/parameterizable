"""Utility for sorting dictionaries by keys.

Ensures consistent ordering for serialization and display.
"""
from typing import Any


def sort_dict_by_keys(d: dict[str, Any]) -> dict[str, Any]:
    """Return a new dictionary with keys sorted alphabetically.

    Args:
        d: The input dictionary.

    Returns:
        A new dictionary with sorted keys.

    Raises:
        TypeError: If d is not a dictionary.
    """
    if not isinstance(d, dict):
        raise TypeError(
            f"d must be a dictionary, got {type(d).__name__} instead"
        )
    return {k: d[k] for k in sorted(d.keys())}