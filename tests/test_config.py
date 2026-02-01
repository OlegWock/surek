"""Tests for configuration loading."""

from pathlib import Path
from textwrap import dedent

import pytest

from surek.core.config import load_config, load_stack_config
from surek.exceptions import StackConfigError, SurekConfigError


class TestLoadConfig:
    """Tests for load_config function."""

    def test_load_valid_config(self, tmp_path: Path) -> None:
        """Test loading a valid config file."""
        config_file = tmp_path / "surek.yml"
        config_file.write_text(
            dedent("""
            root_domain: example.com
            default_auth: admin:password
        """)
        )

        config = load_config(config_file)
        assert config.root_domain == "example.com"
        assert config.default_user == "admin"

    def test_load_config_with_env_vars(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test environment variable expansion in config."""
        monkeypatch.setenv("SUREK_PASSWORD", "secret123")

        config_file = tmp_path / "surek.yml"
        config_file.write_text(
            dedent("""
            root_domain: example.com
            default_auth: admin:${SUREK_PASSWORD}
        """)
        )

        config = load_config(config_file)
        assert config.default_password == "secret123"

    def test_load_config_missing_env_var(self, tmp_path: Path) -> None:
        """Test error when environment variable is not set."""
        config_file = tmp_path / "surek.yml"
        config_file.write_text(
            dedent("""
            root_domain: example.com
            default_auth: admin:${MISSING_VAR}
        """)
        )

        with pytest.raises(SurekConfigError) as exc_info:
            load_config(config_file)
        assert "MISSING_VAR" in str(exc_info.value)

    def test_load_config_not_found(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test error when config file is not found."""
        monkeypatch.chdir(tmp_path)

        with pytest.raises(SurekConfigError) as exc_info:
            load_config()
        assert "not found" in str(exc_info.value)

    def test_load_config_invalid_yaml(self, tmp_path: Path) -> None:
        """Test error when config has invalid YAML."""
        config_file = tmp_path / "surek.yml"
        config_file.write_text("invalid: yaml: content:")

        with pytest.raises(SurekConfigError) as exc_info:
            load_config(config_file)
        assert "Invalid YAML" in str(exc_info.value)

    def test_load_config_empty_file(self, tmp_path: Path) -> None:
        """Test error when config file is empty."""
        config_file = tmp_path / "surek.yml"
        config_file.write_text("")

        with pytest.raises(SurekConfigError) as exc_info:
            load_config(config_file)
        assert "empty" in str(exc_info.value)


class TestLoadStackConfig:
    """Tests for load_stack_config function."""

    def test_load_valid_stack_config(self, tmp_path: Path) -> None:
        """Test loading a valid stack config."""
        config_file = tmp_path / "surek.stack.yml"
        config_file.write_text(
            dedent("""
            name: my-stack
            source:
              type: local
            public:
              - domain: app.<root>
                target: myapp:8080
        """)
        )

        config = load_stack_config(config_file)
        assert config.name == "my-stack"
        assert len(config.public) == 1

    def test_load_stack_config_github_source(self, tmp_path: Path) -> None:
        """Test loading a stack config with GitHub source."""
        config_file = tmp_path / "surek.stack.yml"
        config_file.write_text(
            dedent("""
            name: my-stack
            source:
              type: github
              slug: owner/repo#main
        """)
        )

        config = load_stack_config(config_file)
        from surek.models.stack import GitHubSource

        assert isinstance(config.source, GitHubSource)
        assert config.source.owner == "owner"
        assert config.source.repo == "repo"
        assert config.source.ref == "main"

    def test_load_stack_config_not_found(self, tmp_path: Path) -> None:
        """Test error when stack config is not found."""
        config_file = tmp_path / "nonexistent.yml"

        with pytest.raises(StackConfigError) as exc_info:
            load_stack_config(config_file)
        assert "not found" in str(exc_info.value)

    def test_load_stack_config_with_env_vars(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Test environment variable expansion in stack config."""
        monkeypatch.setenv("MY_DOMAIN", "myapp.example.com")

        config_file = tmp_path / "surek.stack.yml"
        config_file.write_text(
            dedent("""
            name: my-stack
            source:
              type: local
            public:
              - domain: ${MY_DOMAIN}
                target: myapp:8080
        """)
        )

        config = load_stack_config(config_file)
        assert config.public[0].domain == "myapp.example.com"
