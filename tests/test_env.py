"""Tests for environment variable expansion."""

import pytest

from surek.utils.env import expand_env_vars, expand_env_vars_in_dict


class TestExpandEnvVars:
    """Tests for expand_env_vars function."""

    def test_expand_single_var(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test expanding a single environment variable."""
        monkeypatch.setenv("TEST_VAR", "test_value")
        result = expand_env_vars("prefix_${TEST_VAR}_suffix")
        assert result == "prefix_test_value_suffix"

    def test_expand_multiple_vars(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test expanding multiple environment variables."""
        monkeypatch.setenv("VAR1", "value1")
        monkeypatch.setenv("VAR2", "value2")
        result = expand_env_vars("${VAR1} and ${VAR2}")
        assert result == "value1 and value2"

    def test_missing_var_raises_error(self) -> None:
        """Test that missing environment variable raises ValueError."""
        with pytest.raises(ValueError) as exc_info:
            expand_env_vars("${NONEXISTENT_VAR}")
        assert "NONEXISTENT_VAR" in str(exc_info.value)

    def test_no_vars_unchanged(self) -> None:
        """Test that strings without variables are unchanged."""
        result = expand_env_vars("plain string")
        assert result == "plain string"

    def test_empty_string(self) -> None:
        """Test that empty string is unchanged."""
        result = expand_env_vars("")
        assert result == ""


class TestExpandEnvVarsInDict:
    """Tests for expand_env_vars_in_dict function."""

    def test_expand_nested_dict(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test expanding variables in nested dictionaries."""
        monkeypatch.setenv("PASSWORD", "secret")
        data = {
            "level1": {
                "level2": {
                    "password": "${PASSWORD}",
                },
            },
        }
        result = expand_env_vars_in_dict(data)
        assert result["level1"]["level2"]["password"] == "secret"

    def test_expand_in_list(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test expanding variables in lists."""
        monkeypatch.setenv("VAR", "value")
        data = {
            "items": ["${VAR}", "plain"],
        }
        result = expand_env_vars_in_dict(data)
        assert result["items"] == ["value", "plain"]

    def test_preserve_non_strings(self) -> None:
        """Test that non-string values are preserved."""
        data = {
            "number": 42,
            "boolean": True,
            "none": None,
        }
        result = expand_env_vars_in_dict(data)
        assert result == data

    def test_original_not_modified(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test that original dict is not modified."""
        monkeypatch.setenv("VAR", "value")
        original = {"key": "${VAR}"}
        expand_env_vars_in_dict(original)
        assert original["key"] == "${VAR}"
