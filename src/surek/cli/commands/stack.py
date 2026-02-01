"""Stack management commands."""

from pathlib import Path
from typing import Optional

import typer
from rich.console import Console

from surek.core.config import load_stack_config
from surek.exceptions import StackConfigError

console = Console()


def deploy(
    stack_name: str = typer.Argument(..., help="Name of the stack to deploy"),
    force: bool = typer.Option(False, "--force", help="Force re-download even if cached"),
) -> None:
    """Deploy a stack (pull sources, transform compose, start containers)."""
    console.print(f"deploy {stack_name} - not yet implemented")


def start(
    stack_name: str = typer.Argument(..., help="Name of the stack to start"),
) -> None:
    """Start an already deployed stack without re-transformation."""
    console.print(f"start {stack_name} - not yet implemented")


def stop(
    stack_name: str = typer.Argument(..., help="Name of the stack to stop"),
) -> None:
    """Stop a running stack."""
    console.print(f"stop {stack_name} - not yet implemented")


def status(
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
) -> None:
    """Show status of all stacks with health and resource usage."""
    console.print("status - not yet implemented")


def info(
    stack_name: str = typer.Argument(..., help="Name of the stack"),
    logs: bool = typer.Option(False, "-l", "--logs", help="Include last 100 log lines"),
) -> None:
    """Show detailed information about a stack."""
    console.print(f"info {stack_name} - not yet implemented")


def logs(
    stack_name: str = typer.Argument(..., help="Name of the stack"),
    service: Optional[str] = typer.Argument(None, help="Optional specific service name"),
    follow: bool = typer.Option(True, "-f", "--follow", help="Follow log output"),
    tail: int = typer.Option(100, "-t", "--tail", help="Output last N lines"),
    no_follow: bool = typer.Option(False, "--no-follow", help="Disable follow mode"),
) -> None:
    """View logs for a stack or specific service."""
    console.print(f"logs {stack_name} - not yet implemented")


def validate(
    stack_path: Path = typer.Argument(..., help="Path to surek.stack.yml file"),
) -> None:
    """Validate a stack configuration file."""
    try:
        config = load_stack_config(stack_path)
        console.print(f"Loaded stack config with name '{config.name}' from {stack_path}")
        console.print("[green]Config is valid[/green]")
    except StackConfigError as e:
        console.print(f"[red]Error while loading config {stack_path}[/red]")
        console.print(str(e))
        raise typer.Exit(1)
