"""Runtime package management for dynamic dependency installation.

Provides safe, synchronous installation and uninstallation of Python packages
within a running interpreter. This enables autonomous code portals to acquire
dependencies on-demand without manual intervention.

Prefers uv as the installer frontend for speed and reliability, falling back
to pip when needed. Automatically bootstraps missing package managers and
protects critical tools (pip, uv) from accidental removal.
"""

import subprocess
import importlib
import importlib.metadata as importlib_metadata
import sys
import re
from typing import Final
from functools import cache


_PACKAGE_NAME_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"^[A-Za-z0-9]([A-Za-z0-9._-]*[A-Za-z0-9])?$"
)
_PACKAGE_BASE_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"^[A-Za-z0-9]([A-Za-z0-9._-]*[A-Za-z0-9])?"
)
_PACKAGE_EXTRAS_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"^\[[A-Za-z0-9._-]+(,[A-Za-z0-9._-]+)*\]"
)
_VERSION_PATTERN: Final[re.Pattern[str]] = re.compile(r"^[\w\.\-\+\*,<>=!\s]+$")
_REQUIREMENT_MARKER_PATTERN: Final[re.Pattern[str]] = re.compile(r"[<>=!~@;]")
_REQUIREMENT_AT_PATTERN: Final[re.Pattern[str]] = re.compile(r"\s+@\s+\S+")


def _run(command: list[str], timeout: int = 300) -> None:
    """Execute a package management command with timeout protection.

    Automatically invalidates import caches after successful execution to ensure
    Python's import system reflects filesystem changes from package operations.

    Args:
        command: Command and arguments to execute.
        timeout: Maximum execution time in seconds.

    Raises:
        RuntimeError: If command times out or fails with non-zero exit code.
    """
    try:
        subprocess.run(command, check=True, stdout=subprocess.PIPE
            , stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL, text=True
            , timeout=timeout)
    except subprocess.TimeoutExpired as e:
        raise RuntimeError(
            f"Command timed out after {timeout}s: {' '.join(command)}") from e
    except subprocess.CalledProcessError as e:
        raise RuntimeError(
            f"Command failed: {' '.join(command)}\n{e.stdout}") from e

    importlib.invalidate_caches()


def _is_module_available(module_name: str) -> bool:
    """Check if a module is available without importing it.

    Uses importlib.util.find_spec to avoid side effects from actually
    importing the module (e.g., initialization code, sys.modules pollution).
    """
    return importlib.util.find_spec(module_name) is not None


def _validate_package_args(
        package_name: str,
        import_name: str | None = None,
        version: str | None = None,
        allow_requirement: bool = False,
) -> None:
    """Validates package installation arguments for consistency.

    Args:
        package_name: PyPI package name or requirement string.
        import_name: Expected module name after installation.
        version: Explicit version specifier (e.g., "1.0.0").
        allow_requirement: Whether package_name can contain PEP 508 specifiers.

    Raises:
        ValueError: If arguments are invalid or mutually exclusive.
    """
    _validate_package_name(package_name, allow_requirement, version)
    _validate_version(version)
    _validate_import_name(import_name)


def _validate_package_name(
        package_name: str,
        allow_requirement: bool,
        version: str | None,
) -> None:
    """Validates package name format and requirement specifiers.

    Args:
        package_name: Input string to validate.
        allow_requirement: Whether to accept full requirement strings.
        version: Explicit version, incompatible with requirement markers.

    Raises:
        ValueError: If name format is invalid or version conflicts with requirement.
    """
    if not package_name or not isinstance(package_name, str):
        raise ValueError("package_name must be a non-empty string")

    if allow_requirement:
        _validate_requirement_spec(package_name, version)
    elif not _PACKAGE_NAME_PATTERN.match(package_name):
        raise ValueError(f"Invalid package name format: {package_name}")


def _validate_requirement_spec(
        package_name: str,
        version: str | None,
) -> None:
    """Validates structure of PEP 508 requirement strings.

    Args:
        package_name: Requirement string to parse.
        version: Explicit version argument (must be None if markers exist).

    Raises:
        ValueError: If requirement syntax is invalid or incompatible with version.
    """
    base_match = _PACKAGE_BASE_PATTERN.match(package_name)
    if not base_match:
        raise ValueError(f"Invalid package name format: {package_name}")

    remainder = _strip_extras(package_name, base_match.end())
    if remainder and not _is_valid_requirement_remainder(
            remainder,
            package_name,
    ):
        raise ValueError(f"Invalid requirement format: {package_name}")

    if version is not None and _REQUIREMENT_MARKER_PATTERN.search(package_name):
        raise ValueError(
            "version cannot be combined with requirement specifiers"
        )


