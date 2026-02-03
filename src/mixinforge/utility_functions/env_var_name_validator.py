"""Environment variable name validation helpers.

Provides a strict, portable validator for environment variable names to keep
usage consistent across macOS, Windows, and Ubuntu.
"""
import re
from typing import Final

__all__ = ["is_valid_env_name"]

_STRICT_ENV_NAME_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"^[A-Za-z_][A-Za-z0-9_]*$"
)


def is_valid_env_name(name: str) -> bool:
    """Validate a portable environment variable name.

    Enforces a strict, shell-safe subset (POSIX identifiers) so names are
    portable across macOS, Windows, and Ubuntu. Names must start with an
    ASCII letter or underscore and contain only ASCII letters, digits, and
    underscores.

    Args:
        name: Candidate environment variable name.

    Returns:
        True if name is a valid portable identifier, False otherwise.
    """
    if not isinstance(name, str):
        return False
    return _STRICT_ENV_NAME_PATTERN.fullmatch(name) is not None
