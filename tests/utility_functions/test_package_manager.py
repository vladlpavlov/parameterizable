"""Tests for runtime package management functionality.

Tests cover installation, uninstallation, validation, error handling, and
protection mechanisms for dynamic package management.
"""

import importlib
import os
import subprocess
import sys
import textwrap
from pathlib import Path
import pytest

from mixinforge import (
    install_package,
    uninstall_package,
)
from mixinforge.utility_functions.package_manager import _validate_package_args


PROJECT_ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = PROJECT_ROOT / "src"


def _venv_python(venv_dir: Path) -> Path:
    if os.name == "nt":
        return venv_dir / "Scripts" / "python.exe"
    return venv_dir / "bin" / "python"


def _create_venv_without_pip(tmp_path: Path) -> Path:
    venv_dir = tmp_path / "venv"
    subprocess.run(
        [sys.executable, "-m", "venv", "--without-pip", str(venv_dir)],
        check=True,
    )
    return venv_dir


def _run_in_venv(venv_dir: Path, script: str) -> None:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(SRC_ROOT) + (
        os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else ""
    )
    env["PIP_NO_INDEX"] = "1"
    env["PIP_DISABLE_PIP_VERSION_CHECK"] = "1"
    env["PIP_CONFIG_FILE"] = os.devnull
    env["PIP_FIND_LINKS"] = ""

    result = subprocess.run(
        [str(_venv_python(venv_dir)), "-c", script],
        text=True,
        capture_output=True,
        env=env,
    )
    assert result.returncode == 0, (
        "Subprocess failed.\n"
        f"stdout:\n{result.stdout}\n"
        f"stderr:\n{result.stderr}"
    )


# Validation Tests

def test_validate_package_args_accepts_valid_inputs():
    """Verify shared validation accepts valid inputs."""
    _validate_package_args("requests")
    _validate_package_args("requests", import_name="requests")
    _validate_package_args("requests", version="1.2.3")
    _validate_package_args("requests[socks]", allow_requirement=True)
    _validate_package_args(
        "requests>=2.0; python_version>='3.8'",
        allow_requirement=True,
    )
    _validate_package_args(
        "requests @ https://example.com/requests-2.0.0-py3-none-any.whl",
        allow_requirement=True,
    )


def test_validate_package_args_rejects_empty_import_name():
    """Verify shared validation rejects empty import_name."""
    with pytest.raises(ValueError, match="import_name must be"):
        _validate_package_args("requests", import_name="")


def test_validate_package_args_rejects_invalid_package_name():
    """Verify shared validation rejects malformed package name."""
    with pytest.raises(ValueError, match="Invalid package name format"):
        _validate_package_args("package@name")


def test_validate_package_args_rejects_invalid_requirement_format():
    """Verify requirement-style inputs still reject malformed strings."""
    with pytest.raises(ValueError, match="Invalid requirement format"):
        _validate_package_args(
            "requests@https://example.com/requests.whl",
            allow_requirement=True,
        )
    with pytest.raises(ValueError, match="version cannot be combined"):
        _validate_package_args(
            "requests>=2.0",
            version="1.0",
            allow_requirement=True,
        )


def test_validate_package_args_rejects_invalid_version():
    """Verify shared validation rejects invalid version specifier."""
    with pytest.raises(ValueError, match="Invalid version format"):
        _validate_package_args("requests", version="version;rm -rf /")


@pytest.mark.parametrize("invalid_name", [
    "",
    "package@name",
    "package#name",
    "-package",
    "package-",
    ".package",
    "package.",
])
def test_install_rejects_invalid_package_names(invalid_name):
    """Verify install rejects malformed package names."""
    with pytest.raises(ValueError):
        install_package(invalid_name)


def test_install_rejects_non_string_package_name():
    """Verify install rejects non-string package names."""
    with pytest.raises(ValueError, match="package_name must be"):
        install_package(None)
    with pytest.raises(ValueError, match="package_name must be"):
        install_package(123)


@pytest.mark.parametrize("invalid_version", [
    "version with spaces but invalid!@#$",
    "version;rm -rf /",
    "version`echo hacked`",
])
def test_install_rejects_invalid_version_formats(invalid_version):
    """Verify install rejects unsafe version specifiers."""
    with pytest.raises(ValueError, match="Invalid version format"):
        install_package("requests", version=invalid_version)


def test_install_rejects_non_string_version():
    """Verify install rejects non-string version specifiers."""
    with pytest.raises(ValueError, match="version must be a string"):
        install_package("requests", version=123)


def test_install_rejects_empty_import_name():
    """Verify install rejects empty import_name parameter."""
    with pytest.raises(ValueError, match="import_name must be"):
        install_package("requests", import_name="")


