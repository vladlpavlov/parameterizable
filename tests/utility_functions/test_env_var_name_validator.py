"""Tests for environment variable name validators."""
import pytest

from mixinforge import is_valid_env_name


@pytest.mark.parametrize("name", ["PATH", "HOME", "_PRIVATE", "var1", "my_var"])
def test_is_valid_env_name_accepts_identifiers(name):
    """Verify strict validation accepts POSIX identifiers."""
    assert is_valid_env_name(name) is True


@pytest.mark.parametrize(
    "name",
    ["1VAR", "VAR-NAME", "VAR NAME", "VAR.NAME", "Var:Name"],
)
def test_is_valid_env_name_rejects_non_identifiers(name):
    """Verify strict validation rejects non-identifiers."""
    assert is_valid_env_name(name) is False


@pytest.mark.parametrize("name", ["", "VAR=NAME", "VAR\x00NAME"])
def test_is_valid_env_name_rejects_empty_or_reserved_characters(name):
    """Verify strict validation rejects empty names and reserved characters."""
    assert is_valid_env_name(name) is False


@pytest.mark.parametrize("name", [None, 123, object()])
def test_is_valid_env_name_rejects_non_string_inputs(name):
    """Verify strict validation rejects non-string inputs."""
    assert is_valid_env_name(name) is False
