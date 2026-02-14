"""Backup management commands."""

import shutil
import tempfile
from pathlib import Path

import docker
import typer
from rich.console import Console
from rich.prompt import Confirm, Prompt
from rich.table import Table

from surek.core.backup import (
    decrypt_and_extract_backup,
    download_backup,
    list_backups,
    trigger_backup,
)
from surek.core.config import load_config, load_stack_config
from surek.core.deploy import deploy_system_stack, start_stack, stop_stack
from surek.core.docker import ensure_surek_network
from surek.core.stacks import get_available_stacks, get_stack_by_name
from surek.exceptions import BackupError, SurekError
from surek.utils.logging import format_bytes
from surek.utils.paths import get_data_dir, get_system_dir

console = Console()
app = typer.Typer(help="Backup management commands")


@app.callback(invoke_without_command=True)
def backup_default(ctx: typer.Context) -> None:
    """List all backups in S3 (default command)."""
    if ctx.invoked_subcommand is None:
        list_backups_cmd(json_output=False)


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
            if not backups:
                console.print("No backups found")
                return
            table = Table(title="Backups")
            table.add_column("Backup", style="cyan")
            table.add_column("Type")
            table.add_column("Size")
            table.add_column("Created")

            for backup in backups:
                # Color by type
                backup_type = backup.backup_type
                if backup_type == "daily":
                    type_text = f"[blue]{backup_type}[/blue]"
                elif backup_type == "weekly":
                    type_text = f"[green]{backup_type}[/green]"
                elif backup_type == "monthly":
                    type_text = f"[magenta]{backup_type}[/magenta]"
                elif backup_type == "manual":
                    type_text = f"[yellow]{backup_type}[/yellow]"
                else:
                    type_text = backup_type

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
def run_backup() -> None:
    """Trigger an immediate backup."""
    try:
        config = load_config()

        if not config.backup:
            console.print("[yellow]Backup is not configured in surek.yml[/yellow]")
            raise typer.Exit(1) from None

        trigger_backup()

    except (SurekError, BackupError) as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1) from None


@app.command(name="restore")
def restore_backup(
    backup_id: str | None = typer.Option(None, "--id", help="Backup filename to restore"),
    stack: str | None = typer.Option(None, "--stack", help="Stack to restore"),
    volume: str | None = typer.Option(None, "--volume", help="Specific volume to restore"),
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

        console.print(f"\nRestoring from backup: {backup_id}", highlight=False)

        if not Confirm.ask("This will stop affected stacks. Continue?", default=False):
            console.print("[yellow]Aborted[/yellow]")
            raise typer.Exit(0)

        stopped_stacks: list[str] = []

        def is_stack_running(name: str) -> bool:
            """Check if a stack has any running containers."""
            try:
                client = docker.from_env()
                containers = client.containers.list(
                    filters={"label": f"com.docker.compose.project={name}"}
                )
                return len(containers) > 0
            except Exception:
                return False

        if stack:
            console.print(f"Stopping stack {stack}...")
            stack_info = get_stack_by_name(stack)
            if stack_info.config and is_stack_running(stack):
                stop_stack(stack_info.config, silent=True)
                stopped_stacks.append(stack)
        else:
            console.print("Stopping all stacks...")

            try:
                system_dir = get_system_dir()
                system_config = load_stack_config(system_dir / "surek.stack.yml")
                if is_stack_running(system_config.name):
                    stop_stack(system_config, silent=True)
                    stopped_stacks.append("system")
            except SurekError:
                pass

            try:
                for s in get_available_stacks():
                    if s.valid and s.config and is_stack_running(s.config.name):
                        stop_stack(s.config, silent=True)
                        stopped_stacks.append(s.config.name)
            except SurekError:
                pass

        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            backup_path = temp_path / backup_id

            console.print(f"Downloading backup {backup_id}...", highlight=False)
            download_backup(config.backup, backup_id, backup_path)

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
                        console.print(f"  Restoring {stack_dir.name}/{volume_dir.name}...")

                        if target_volume_dir.exists():
                            shutil.rmtree(target_volume_dir)
                        shutil.move(volume_dir, target_volume_dir)

        # Restart stopped stacks
        console.print("\nRestarting stacks...")
        for stack_name in stopped_stacks:
            try:
                if stack_name == "system":
                    ensure_surek_network()
                    deploy_system_stack(config)
                else:
                    stack_info = get_stack_by_name(stack_name)
                    if stack_info.config:
                        start_stack(stack_info.config)
                console.print(f"  Started {stack_name}")
            except SurekError as e:
                console.print(f"  [yellow]Failed to start {stack_name}: {e}[/yellow]")

        console.print("\n[green]Restore completed.[/green]")

    except (SurekError, BackupError) as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1) from None