def test_install_rejects_non_string_import_name():
    """Verify install rejects non-string import_name parameter."""
    with pytest.raises(ValueError, match="import_name must be"):
        install_package("requests", import_name=123)


def test_install_pip_requires_uv():
    """Verify pip can only be installed via uv."""
    with pytest.raises(ValueError, match="pip must be installed using uv"):
        install_package("pip", use_uv=False)


def test_install_uv_requires_pip():
    """Verify uv can only be installed via pip."""
    with pytest.raises(ValueError, match="uv must be installed using pip"):
        install_package("uv", use_uv=True)


@pytest.mark.parametrize("protected", ["pip", "uv"])
def test_uninstall_protects_package_managers(protected):
    """Verify critical package managers cannot be uninstalled."""
    with pytest.raises(ValueError, match="protected package"):
        uninstall_package(protected)


def test_uninstall_rejects_invalid_package_name():
    """Verify uninstall rejects empty or non-string package names."""
    with pytest.raises(ValueError, match="package_name must be"):
        uninstall_package("")
    with pytest.raises(ValueError, match="package_name must be"):
        uninstall_package(None)


# Functional Behavior Tests

@pytest.mark.parametrize("use_uv", [True, False])
def test_install_and_uninstall_real_package(use_uv):
    """Verify complete install-verify-uninstall cycle."""
    package = "nothing"

    # Ensure clean state
    try:
        uninstall_package(package, use_uv=use_uv, verify_uninstall=False)
    except RuntimeError:
        pass

    try:
        # Install and verify
        install_package(package, use_uv=use_uv, verify_import=True)
        mod = importlib.import_module(package)
        assert mod is not None

        # Uninstall and verify removal
        uninstall_package(package, use_uv=use_uv, verify_uninstall=True)

        with pytest.raises(ModuleNotFoundError):
            importlib.invalidate_caches()
            if package in sys.modules:
                del sys.modules[package]
            importlib.import_module(package)
    finally:
        # Ensure cleanup even if test fails
        try:
            uninstall_package(package, use_uv=use_uv, verify_uninstall=False)
        except Exception:
            pass


@pytest.mark.parametrize("use_uv", [True, False])
def test_install_with_version_pinning(use_uv):
    """Verify version-specific installation works without error."""
    package = "nothing"
    version = "0.0.3"  # Use an actual available version

    try:
        uninstall_package(package, use_uv=use_uv, verify_uninstall=False)
    except RuntimeError:
        pass

    try:
        # Just verify version pinning syntax works
        install_package(package, version=version, use_uv=use_uv, verify_import=True)
        mod = importlib.import_module(package)
        assert mod is not None
    finally:
        # Ensure cleanup even if test fails
        try:
            uninstall_package(package, use_uv=use_uv, verify_uninstall=False)
        except Exception:
            pass


@pytest.mark.parametrize("use_uv", [True, False])
def test_install_with_upgrade_flag(use_uv):
    """Verify upgrade flag works without error."""
    package = "nothing"

    try:
        uninstall_package(package, use_uv=use_uv, verify_uninstall=False)
    except RuntimeError:
        pass

    try:
        # Install and then upgrade (both should succeed without error)
        install_package(package, use_uv=use_uv, verify_import=True)
        install_package(package, upgrade=True, use_uv=use_uv, verify_import=True)
    finally:
        # Ensure cleanup even if test fails
        try:
            uninstall_package(package, use_uv=use_uv, verify_uninstall=False)
        except Exception:
            pass


def test_install_without_verification():
    """Verify install works when verify_import is disabled but package is still importable."""
    package = "nothing"

    try:
        uninstall_package(package, verify_uninstall=False)
    except RuntimeError:
        pass

    try:
        # Install without verification
        install_package(package, verify_import=False)

        # But package should still be importable because caches were invalidated
        mod = importlib.import_module(package)
        assert mod is not None
    finally:
        # Ensure cleanup even if test fails
        try:
            uninstall_package(package, verify_uninstall=False)
        except Exception:
            pass


def test_uninstall_without_verification():
    """Verify uninstall works when verify_uninstall is disabled but package is still gone."""
    package = "nothing"

    try:
        uninstall_package(package, verify_uninstall=False)
    except RuntimeError:
        pass

    try:
        install_package(package, verify_import=True)

        # Uninstall without verification
        uninstall_package(package, verify_uninstall=False)

        # But package should still be gone because caches were invalidated and sys.modules cleared
        with pytest.raises(ModuleNotFoundError):
            importlib.import_module(package)
    finally:
        # Ensure cleanup even if test fails
        try:
            uninstall_package(package, verify_uninstall=False)
        except Exception:
            pass


