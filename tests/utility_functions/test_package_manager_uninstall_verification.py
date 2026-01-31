"""Tests for uninstall verification behavior using real package operations."""

from __future__ import annotations

import importlib.metadata as importlib_metadata
import os
from pathlib import Path
import subprocess
import sys
import textwrap

import pytest

from mixinforge import uninstall_package


def _pip_env() -> dict[str, str]:
    env = os.environ.copy()
    env["PIP_NO_INDEX"] = "1"
    env["PIP_DISABLE_PIP_VERSION_CHECK"] = "1"
    env["PIP_CONFIG_FILE"] = os.devnull
    return env


def _write_local_package(
    package_dir: Path,
    dist_name: str,
    module_name: str | None = None,
) -> None:
    module_name = module_name or dist_name
    package_dir.mkdir(parents=True, exist_ok=True)
    (package_dir / f"{module_name}.py").write_text(
        "VALUE = 1\n",
        encoding="ascii",
    )
    setup_py = textwrap.dedent(
        f"""
        from setuptools import setup

        setup(
            name="{dist_name}",
            version="0.0.0",
            py_modules=["{module_name}"],
        )
        """
    ).lstrip()
    (package_dir / "setup.py").write_text(setup_py, encoding="ascii")


def _pip_install_local(package_dir: Path) -> None:
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "pip",
            "install",
            "--no-deps",
            "--no-build-isolation",
            str(package_dir),
        ],
        text=True,
        capture_output=True,
        env=_pip_env(),
    )
    assert result.returncode == 0, (
        "pip install failed.\n"
        f"stdout:\n{result.stdout}\n"
        f"stderr:\n{result.stderr}"
    )


def _pip_uninstall(package_name: str) -> None:
    subprocess.run(
        [sys.executable, "-m", "pip", "uninstall", "-y", package_name],
        check=False,
        text=True,
        capture_output=True,
        env=_pip_env(),
    )


def test_uninstall_verification_ignores_stdlib_import_name(tmp_path):
    """Verify uninstall does not fail when import_name is a stdlib module."""
    pytest.importorskip("setuptools")
    import json

    assert json.loads('{"ok": true}') == {"ok": True}
    package_name = "mf_stdlib_shadow_pkg"
    package_dir = tmp_path / package_name
    _write_local_package(package_dir, package_name)
    _pip_install_local(package_dir)

    try:
        assert importlib_metadata.distribution(package_name) is not None
        uninstall_package(
            package_name,
            import_name="json",
            verify_uninstall=True,
        )
    finally:
        _pip_uninstall(package_name)

    with pytest.raises(importlib_metadata.PackageNotFoundError):
        importlib_metadata.distribution(package_name)

    assert json.dumps({"still": "there"}) == '{"still": "there"}'


def test_uninstall_verification_falls_back_to_import_name(tmp_path):
    """Verify uninstall fails when package_name is an alias for the import name."""
    pytest.importorskip("setuptools")
    dist_name = "mf-alias-dist"
    module_name = "mf_alias_mod"
    package_dir = tmp_path / dist_name
    _write_local_package(package_dir, dist_name, module_name)
    _pip_install_local(package_dir)

    try:
        assert importlib_metadata.distribution(dist_name) is not None
        with pytest.raises(RuntimeError):
            uninstall_package(
                module_name,
                import_name=module_name,
                verify_uninstall=True,
            )
    finally:
        _pip_uninstall(dist_name)

    with pytest.raises(importlib_metadata.PackageNotFoundError):
        importlib_metadata.distribution(dist_name)
