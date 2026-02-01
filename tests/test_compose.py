"""Tests for Docker Compose file transformation."""

from pathlib import Path
from textwrap import dedent
from unittest.mock import patch

import pytest

from surek.core.compose import (
    read_compose_file,
    transform_compose_file,
    transform_system_compose,
)
from surek.exceptions import SurekError
from surek.models.config import SurekConfig
from surek.models.stack import StackConfig


@pytest.fixture
def surek_config() -> SurekConfig:
    """Create a SurekConfig for testing."""
    return SurekConfig(
        root_domain="example.com",
        default_auth="admin:secret123",
    )


@pytest.fixture
def stack_config() -> StackConfig:
    """Create a basic StackConfig for testing."""
    return StackConfig(
        name="test-stack",
        source={"type": "local"},
    )


class TestReadComposeFile:
    """Tests for read_compose_file function."""

    def test_read_valid_file(self, tmp_path: Path) -> None:
        """Test reading a valid compose file."""
        compose_file = tmp_path / "docker-compose.yml"
        compose_file.write_text(
            dedent("""
            services:
              web:
                image: nginx
        """)
        )

        spec = read_compose_file(compose_file)
        assert "services" in spec
        assert "web" in spec["services"]

    def test_read_empty_file(self, tmp_path: Path) -> None:
        """Test error when file is empty."""
        compose_file = tmp_path / "docker-compose.yml"
        compose_file.write_text("")

        with pytest.raises(SurekError) as exc_info:
            read_compose_file(compose_file)
        assert "empty" in str(exc_info.value)

    def test_read_nonexistent_file(self, tmp_path: Path) -> None:
        """Test error when file doesn't exist."""
        compose_file = tmp_path / "nonexistent.yml"

        with pytest.raises(SurekError):
            read_compose_file(compose_file)


