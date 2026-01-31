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
from functools import cache


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
) -> None:
    if not package_name or not isinstance(package_name, str):
        raise ValueError("package_name must be a non-empty string")

    if len(package_name) == 1:
        if not re.match(r'^[A-Za-z0-9]$', package_name):
            raise ValueError(f"Invalid package name format: {package_name}")
    elif not re.match(r'^[A-Za-z0-9]([A-Za-z0-9._-]*[A-Za-z0-9])?$', package_name):
        raise ValueError(f"Invalid package name format: {package_name}")

    if version is not None and not isinstance(version, str):
        raise ValueError("version must be a string")

    if version is not None and not re.match(r'^[\w\.\-\+\*,<>=!\s]+$', version):
        raise ValueError(f"Invalid version format: {version}")

    if (import_name is not None
            and (not isinstance(import_name, str)
                    or len(import_name) == 0)):
        raise ValueError("import_name must be a non-empty string")


def _ensure_pip_available() -> None:
    """Ensure pip is available, bootstrapping via uv or ensurepip as needed."""
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
    """Ensure uv is available, bootstrapping via pip as needed."""
    if _is_module_available("uv"):
        return

    _ensure_pip_available()
    install_package("uv", use_uv=False)


@cache
def _install_uv_and_pip() -> None:
    """Ensure both package managers are available for installation.

    Bootstraps missing package managers using whichever is available: installs
    uv via pip or pip via uv. Cached to ensure this runs only once per session.

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
        module_to_import = import_name if import_name is not None else package_name
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
                if len(dist_names) == 1 and dist_names[0] != package_name:
                    raise RuntimeError(
                        f"Package '{package_name}' appears still installed via "
                        f"distribution '{dist_names[0]}' for import '{import_name}'"
                    )
        else:
            raise RuntimeError(
                f"Package '{package_name}' is still installed after uninstallation"
            )
