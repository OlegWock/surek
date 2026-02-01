"""Backup management commands."""

import shutil
import tempfile
from pathlib import Path

import typer
from rich.console import Console
from rich.prompt import Confirm, Prompt
from rich.table import Table

from surek.core.backup import (
    decrypt_and_extract_backup,
    download_backup,
    format_bytes,
    list_backups,
    trigger_backup,
)
from surek.core.config import load_config
from surek.core.deploy import stop_stack
from surek.core.stacks import get_available_stacks, get_stack_by_name
from surek.exceptions import BackupError, SurekError
from surek.utils.paths import get_data_dir

console = Console()
app = typer.Typer(help="Backup management commands")


@app.callback(invoke_without_command=True)
def backup_default(ctx: typer.Context) -> None:
    """List all backups in S3 (default command)."""
    if ctx.invoked_subcommand is None:
        list_backups_cmd()


@app.command(name="list")
def list_backups_cmd(
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
) -> None:
    """List all backups in S3."""
    try:
        config = load_config()

        if not config.backup:
            console.print("[yellow]Backup is not configured in surek.yml[/yellow]")
            raise typer.Exit(1) from None

        backups = list_backups(config.backup)

        if not backups:
            console.print("No backups found")
            return

        if json_output:
            import json

            data = [
                {
                    "name": b.name,
                    "type": b.backup_type,
                    "size": b.size,
                    "created": b.created.isoformat(),
                }
                for b in backups
            ]
            console.print(json.dumps(data, indent=2))
        else:
            table = Table(title="Backups")
            table.add_column("Backup", style="cyan")
            table.add_column("Type")
            table.add_column("Size")
            table.add_column("Created")

            for backup in backups:
                # Color by type
                type_text = backup.backup_type
                if type_text == "daily":
                    type_text = f"[blue]{type_text}[/blue]"
                elif type_text == "weekly":
                    type_text = f"[green]{type_text}[/green]"
                elif type_text == "monthly":
                    type_text = f"[magenta]{type_text}[/magenta]"

                table.add_row(
                    backup.name,
                    type_text,
                    format_bytes(backup.size),
                    backup.created.strftime("%Y-%m-%d %H:%M"),
                )

            console.print(table)

    except SurekError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1) from None


@app.command(name="run")
def run_backup(
    backup_type: str = typer.Option(
        "daily", "--type", "-t", help="Backup type: daily, weekly, monthly"
    ),
) -> None:
    """Trigger an immediate backup."""
    try:
        config = load_config()

        if not config.backup:
            console.print("[yellow]Backup is not configured in surek.yml[/yellow]")
            raise typer.Exit(1) from None

        if backup_type not in ("daily", "weekly", "monthly"):
            console.print(f"[red]Invalid backup type: {backup_type}[/red]")
            console.print("Valid types: daily, weekly, monthly")
            raise typer.Exit(1) from None

        trigger_backup(backup_type)

    except (SurekError, BackupError) as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1) from None


@app.command(name="restore")
def restore_backup(
    backup_id: str | None = typer.Option(
        None, "--id", help="Backup filename to restore"
    ),
    stack: str | None = typer.Option(None, "--stack", help="Stack to restore"),
    volume: str | None = typer.Option(
        None, "--volume", help="Specific volume to restore"
    ),
) -> None:
    """Restore volumes from a backup."""
    try:
        config = load_config()

        if not config.backup:
            console.print("[yellow]Backup is not configured in surek.yml[/yellow]")
            raise typer.Exit(1) from None

        # Interactive mode if no backup_id
        if backup_id is None:
            backups = list_backups(config.backup)
            if not backups:
                console.print("No backups found")
                raise typer.Exit(1) from None

            console.print("\n[bold]Available backups:[/bold]")
            for i, b in enumerate(backups[:20], 1):
                console.print(
                    f"  {i}. {b.name} ({format_bytes(b.size)}, {b.created.strftime('%Y-%m-%d %H:%M')})"
                )

            choice = Prompt.ask(
                "\nEnter backup number to restore",
                default="1",
            )
            try:
                idx = int(choice) - 1
                if idx < 0 or idx >= len(backups):
                    raise ValueError()
                backup_id = backups[idx].name
            except ValueError:
                console.print("[red]Invalid selection[/red]")
                raise typer.Exit(1) from None

        console.print(f"\nRestoring from backup: {backup_id}")

        # Confirm
        if not Confirm.ask("This will stop affected stacks. Continue?", default=False):
            console.print("[yellow]Aborted[/yellow]")
            raise typer.Exit(0)

        # Stop affected stacks
        if stack:
            console.print(f"Stopping stack {stack}...")
            stack_info = get_stack_by_name(stack)
            if stack_info.config:
                stop_stack(stack_info.config, silent=True)
        else:
            console.print("Stopping all stacks...")
            try:
                for s in get_available_stacks():
                    if s.valid and s.config:
                        stop_stack(s.config, silent=True)
            except SurekError:
                pass  # No stacks directory

        # Download backup
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            backup_path = temp_path / backup_id

            console.print(f"Downloading backup {backup_id}...")
            download_backup(config.backup, backup_id, backup_path)

            # Decrypt and extract
            console.print("Decrypting and extracting...")
            extract_dir = temp_path / "extracted"
            decrypt_and_extract_backup(backup_path, config.backup.password, extract_dir)

            # Restore volumes
            volumes_dir = get_data_dir() / "volumes"
            backup_volumes = extract_dir / "backup"  # docker-volume-backup structure

            if backup_volumes.exists():
                for stack_dir in backup_volumes.iterdir():
                    if stack and stack_dir.name != stack:
                        continue

                    target_stack_dir = volumes_dir / stack_dir.name
                    target_stack_dir.mkdir(parents=True, exist_ok=True)

                    for volume_dir in stack_dir.iterdir():
                        if volume and volume_dir.name != volume:
                            continue

                        target_volume_dir = target_stack_dir / volume_dir.name
                        console.print(
                            f"  Restoring {stack_dir.name}/{volume_dir.name}..."
                        )

                        if target_volume_dir.exists():
                            shutil.rmtree(target_volume_dir)
                        shutil.copytree(volume_dir, target_volume_dir)

        console.print(
            "\n[green]Restore completed. Start your stacks with 'surek start <stack>'[/green]"
        )

    except (SurekError, BackupError) as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1) from None
