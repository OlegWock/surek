"""Backup operations and S3 integration."""

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Literal

import boto3
from botocore.exceptions import BotoCoreError, ClientError

from surek.core.stacks import SYSTEM_STACK_NAME
from surek.exceptions import BackupError
from surek.models.config import BackupConfig
from surek.utils.logging import console, print_dim, run_command

BackupType = Literal["daily", "weekly", "monthly", "manual", "unknown"]


@dataclass
class BackupInfo:
    """Information about a backup file in S3."""

    name: str
    backup_type: BackupType
    size: int
    created: datetime


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
            backup_type: BackupType
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
            filters={
                "label": [
                    f"com.docker.compose.project={SYSTEM_STACK_NAME}",
                    "com.docker.compose.service=backup",
                ]
            }
        )

        if not containers:
            raise BackupError("Backup container not found. Is system stack running?")

        container = containers[0]

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
            raise BackupError(f"Backup failed: {error_msg}")

        console.print("[green]Backup completed successfully[/green]")

    except DockerException as e:
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
    decrypted_path = backup_path.with_suffix("")
    gpg_cmd = [
        "gpg",
        "--batch",
        "--yes",
        "--passphrase",
        password,
        "--output",
        str(decrypted_path),
        "--decrypt",
        str(backup_path),
    ]

    censored_cmd = gpg_cmd.copy()
    censored_cmd[censored_cmd.index("--passphrase") + 1] = "***"
    print_dim(f"$ {' '.join(censored_cmd)}")

    try:
        run_command(gpg_cmd, capture_output=True, silent=True)
    except Exception as e:
        raise BackupError(f"Failed to decrypt backup: {e}") from e

    target_dir.mkdir(parents=True, exist_ok=True)
    try:
        run_command(
            ["tar", "-xzf", str(decrypted_path), "-C", str(target_dir)], capture_output=True
        )
    except Exception as e:
        raise BackupError(f"Failed to extract backup: {e}") from e

    decrypted_path.unlink()