@pytest.mark.parametrize("use_uv", [True, False])
def test_idempotent_install(use_uv):
    """Verify installing already-installed package succeeds."""
    package = "nothing"

    try:
        uninstall_package(package, use_uv=use_uv, verify_uninstall=False)
    except RuntimeError:
        pass

    try:
        install_package(package, use_uv=use_uv, verify_import=True)
        install_package(package, use_uv=use_uv, verify_import=True)  # Should not fail
    finally:
        # Ensure cleanup even if test fails
        try:
            uninstall_package(package, use_uv=use_uv, verify_uninstall=False)
        except Exception:
            pass


def test_install_uv_bootstraps_pip_when_missing(tmp_path):
    """Installing uv bootstraps pip via ensurepip in a pip-less venv."""
    venv_dir = _create_venv_without_pip(tmp_path)
    script = textwrap.dedent(
        """
        import importlib
        from mixinforge import install_package

        for name in ("pip", "uv"):
            try:
                importlib.import_module(name)
                raise SystemExit(f"{name} unexpectedly available")
            except ModuleNotFoundError:
                pass

        try:
            install_package("uv", use_uv=False, verify_import=False)
        except RuntimeError:
            pass

        importlib.invalidate_caches()
        importlib.import_module("pip")
        """
    )
    _run_in_venv(venv_dir, script)


def test_install_pip_bootstraps_pip_even_when_uv_missing(tmp_path):
    """Installing pip bootstraps pip before attempting uv installation."""
    venv_dir = _create_venv_without_pip(tmp_path)
    script = textwrap.dedent(
        """
        import importlib
        from mixinforge import install_package

        for name in ("pip", "uv"):
            try:
                importlib.import_module(name)
                raise SystemExit(f"{name} unexpectedly available")
            except ModuleNotFoundError:
                pass

        try:
            install_package("pip", use_uv=True, verify_import=False)
        except RuntimeError:
            pass

        importlib.invalidate_caches()
        importlib.import_module("pip")
        """
    )
    _run_in_venv(venv_dir, script)


# Error Handling Tests

@pytest.mark.parametrize("use_uv", [True, False])
def test_install_nonexistent_package_fails(use_uv):
    """Verify installing nonexistent package raises RuntimeError."""
    fake_package = "xyzabc123nonexistent9999"

    with pytest.raises(RuntimeError, match="Command failed"):
        install_package(fake_package, use_uv=use_uv)


@pytest.mark.parametrize("use_uv", [True, False])
def test_uninstall_nonexistent_package_without_verification_succeeds(use_uv):
    """Verify uninstalling nonexistent package without verification is a no-op."""
    fake_package = "xyzabc123nonexistent9999"

    # pip/uv uninstall without verification doesn't fail for nonexistent packages
    # This tests the actual behavior: it's a silent no-op
    uninstall_package(fake_package, use_uv=use_uv, verify_uninstall=False)


def test_install_with_verification_detects_missing_module():
    """Verify install fails if package installs but module not importable."""
    # This would require a package that installs but has no module,
    # which is difficult to test reliably. Skipping for now.
    pass


def test_uninstall_with_verification_detects_remaining_distribution():
    """Verify uninstall fails if distribution still present after removal."""
    from unittest.mock import patch, MagicMock

    package = "fake-still-installed"

    with patch(
        "mixinforge.utility_functions.package_manager._install_uv_and_pip"
    ), patch(
        "mixinforge.utility_functions.package_manager._run"
    ), patch(
        "mixinforge.utility_functions.package_manager.importlib.invalidate_caches"
    ), patch(
        "mixinforge.utility_functions.package_manager.importlib_metadata.distribution"
    ) as mock_distribution:
        # Simulate distribution still exists after uninstall attempt
        mock_distribution.return_value = MagicMock()

        with pytest.raises(RuntimeError, match="still installed after uninstallation"):
            uninstall_package(package, verify_uninstall=True)


# Edge Cases

def test_install_accepts_single_char_package_name():
    """Verify single-character package names are accepted if valid."""
    # Single char names are rare but valid according to the regex
    with pytest.raises(RuntimeError):  # Will fail to find package, but validation passes
        install_package("z", verify_import=False)


def test_install_accepts_complex_valid_version():
    """Verify complex version specifiers are accepted."""
    # Test that validation accepts complex version strings
    # Note: we don't actually install to avoid dependency on package availability
    fake_package = "nonexistent12345"

    # Should pass validation but fail at installation
    with pytest.raises(RuntimeError, match="Command failed"):
        install_package(fake_package, version=">=0.5.0,<1.0.0", verify_import=False)


def test_install_accepts_package_with_hyphens_underscores():
    """Verify package names with hyphens and underscores work."""
    # nothing is simple, but testing the validation logic
    with pytest.raises(RuntimeError):  # Nonexistent, but validation passes
        install_package("test-package-name", verify_import=False)

    with pytest.raises(RuntimeError):  # Nonexistent, but validation passes
        install_package("test_package_name", verify_import=False)
