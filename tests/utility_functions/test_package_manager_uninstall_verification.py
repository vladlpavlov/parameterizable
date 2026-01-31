"""Tests for uninstall verification behavior using mocked package operations."""

from __future__ import annotations

import importlib.metadata as importlib_metadata
from unittest.mock import patch, MagicMock

import pytest

from mixinforge import uninstall_package


def test_uninstall_verification_ignores_stdlib_import_name():
    """Verify uninstall does not fail when import_name is a stdlib module.

    When a package is uninstalled and verify_uninstall=True with an import_name
    that happens to be a stdlib module (like 'json'), the verification should
    pass because:
    1. distribution(package_name) raises PackageNotFoundError (package gone)
    2. packages_distributions().get(import_name) returns [] for stdlib modules
    3. Since len([]) != 1, no RuntimeError is raised
    """
    package_name = "mf_stdlib_shadow_pkg"

    with patch(
        "mixinforge.utility_functions.package_manager._install_uv_and_pip"
    ), patch(
        "mixinforge.utility_functions.package_manager._run"
    ), patch(
        "mixinforge.utility_functions.package_manager.importlib.invalidate_caches"
    ), patch(
        "mixinforge.utility_functions.package_manager.importlib_metadata.distribution"
    ) as mock_distribution, patch(
        "mixinforge.utility_functions.package_manager.importlib_metadata.packages_distributions"
    ) as mock_packages_distributions:
        # Simulate package not found after uninstall
        mock_distribution.side_effect = importlib_metadata.PackageNotFoundError(
            package_name
        )
        # stdlib modules like 'json' are not in packages_distributions
        mock_packages_distributions.return_value = {}

        # Should not raise - stdlib import_name means no distribution found
        uninstall_package(
            package_name,
            import_name="json",
            verify_uninstall=True,
        )


def test_uninstall_verification_falls_back_to_import_name():
    """Verify uninstall fails when package_name is an alias for the import name.

    When uninstalling with a package name that doesn't match the distribution
    name but the import_name maps to exactly one distribution, it should raise
    RuntimeError indicating the package is still installed under a different name.
    """
    dist_name = "mf-alias-dist"
    module_name = "mf_alias_mod"

    with patch(
        "mixinforge.utility_functions.package_manager._install_uv_and_pip"
    ), patch(
        "mixinforge.utility_functions.package_manager._run"
    ), patch(
        "mixinforge.utility_functions.package_manager.importlib.invalidate_caches"
    ), patch(
        "mixinforge.utility_functions.package_manager.importlib_metadata.distribution"
    ) as mock_distribution, patch(
        "mixinforge.utility_functions.package_manager.importlib_metadata.packages_distributions"
    ) as mock_packages_distributions:
        # Simulate that the package_name (module_name) is not found as a distribution
        mock_distribution.side_effect = importlib_metadata.PackageNotFoundError(
            module_name
        )
        # But the import_name maps to exactly one distribution (the real dist_name)
        # which is DIFFERENT from the package_name we tried to uninstall
        mock_packages_distributions.return_value = {module_name: [dist_name]}

        with pytest.raises(RuntimeError) as exc_info:
            uninstall_package(
                module_name,
                import_name=module_name,
                verify_uninstall=True,
            )

        assert dist_name in str(exc_info.value)
        assert "still installed" in str(exc_info.value)


def test_uninstall_verification_passes_when_distribution_not_found():
    """Verify uninstall succeeds when distribution is completely removed."""
    package_name = "some-package"

    with patch(
        "mixinforge.utility_functions.package_manager._install_uv_and_pip"
    ), patch(
        "mixinforge.utility_functions.package_manager._run"
    ), patch(
        "mixinforge.utility_functions.package_manager.importlib.invalidate_caches"
    ), patch(
        "mixinforge.utility_functions.package_manager.importlib_metadata.distribution"
    ) as mock_distribution:
        mock_distribution.side_effect = importlib_metadata.PackageNotFoundError(
            package_name
        )

        # Should not raise when no import_name provided and distribution not found
        uninstall_package(
            package_name,
            verify_uninstall=True,
        )


def test_uninstall_verification_fails_when_distribution_still_exists():
    """Verify uninstall fails when distribution is still found after uninstall."""
    package_name = "stubborn-package"

    with patch(
        "mixinforge.utility_functions.package_manager._install_uv_and_pip"
    ), patch(
        "mixinforge.utility_functions.package_manager._run"
    ), patch(
        "mixinforge.utility_functions.package_manager.importlib.invalidate_caches"
    ), patch(
        "mixinforge.utility_functions.package_manager.importlib_metadata.distribution"
    ) as mock_distribution:
        # Distribution still exists after uninstall attempt
        mock_distribution.return_value = MagicMock()

        with pytest.raises(RuntimeError) as exc_info:
            uninstall_package(
                package_name,
                verify_uninstall=True,
            )

        assert "still installed after uninstallation" in str(exc_info.value)


def test_uninstall_verification_passes_when_same_distribution_found():
    """Verify uninstall passes when packages_distributions returns the same package_name.

    If the package was successfully uninstalled (distribution() raises PackageNotFoundError)
    but packages_distributions() still shows the same package_name for the import_name,
    this is likely stale cache data and should not trigger a failure.
    """
    package_name = "my-package"
    import_name = "my_module"
    dist_name = "My_Package"

    with patch(
        "mixinforge.utility_functions.package_manager._install_uv_and_pip"
    ), patch(
        "mixinforge.utility_functions.package_manager._run"
    ), patch(
        "mixinforge.utility_functions.package_manager.importlib.invalidate_caches"
    ), patch(
        "mixinforge.utility_functions.package_manager.importlib_metadata.distribution"
    ) as mock_distribution, patch(
        "mixinforge.utility_functions.package_manager.importlib_metadata.packages_distributions"
    ) as mock_packages_distributions:
        # Package distribution not found (successfully uninstalled)
        mock_distribution.side_effect = importlib_metadata.PackageNotFoundError(
            package_name
        )
        # But packages_distributions returns a canonical-equivalent name
        mock_packages_distributions.return_value = {import_name: [dist_name]}

        # Should NOT raise because dist_names[0] == package_name
        uninstall_package(
            package_name,
            import_name=import_name,
            verify_uninstall=True,
        )


def test_uninstall_verification_passes_when_multiple_distributions_found():
    """Verify uninstall passes when multiple distributions provide the import.

    If multiple distributions provide the same import_name, we can't determine
    which one was the target, so we don't raise an error.
    """
    package_name = "my-package"
    import_name = "shared_module"

    with patch(
        "mixinforge.utility_functions.package_manager._install_uv_and_pip"
    ), patch(
        "mixinforge.utility_functions.package_manager._run"
    ), patch(
        "mixinforge.utility_functions.package_manager.importlib.invalidate_caches"
    ), patch(
        "mixinforge.utility_functions.package_manager.importlib_metadata.distribution"
    ) as mock_distribution, patch(
        "mixinforge.utility_functions.package_manager.importlib_metadata.packages_distributions"
    ) as mock_packages_distributions:
        mock_distribution.side_effect = importlib_metadata.PackageNotFoundError(
            package_name
        )
        # Multiple distributions provide this import - ambiguous, so don't raise
        mock_packages_distributions.return_value = {
            import_name: ["dist-a", "dist-b"]
        }

        # Should NOT raise because len(dist_names) != 1
        uninstall_package(
            package_name,
            import_name=import_name,
            verify_uninstall=True,
        )
