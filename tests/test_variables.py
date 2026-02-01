"""Tests for variable expansion."""

import pytest

from surek.core.variables import expand_variables, expand_variables_in_list
from surek.models.config import SurekConfig


@pytest.fixture
def config_minimal() -> SurekConfig:
    """Create a minimal SurekConfig for testing."""
    return SurekConfig(
        root_domain="example.com",
        default_auth="admin:secret123",
    )


@pytest.fixture
def config_with_backup() -> SurekConfig:
    """Create a SurekConfig with backup configuration."""
    return SurekConfig(
        root_domain="example.com",
        default_auth="admin:secret123",
        backup={
            "password": "backup_pass",
            "s3_endpoint": "s3.example.com",
            "s3_bucket": "my-bucket",
            "s3_access_key": "ACCESS_KEY",
            "s3_secret_key": "SECRET_KEY",
        },
    )


class TestExpandVariables:
    """Tests for expand_variables function."""

    def test_expand_root_domain(self, config_minimal: SurekConfig) -> None:
        """Test expanding <root> variable."""
        result = expand_variables("app.<root>", config_minimal)
        assert result == "app.example.com"

    def test_expand_default_auth(self, config_minimal: SurekConfig) -> None:
        """Test expanding <default_auth> variable."""
        result = expand_variables("<default_auth>", config_minimal)
        assert result == "admin:secret123"

    def test_expand_default_user(self, config_minimal: SurekConfig) -> None:
        """Test expanding <default_user> variable."""
        result = expand_variables("user=<default_user>", config_minimal)
        assert result == "user=admin"

    def test_expand_default_password(self, config_minimal: SurekConfig) -> None:
        """Test expanding <default_password> variable."""
        result = expand_variables("pass=<default_password>", config_minimal)
        assert result == "pass=secret123"

    def test_expand_multiple_variables(self, config_minimal: SurekConfig) -> None:
        """Test expanding multiple variables in one string."""
        result = expand_variables(
            "https://app.<root> with <default_user>:<default_password>",
            config_minimal,
        )
        assert result == "https://app.example.com with admin:secret123"

    def test_expand_backup_variables(self, config_with_backup: SurekConfig) -> None:
        """Test expanding backup-related variables."""
        result = expand_variables("<backup_password>", config_with_backup)
        assert result == "backup_pass"

        result = expand_variables("<backup_s3_endpoint>", config_with_backup)
        assert result == "s3.example.com"

        result = expand_variables("<backup_s3_bucket>", config_with_backup)
        assert result == "my-bucket"

    def test_no_expansion_without_variables(self, config_minimal: SurekConfig) -> None:
        """Test that strings without variables are unchanged."""
        result = expand_variables("plain string", config_minimal)
        assert result == "plain string"

    def test_backup_vars_not_expanded_when_not_configured(
        self, config_minimal: SurekConfig
    ) -> None:
        """Test that backup variables are not expanded when backup is not configured."""
        result = expand_variables("<backup_password>", config_minimal)
        # Variable should remain as-is since backup is not configured
        assert result == "<backup_password>"


class TestExpandVariablesInList:
    """Tests for expand_variables_in_list function."""

    def test_expand_list_of_strings(self, config_minimal: SurekConfig) -> None:
        """Test expanding variables in a list of strings."""
        values = [
            "DOMAIN=<root>",
            "USER=<default_user>",
            "PLAIN=value",
        ]
        result = expand_variables_in_list(values, config_minimal)
        assert result == [
            "DOMAIN=example.com",
            "USER=admin",
            "PLAIN=value",
        ]

    def test_expand_empty_list(self, config_minimal: SurekConfig) -> None:
        """Test expanding an empty list."""
        result = expand_variables_in_list([], config_minimal)
        assert result == []
