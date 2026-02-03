"""Backup operations and S3 integration."""

import json
import subprocess
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import boto3
from botocore.exceptions import BotoCoreError, ClientError

from surek.exceptions import BackupError
from surek.models.config import BackupConfig
from surek.utils.logging import console, print_error
from surek.utils.paths import get_data_dir


@dataclass
class BackupInfo:
    """Information about a backup file in S3."""

    name: str
    backup_type: str  # "daily", "weekly", "monthly", "unknown"
    size: int
    created: datetime


@dataclass
class BackupFailure:
    """Record of a backup failure."""

    timestamp: str
    backup_type: str
    error: str
    notified: bool = False


def get_s3_client(config: BackupConfig) -> boto3.client:  # type: ignore[valid-type]
    """Create an S3 client for backup operations.

    Args:
        config: Backup configuration with S3 credentials.

    Returns:
        Configured boto3 S3 client.
    """
    return boto3.client(
        "s3",
        endpoint_url=f"https://{config.s3_endpoint}",
        aws_access_key_id=config.s3_access_key,
        aws_secret_access_key=config.s3_secret_key,
    )


def list_backups(config: BackupConfig) -> list[BackupInfo]:
    """List all backups in S3.

    Args:
        config: Backup configuration.

    Returns:
        List of backup information, sorted by date (newest first).

    Raises:
        BackupError: If S3 operation fails.
    """
    try:
        s3 = get_s3_client(config)
        response = s3.list_objects_v2(Bucket=config.s3_bucket)  # type: ignore[attr-defined]

        backups = []
        for obj in response.get("Contents", []):
            name = obj["Key"]

            # Determine backup type from filename
            if name.startswith("daily-"):
                backup_type = "daily"
            elif name.startswith("weekly-"):
                backup_type = "weekly"
            elif name.startswith("monthly-"):
                backup_type = "monthly"
            elif name.startswith("manual-"):
                backup_type = "manual"
            else:
                backup_type = "unknown"

            backups.append(
                BackupInfo(
                    name=name,
                    backup_type=backup_type,
                    size=obj["Size"],
                    created=obj["LastModified"],
                )
            )

        return sorted(backups, key=lambda b: b.created, reverse=True)

    except (BotoCoreError, ClientError) as e:
        raise BackupError(f"Failed to list backups: {e}") from e


def download_backup(config: BackupConfig, backup_name: str, target_path: Path) -> None:
    """Download a backup from S3.

    Args:
        config: Backup configuration.
        backup_name: Name of the backup file.
        target_path: Path to save the backup.

    Raises:
        BackupError: If download fails.
    """
    try:
        s3 = get_s3_client(config)
        s3.download_file(config.s3_bucket, backup_name, str(target_path))  # type: ignore[attr-defined]
    except (BotoCoreError, ClientError) as e:
        raise BackupError(f"Failed to download backup: {e}") from e


def trigger_backup() -> None:
    """Trigger a manual backup by executing command in backup container.

    Raises:
        BackupError: If backup trigger fails.
    """
    import docker
    from docker.errors import DockerException

    try:
        client = docker.from_env()

        # Find the backup container
        containers = client.containers.list(
            filters={"label": "com.docker.compose.service=backup"}
        )

        if not containers:
            raise BackupError("Backup container not found. Is system stack running?")

        container = containers[0]

        # Execute backup command with manual config (long retention, never auto-triggers)
        # Source the config file first, then run backup (required for multi-schedule setups)
        console.print("Triggering manual backup...")
        exit_code, output = container.exec_run(
            [
                "/bin/sh",
                "-c",
                "set -a; source /etc/dockervolumebackup/conf.d/backup-manual.env; set +a && backup",
            ],
            stream=False,
        )

        if exit_code != 0:
            error_msg = output.decode() if output else "Unknown error"
            record_backup_failure("manual", error_msg)
            raise BackupError(f"Backup failed: {error_msg}")

        console.print("[green]Backup completed successfully[/green]")

    except DockerException as e:
        record_backup_failure("manual", str(e))
        raise BackupError(f"Docker error: {e}") from e


def decrypt_and_extract_backup(
    backup_path: Path,
    password: str,
    target_dir: Path,
) -> None:
    """Decrypt and extract a backup archive.

    Args:
        backup_path: Path to the encrypted backup.
        password: GPG password for decryption.
        target_dir: Directory to extract to.

    Raises:
        BackupError: If decryption or extraction fails.
    """
    try:
        # Decrypt with GPG
        decrypted_path = backup_path.with_suffix("")
        subprocess.run(
            [
                "gpg",
                "--batch",
                "--yes",
                "--passphrase",
                password,
                "--output",
                str(decrypted_path),
                "--decrypt",
                str(backup_path),
            ],
            check=True,
            capture_output=True,
        )

        # Extract tar.gz
        target_dir.mkdir(parents=True, exist_ok=True)
        subprocess.run(
            ["tar", "-xzf", str(decrypted_path), "-C", str(target_dir)],
            check=True,
            capture_output=True,
        )

        # Cleanup decrypted file
        decrypted_path.unlink()

    except subprocess.CalledProcessError as e:
        error_msg = e.stderr.decode() if e.stderr else str(e)
        raise BackupError(f"Failed to decrypt/extract backup: {error_msg}") from e


# Failure tracking


def get_failure_log_path() -> Path:
    """Get path to backup failures log file."""
    return get_data_dir() / "backup_failures.json"


def load_failures() -> list[BackupFailure]:
    """Load backup failure history."""
    path = get_failure_log_path()
    if not path.exists():
        return []

    try:
        data = json.loads(path.read_text())
        return [BackupFailure(**f) for f in data]
    except (json.JSONDecodeError, OSError):
        return []


def record_backup_failure(backup_type: str, error: str) -> None:
    """Record a backup failure for tracking.

    Args:
        backup_type: Type of backup that failed.
        error: Error message.
    """
    failures = load_failures()

    failure = BackupFailure(
        timestamp=datetime.now(UTC).isoformat(),
        backup_type=backup_type,
        error=error,
        notified=False,
    )
    failures.append(failure)

    # Keep last 100 failures
    failures = failures[-100:]

    path = get_failure_log_path()
    path.write_text(json.dumps([f.__dict__ for f in failures], indent=2))

    print_error(f"Backup failed: {error}")


def get_recent_failures(limit: int = 10) -> list[BackupFailure]:
    """Get recent backup failures for display.

    Args:
        limit: Maximum number of failures to return.

    Returns:
        List of recent failures.
    """
    failures = load_failures()
    return failures[-limit:]


def format_bytes(num_bytes: int) -> str:
    """Format bytes as human-readable string."""
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if abs(num_bytes) < 1024.0:
            return f"{num_bytes:.1f} {unit}"
        num_bytes = int(num_bytes / 1024.0)
    return f"{num_bytes:.1f} PB"
