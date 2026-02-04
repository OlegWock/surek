"""Pydantic models for main Surek configuration (surek.yml)."""

from pydantic import BaseModel, Field, field_validator, model_validator


class BackupConfig(BaseModel):
    """S3 backup configuration."""

    password: str
    s3_endpoint: str
    s3_bucket: str
    s3_access_key: str
    s3_secret_key: str


class GitHubConfig(BaseModel):
    """GitHub authentication configuration."""

    pat: str


class SystemServicesConfig(BaseModel):
    """Control which system services are enabled."""

    portainer: bool = True
    netdata: bool = True


class SurekConfig(BaseModel):
    """Main Surek configuration from surek.yml."""

    root_domain: str
    default_auth: str = Field(..., description="Format: 'user:password'")
    backup: BackupConfig | None = None
    github: GitHubConfig | None = None
    system_services: SystemServicesConfig = Field(default_factory=SystemServicesConfig)

    # Parsed from default_auth (set by validator)
    default_user: str = ""
    default_password: str = ""

    @field_validator("default_auth")
    @classmethod
    def validate_auth_format(cls, v: str) -> str:
        """Validate that default_auth is in 'user:password' format."""
        if ":" not in v:
            raise ValueError("default_auth must be in 'user:password' format (missing ':')")
        if v.count(":") != 1:
            raise ValueError("default_auth must be in 'user:password' format (multiple ':' found)")
        user, password = v.split(":")
        if not user:
            raise ValueError("default_auth username cannot be empty")
        if not password:
            raise ValueError("default_auth password cannot be empty")
        return v

    @model_validator(mode="after")
    def parse_default_auth(self) -> "SurekConfig":
        """Parse default_auth into user and password fields."""
        if self.default_auth and ":" in self.default_auth:
            user, password = self.default_auth.split(":", 1)
            object.__setattr__(self, "default_user", user)
            object.__setattr__(self, "default_password", password)
        return self

    model_config = {"extra": "forbid"}