class TestTransformComposeFile:
    """Tests for transform_compose_file function."""

    def test_network_injection(
        self, surek_config: SurekConfig, stack_config: StackConfig, tmp_path: Path
    ) -> None:
        """Test that Surek network is added."""
        spec = {
            "version": "3.8",
            "services": {
                "web": {"image": "nginx"},
            },
        }

        with patch("surek.core.compose.get_stack_volumes_dir", return_value=tmp_path):
            result = transform_compose_file(spec, stack_config, surek_config)

        assert "networks" in result
        assert "surek" in result["networks"]
        assert result["networks"]["surek"]["external"] is True

    def test_service_network_injection(
        self, surek_config: SurekConfig, stack_config: StackConfig, tmp_path: Path
    ) -> None:
        """Test that services are connected to Surek network."""
        spec = {
            "version": "3.8",
            "services": {
                "web": {"image": "nginx"},
            },
        }

        with patch("surek.core.compose.get_stack_volumes_dir", return_value=tmp_path):
            result = transform_compose_file(spec, stack_config, surek_config)

        assert "networks" in result["services"]["web"]
        assert "surek" in result["services"]["web"]["networks"]

    def test_skip_network_for_network_mode(
        self, surek_config: SurekConfig, stack_config: StackConfig, tmp_path: Path
    ) -> None:
        """Test that network injection is skipped when network_mode is set."""
        spec = {
            "version": "3.8",
            "services": {
                "web": {"image": "nginx", "network_mode": "host"},
            },
        }

        with patch("surek.core.compose.get_stack_volumes_dir", return_value=tmp_path):
            result = transform_compose_file(spec, stack_config, surek_config)

        # Service should not have networks added
        assert "networks" not in result["services"]["web"]

    def test_volume_transformation(
        self, surek_config: SurekConfig, stack_config: StackConfig, tmp_path: Path
    ) -> None:
        """Test that volumes are converted to bind mounts."""
        spec = {
            "version": "3.8",
            "services": {
                "web": {"image": "nginx"},
            },
            "volumes": {
                "data": {},
            },
        }

        with patch("surek.core.compose.get_stack_volumes_dir", return_value=tmp_path):
            result = transform_compose_file(spec, stack_config, surek_config)

        assert result["volumes"]["data"]["driver"] == "local"
        assert result["volumes"]["data"]["driver_opts"]["type"] == "none"
        assert result["volumes"]["data"]["driver_opts"]["o"] == "bind"
        assert "surek.managed" in result["volumes"]["data"]["labels"]

    def test_skip_preconfigured_volumes(
        self, surek_config: SurekConfig, stack_config: StackConfig, tmp_path: Path
    ) -> None:
        """Test that pre-configured volumes are not transformed."""
        spec = {
            "version": "3.8",
            "services": {
                "web": {"image": "nginx"},
            },
            "volumes": {
                "data": {"driver": "custom"},
            },
        }

        with patch("surek.core.compose.get_stack_volumes_dir", return_value=tmp_path):
            result = transform_compose_file(spec, stack_config, surek_config)

        # Should remain unchanged
        assert result["volumes"]["data"]["driver"] == "custom"

    def test_public_endpoint_labels(self, surek_config: SurekConfig, tmp_path: Path) -> None:
        """Test that Caddy labels are added for public endpoints."""
        stack_config = StackConfig(
            name="test-stack",
            source={"type": "local"},
            public=[
                {"domain": "app.<root>", "target": "web:8080"},
            ],
        )

        spec = {
            "version": "3.8",
            "services": {
                "web": {"image": "nginx"},
            },
        }

        with patch("surek.core.compose.get_stack_volumes_dir", return_value=tmp_path):
            result = transform_compose_file(spec, stack_config, surek_config)

        labels = result["services"]["web"]["labels"]
        assert labels["caddy"] == "app.example.com"
        assert "{{upstreams 8080}}" in labels["caddy.reverse_proxy"]

    def test_public_endpoint_with_auth(self, surek_config: SurekConfig, tmp_path: Path) -> None:
        """Test that basic auth labels are added."""
        stack_config = StackConfig(
            name="test-stack",
            source={"type": "local"},
            public=[
                {"domain": "app.<root>", "target": "web:8080", "auth": "<default_auth>"},
            ],
        )

        spec = {
            "version": "3.8",
            "services": {
                "web": {"image": "nginx"},
            },
        }

        with patch("surek.core.compose.get_stack_volumes_dir", return_value=tmp_path):
            result = transform_compose_file(spec, stack_config, surek_config)

        labels = result["services"]["web"]["labels"]
        assert "caddy.basic_auth" in labels
        assert "caddy.basic_auth.admin" in labels
        # Password should be bcrypt hashed and escaped
        assert "$$" in labels["caddy.basic_auth.admin"]

    def test_missing_service_error(self, surek_config: SurekConfig, tmp_path: Path) -> None:
        """Test error when public endpoint references missing service."""
        stack_config = StackConfig(
            name="test-stack",
            source={"type": "local"},
            public=[
                {"domain": "app.<root>", "target": "nonexistent:8080"},
            ],
        )

        spec = {
            "version": "3.8",
            "services": {
                "web": {"image": "nginx"},
            },
        }

        with patch("surek.core.compose.get_stack_volumes_dir", return_value=tmp_path):
            with pytest.raises(SurekError) as exc_info:
                transform_compose_file(spec, stack_config, surek_config)
            assert "nonexistent" in str(exc_info.value)

    def test_environment_injection(self, surek_config: SurekConfig, tmp_path: Path) -> None:
        """Test that environment variables are injected."""
        stack_config = StackConfig(
            name="test-stack",
            source={"type": "local"},
            env={
                "shared": ["TZ=UTC"],
                "by_container": {
                    "web": ["APP_ENV=production"],
                },
            },
        )

        spec = {
            "version": "3.8",
            "services": {
                "web": {"image": "nginx"},
                "db": {"image": "postgres"},
            },
        }

        with patch("surek.core.compose.get_stack_volumes_dir", return_value=tmp_path):
            result = transform_compose_file(spec, stack_config, surek_config)

        # web should have both shared and container-specific env
        assert "TZ=UTC" in result["services"]["web"]["environment"]
        assert "APP_ENV=production" in result["services"]["web"]["environment"]

        # db should only have shared env
        assert "TZ=UTC" in result["services"]["db"]["environment"]
        assert "APP_ENV=production" not in result["services"]["db"]["environment"]


class TestTransformSystemCompose:
    """Tests for transform_system_compose function."""

    def test_remove_backup_when_not_configured(self) -> None:
        """Test that backup service is removed when not configured."""
        config = SurekConfig(
            root_domain="example.com",
            default_auth="admin:password",
        )

        spec = {
            "services": {
                "caddy": {"image": "caddy"},
                "backup": {"image": "backup"},
            },
        }

        result = transform_system_compose(spec, config)
        assert "caddy" in result["services"]
        assert "backup" not in result["services"]

    def test_keep_backup_when_configured(self) -> None:
        """Test that backup service is kept when configured."""
        config = SurekConfig(
            root_domain="example.com",
            default_auth="admin:password",
            backup={
                "password": "pass",
                "s3_endpoint": "s3.example.com",
                "s3_bucket": "bucket",
                "s3_access_key": "key",
                "s3_secret_key": "secret",
            },
        )

        spec = {
            "services": {
                "caddy": {"image": "caddy"},
                "backup": {"image": "backup"},
            },
        }

        result = transform_system_compose(spec, config)
        assert "backup" in result["services"]

    def test_remove_disabled_services(self) -> None:
        """Test that disabled system services are removed."""
        config = SurekConfig(
            root_domain="example.com",
            default_auth="admin:password",
            system_services={"portainer": False, "netdata": False},
        )

        spec = {
            "services": {
                "caddy": {"image": "caddy"},
                "portainer": {"image": "portainer"},
                "netdata": {"image": "netdata"},
            },
        }

        result = transform_system_compose(spec, config)
        assert "caddy" in result["services"]
        assert "portainer" not in result["services"]
        assert "netdata" not in result["services"]
