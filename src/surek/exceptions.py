"""Surek exception hierarchy."""


class SurekError(Exception):
    """Base exception for Surek errors."""

    pass


class SurekConfigError(SurekError):
    """Configuration-related errors."""

    pass


class StackConfigError(SurekError):
    """Stack configuration errors."""

    pass


class DockerError(SurekError):
    """Docker-related errors."""

    pass


class BackupError(SurekError):
    """Backup operation errors."""

    pass


class GitHubError(SurekError):
    """GitHub API errors."""

    pass
