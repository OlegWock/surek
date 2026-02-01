"""Tests for Pydantic models."""

import pytest
from pydantic import ValidationError

from surek.models.config import SurekConfig
from surek.models.stack import GitHubSource, LocalSource, PublicEndpoint, StackConfig


class TestSurekConfig:
    """Tests for SurekConfig model."""

    def test_valid_minimal_config(self) -> None:
        """Test minimal valid configuration."""
        config = SurekConfig(
            root_domain="example.com",
            default_auth="admin:password",
        )
        assert config.root_domain == "example.com"
        assert config.default_auth == "admin:password"
        assert config.default_user == "admin"
        assert config.default_password == "password"

    def test_valid_full_config(self) -> None:
        """Test full configuration with all options."""
        config = SurekConfig(
            root_domain="example.com",
            default_auth="admin:secret123",
            backup={
                "password": "backup_pass",
                "s3_endpoint": "s3.example.com",
                "s3_bucket": "my-bucket",
                "s3_access_key": "ACCESS",
                "s3_secret_key": "SECRET",
            },
            github={"pat": "ghp_xxxx"},
            system_services={"portainer": True, "netdata": False},
        )
        assert config.backup is not None
        assert config.backup.s3_bucket == "my-bucket"
        assert config.github is not None
        assert config.github.pat == "ghp_xxxx"
        assert config.system_services.portainer is True
        assert config.system_services.netdata is False

    def test_invalid_auth_missing_colon(self) -> None:
        """Test that auth without colon is rejected."""
        with pytest.raises(ValidationError) as exc_info:
            SurekConfig(root_domain="example.com", default_auth="adminpassword")
        assert "missing ':'" in str(exc_info.value)

    def test_invalid_auth_multiple_colons(self) -> None:
        """Test that auth with multiple colons is rejected."""
        with pytest.raises(ValidationError) as exc_info:
            SurekConfig(root_domain="example.com", default_auth="admin:pass:word")
        assert "multiple ':'" in str(exc_info.value)

    def test_invalid_auth_empty_user(self) -> None:
        """Test that empty username is rejected."""
        with pytest.raises(ValidationError) as exc_info:
            SurekConfig(root_domain="example.com", default_auth=":password")
        assert "username cannot be empty" in str(exc_info.value)

    def test_invalid_auth_empty_password(self) -> None:
        """Test that empty password is rejected."""
        with pytest.raises(ValidationError) as exc_info:
            SurekConfig(root_domain="example.com", default_auth="admin:")
        assert "password cannot be empty" in str(exc_info.value)


class TestStackConfig:
    """Tests for StackConfig model."""

    def test_valid_local_stack(self) -> None:
        """Test valid local source stack."""
        config = StackConfig(
            name="my-stack",
            source={"type": "local"},
        )
        assert config.name == "my-stack"
        assert isinstance(config.source, LocalSource)
        assert config.compose_file_path == "./docker-compose.yml"

    def test_valid_github_stack(self) -> None:
        """Test valid GitHub source stack."""
        config = StackConfig(
            name="my-stack",
            source={"type": "github", "slug": "owner/repo#main"},
        )
        assert isinstance(config.source, GitHubSource)
        assert config.source.owner == "owner"
        assert config.source.repo == "repo"
        assert config.source.ref == "main"

    def test_github_source_default_ref(self) -> None:
        """Test GitHub source defaults to HEAD ref."""
        config = StackConfig(
            name="my-stack",
            source={"type": "github", "slug": "owner/repo"},
        )
        assert isinstance(config.source, GitHubSource)
        assert config.source.ref == "HEAD"

    def test_valid_stack_with_public_endpoints(self) -> None:
        """Test stack with public endpoints."""
        config = StackConfig(
            name="my-stack",
            source={"type": "local"},
            public=[
                {"domain": "app.example.com", "target": "myapp:8080"},
                {"domain": "api.example.com", "target": "api", "auth": "admin:pass"},
            ],
        )
        assert len(config.public) == 2
        assert config.public[0].service_name == "myapp"
        assert config.public[0].port == 8080
        assert config.public[1].port == 80  # default

    def test_invalid_stack_name_empty(self) -> None:
        """Test that empty stack name is rejected."""
        with pytest.raises(ValidationError) as exc_info:
            StackConfig(name="", source={"type": "local"})
        assert "cannot be empty" in str(exc_info.value)

    def test_invalid_stack_name_special_chars(self) -> None:
        """Test that invalid characters in stack name are rejected."""
        with pytest.raises(ValidationError) as exc_info:
            StackConfig(name="my.stack", source={"type": "local"})
        assert "must start with alphanumeric" in str(exc_info.value)

    def test_invalid_github_slug_no_slash(self) -> None:
        """Test that GitHub slug without slash is rejected."""
        with pytest.raises(ValidationError) as exc_info:
            StackConfig(name="my-stack", source={"type": "github", "slug": "owner-repo"})
        assert "owner/repo" in str(exc_info.value)


class TestPublicEndpoint:
    """Tests for PublicEndpoint model."""

    def test_service_name_with_port(self) -> None:
        """Test extracting service name when port is specified."""
        endpoint = PublicEndpoint(domain="app.example.com", target="myapp:8080")
        assert endpoint.service_name == "myapp"
        assert endpoint.port == 8080

    def test_service_name_without_port(self) -> None:
        """Test extracting service name when no port is specified."""
        endpoint = PublicEndpoint(domain="app.example.com", target="myapp")
        assert endpoint.service_name == "myapp"
        assert endpoint.port == 80
