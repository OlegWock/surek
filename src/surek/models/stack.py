"""Pydantic models for stack configuration (surek.stack.yml)."""

import re
from typing import Annotated, Literal

from pydantic import BaseModel, Field, field_validator


class LocalSource(BaseModel):
    """Local source configuration - files already present in stack directory."""

    type: Literal["local"]

    @property
    def pretty(self) -> str:
        """Get a human-readable description of the source."""
        return "local"


class GitHubSource(BaseModel):
    """GitHub source configuration - download from GitHub repository."""

    type: Literal["github"]
    slug: str = Field(..., description="Format: 'owner/repo' or 'owner/repo#ref'")

    @property
    def owner(self) -> str:
        """Get the repository owner from the slug."""
        return self.slug.split("/")[0]

    @property
    def repo(self) -> str:
        """Get the repository name from the slug (without ref)."""
        repo_with_ref = self.slug.split("/")[1]
        return repo_with_ref.split("#")[0]

    @property
    def ref(self) -> str:
        """Get the ref (branch/tag/commit) from the slug, defaulting to HEAD."""
        if "#" in self.slug:
            return self.slug.split("#")[1]
        return "HEAD"

    @field_validator("slug")
    @classmethod
    def validate_slug_format(cls, v: str) -> str:
        """Validate the slug format."""
        if "/" not in v:
            raise ValueError("GitHub slug must be in 'owner/repo' or 'owner/repo#ref' format")
        parts = v.split("/")
        if len(parts) != 2:
            raise ValueError("GitHub slug must have exactly one '/' separator")
        if not parts[0]:
            raise ValueError("GitHub owner cannot be empty")
        repo_part = parts[1].split("#")[0]
        if not repo_part:
            raise ValueError("GitHub repo cannot be empty")
        return v

    @property
    def pretty(self) -> str:
        """Get a human-readable description of the source."""
        return f"GitHub {self.slug}"


# Discriminated union for source types
Source = Annotated[LocalSource | GitHubSource, Field(discriminator="type")]


class PublicEndpoint(BaseModel):
    """Public endpoint configuration for reverse proxy."""

    domain: str
    target: str = Field(..., description="Format: 'service:port' or 'service' (default port 80)")
    auth: str | None = Field(
        None, description="Format: 'user:password' or '<default_auth>'"
    )

    @property
    def service_name(self) -> str:
        """Get the service name from the target."""
        return self.target.split(":")[0]

    @property
    def port(self) -> int:
        """Get the port from the target, defaulting to 80."""
        if ":" in self.target:
            return int(self.target.split(":")[1])
        return 80


class EnvConfig(BaseModel):
    """Environment variable configuration."""

    shared: list[str] = Field(default_factory=list)
    by_container: dict[str, list[str]] = Field(default_factory=dict)


class BackupExcludeConfig(BaseModel):
    """Backup exclusion settings."""

    exclude_volumes: list[str] = Field(default_factory=list)


class StackConfig(BaseModel):
    """Stack configuration from surek.stack.yml."""

    name: str
    source: Source
    compose_file_path: str = "./docker-compose.yml"
    public: list[PublicEndpoint] = Field(default_factory=list)
    env: EnvConfig | None = None
    backup: BackupExcludeConfig = Field(default_factory=BackupExcludeConfig)

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        """Validate stack name format."""
        if not v or not v.strip():
            raise ValueError("Stack name cannot be empty")
        # Check for reserved names
        reserved_names = {"system", "surek-system"}
        if v.lower() in reserved_names:
            raise ValueError(f"'{v}' is a reserved stack name and cannot be used")
        # Validate characters suitable for Docker project names
        if not re.match(r"^[a-zA-Z0-9][a-zA-Z0-9_-]*$", v):
            raise ValueError(
                "Stack name must start with alphanumeric and contain only "
                "alphanumeric, underscore, or hyphen characters"
            )
        return v

    model_config = {"extra": "forbid"}
