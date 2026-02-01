"""Backup management commands."""

from typing import Optional

import typer

app = typer.Typer(help="Backup management commands")


@app.callback(invoke_without_command=True)
def backup_list(ctx: typer.Context) -> None:
    """List all backups in S3 (default command)."""
    if ctx.invoked_subcommand is None:
        typer.echo("backup list - not yet implemented")


@app.command(name="list")
def list_backups() -> None:
    """List all backups in S3."""
    typer.echo("backup list - not yet implemented")


@app.command(name="run")
def run_backup(
    backup_type: str = typer.Option("daily", "--type", help="Backup type: daily, weekly, monthly"),
) -> None:
    """Trigger an immediate backup."""
    typer.echo(f"backup run --type={backup_type} - not yet implemented")


@app.command(name="restore")
def restore_backup(
    backup_id: Optional[str] = typer.Option(None, "--id", help="Backup filename to restore"),
    stack: Optional[str] = typer.Option(None, "--stack", help="Stack to restore"),
    volume: Optional[str] = typer.Option(None, "--volume", help="Specific volume to restore"),
) -> None:
    """Restore volumes from a backup."""
    if backup_id is None:
        typer.echo("backup restore (interactive) - not yet implemented")
    else:
        typer.echo(f"backup restore --id={backup_id} - not yet implemented")