def _strip_extras(package_name: str, base_end: int) -> str:
    """Removes extras (e.g., [security]) from a requirement string.

    Args:
        package_name: Full requirement string.
        base_end: Index where the base package name ends.

    Returns:
        The remaining string after stripping extras blocks.

    Raises:
        ValueError: If extras block format is invalid.
    """
    remainder = package_name[base_end:].lstrip()
    if not remainder.startswith("["):
        return remainder

    extras_match = _PACKAGE_EXTRAS_PATTERN.match(remainder)
    if not extras_match:
        raise ValueError(f"Invalid extras format: {package_name}")
    return remainder[extras_match.end():].lstrip()


def _is_valid_requirement_remainder(
        remainder: str,
        package_name: str,
) -> bool:
    """Checks if the requirement suffix contains valid PEP 508 specifiers.

    Args:
        remainder: The string following the package name (and extras).
        package_name: Original full package string (for context checks).

    Returns:
        True if the remainder is a valid version specifier or marker.
    """
    if remainder.startswith("@"):
        return _REQUIREMENT_AT_PATTERN.search(package_name) is not None
    return remainder.startswith(";") or remainder[0] in "<>!=~"


def _validate_version(version: str | None) -> None:
    """Validates the format of an explicit version string.

    Args:
        version: Version string to check (can be None).

    Raises:
        ValueError: If version is not a string or has invalid format.
    """
    if version is None:
        return

    if not isinstance(version, str):
        raise ValueError("version must be a string")

    if not _VERSION_PATTERN.match(version):
        raise ValueError(f"Invalid version format: {version}")


def _validate_import_name(import_name: str | None) -> None:
    """Validates the format of the optional import name.

    Args:
        import_name: Module name to check (can be None).

    Raises:
        ValueError: If import_name is provided but is empty or not a string.
    """
    if import_name is None:
        return

    if not isinstance(import_name, str) or len(import_name) == 0:
        raise ValueError("import_name must be a non-empty string")


def _canonicalize_distribution_name(name: str) -> str:
    """Canonicalizes a distribution name according to PyPI standards.

    Converts to lowercase and replaces runs of non-alphanumeric characters with
    a single dash.

    Args:
        name: Raw distribution name.

    Returns:
        Canonicalized name string.
    """
    return re.sub(r"[-_.]+", "-", name).lower()


def _extract_base_package_name(package_name: str) -> str:
    """Extracts the base package name from a requirement string.

    Args:
        package_name: Requirement string (e.g., "requests>=2.0").

    Returns:
        The base name (e.g., "requests") without extras or version specifiers.
    """
    match = _PACKAGE_BASE_PATTERN.match(package_name)
    return match.group(0) if match else package_name


def _ensure_pip_available() -> None:
    """Ensure pip is available, bootstrapping via uv or ensurepip as needed.

    Raises:
        RuntimeError: If bootstrapping pip fails.
    """
    if _is_module_available("pip"):
        return

    if _is_module_available("uv"):
        install_package("pip", use_uv=True)
        return

    try:
        _run([sys.executable, "-m", "ensurepip", "--upgrade"])
        importlib.import_module("pip")
    except (RuntimeError, ModuleNotFoundError) as e:
        raise RuntimeError(
            "pip is not available, and ensurepip failed to bootstrap pip."
        ) from e


def _ensure_uv_available() -> None:
    """Ensure uv is available, bootstrapping via pip as needed.

    Raises:
        RuntimeError: If bootstrapping uv fails.
    """
    if _is_module_available("uv"):
        return

    _ensure_pip_available()
    install_package("uv", use_uv=False)


@cache
def _install_uv_and_pip() -> None:
    """Ensure both package managers are available for installation.

    Bootstraps missing package managers using whichever is available: installs
    uv via pip or pip via uv. Cached to ensure this runs only once per session.

    Raises:
        RuntimeError: If bootstrapping either package manager fails.

    Note:
        Called automatically by install_package for any package except pip
        or uv themselves. Use `_install_uv_and_pip.cache_clear()` to reset
        the cached state if the environment changes (e.g., in tests).
    """
    _ensure_pip_available()
    _ensure_uv_available()


def install_package(package_name: str,
        upgrade: bool = False,
        version: str | None = None,
        use_uv: bool = True,
        import_name: str | None = None,
        verify_import: bool = True
        ) -> None:
    """Install a Python package from PyPI into the current environment.

    Installs packages using uv (default) or pip, automatically bootstrapping
    missing package managers. Handles packages where the PyPI name differs
    from the import name, and verifies successful installation by default.

    Args:
        package_name: PyPI package name to install.
        upgrade: Whether to upgrade if package is already installed.
        version: Version specifier for pinned installation.
        use_uv: Whether to use uv instead of pip as installer. Note that pip
            requires use_uv=True and uv requires use_uv=False.
        import_name: Module name for import verification when it differs from
            package_name (e.g., "PIL" for "Pillow" package).
        verify_import: Whether to verify importability after installation.
            Disable for CLI-only tools without importable modules.

    Raises:
        ValueError: If package_name or version format is invalid, or if
            attempting to install pip without uv or uv without pip.
        RuntimeError: If installation command fails or times out.
        ModuleNotFoundError: If verify_import is True but import fails.

    Example:
        >>> install_package("requests")
        >>> install_package("Pillow", import_name="PIL")
        >>> install_package("black", verify_import=False)
    """
    _validate_package_args(
        package_name=package_name,
        import_name=import_name,
        version=version,
        allow_requirement=True,
    )

    if package_name == "pip":
        if not use_uv:
            raise ValueError("pip must be installed using uv (use_uv=True)")
        _ensure_uv_available()
    elif package_name == "uv":
        if use_uv:
            raise ValueError("uv must be installed using pip (use_uv=False)")
        _ensure_pip_available()
    else:
        _install_uv_and_pip()

    if use_uv:
        command = [sys.executable, "-m", "uv", "pip", "install"]
    else:
        command = [sys.executable, "-m", "pip", "install", "--no-input"]

    if upgrade:
        command.append("--upgrade")

    package_spec = f"{package_name}=={version}" if version else package_name
    command.append(package_spec)

    _run(command)

    if verify_import:
        module_to_import = (
            import_name
            if import_name is not None
            else _extract_base_package_name(package_name)
        )
        importlib.import_module(module_to_import)


def uninstall_package(package_name: str,
            use_uv: bool = True,
            import_name: str | None = None,
            verify_uninstall: bool = True,
            ) -> None:
    """Remove a Python package from the current environment.

    Uninstalls packages and verifies complete removal. Protects critical
    package managers (pip, uv) from accidental deletion to maintain system
    package management capabilities.

    Args:
        package_name: Package to uninstall. Cannot be pip or uv.
        use_uv: Whether to use uv instead of pip as uninstaller.
        import_name: Module name for verification when it differs from
            package_name (e.g., "PIL" for "Pillow" package).
        verify_uninstall: Whether to verify the package distribution is no
            longer installed after removal. If import_name is provided and the
            package name lookup fails, fallback to resolving distributions
            providing the import name.

    Raises:
        ValueError: If attempting to uninstall protected packages (pip, uv).
        RuntimeError: If uninstall command fails or the package distribution
            remains installed after uninstallation when verify_uninstall is True.
    """
    _validate_package_args(
        package_name=package_name,
        import_name=import_name,
    )

    if package_name in ["pip", "uv"]:
        raise ValueError(f"Cannot uninstall '{package_name}' "
                         "- it's a protected package")

    _install_uv_and_pip()

    if use_uv:
        command = [sys.executable, "-m", "uv", "pip", "uninstall", package_name]
    else:
        command = [sys.executable, "-m", "pip", "uninstall", "-y", package_name]

    _run(command)

    # Remove from sys.modules to ensure clean state
    module_to_check = import_name if import_name else package_name
    modules_to_remove = [m for m in sys.modules
        if m == module_to_check or m.startswith(f"{module_to_check}.")]
    for mod in modules_to_remove:
        del sys.modules[mod]

    if verify_uninstall:
        # Invalidate import caches to ensure fresh lookups after uninstall
        importlib.invalidate_caches()

        try:
            importlib_metadata.distribution(package_name)
        except importlib_metadata.PackageNotFoundError:
            if import_name:
                top_level_name = import_name.split(".", 1)[0]
                dist_names = importlib_metadata.packages_distributions().get(
                    top_level_name,
                    [],
                )
                # Only raise if exactly one distribution provides this import
                # AND that distribution is different from what we tried to uninstall
                # (handles case where package_name was an alias)
                if len(dist_names) == 1:
                    canonical_requested = _canonicalize_distribution_name(
                        package_name
                    )
                    canonical_found = _canonicalize_distribution_name(
                        dist_names[0]
                    )
                    if canonical_found != canonical_requested:
                        raise RuntimeError(
                            f"Package '{package_name}' appears still installed via "
                            f"distribution '{dist_names[0]}' for import '{import_name}'"
                        )
        else:
            raise RuntimeError(
                f"Package '{package_name}' is still installed after uninstallation"
            )
