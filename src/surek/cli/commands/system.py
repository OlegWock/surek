"""System container management commands."""

import subprocess

import typer
from rich.console import Console
from rich.prompt import Confirm

from surek.core.config import load_config
from surek.core.deploy import deploy_system_stack, stop_stack
from surek.core.docker import ensure_surek_network
from surek.exceptions import SurekError
from surek.utils.paths import get_system_dir

console = Console()
app = typer.Typer(help="System container management")


@app.command(name="start")
def start() -> None:
    """Ensure correct Docker configuration and run system containers."""
    try:
        config = load_config()
        console.print("Loaded config")

        # Ensure network exists
        ensure_surek_network()

        # Stop existing system containers (silent)
        from surek.core.config import load_stack_config

        system_dir = get_system_dir()
        system_config = load_stack_config(system_dir / "surek.stack.yml")
        stop_stack(system_config, silent=True)

        # Deploy system stack
        deploy_system_stack(config)

    except SurekError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1) from None


@app.command(name="stop")
def stop() -> None:
    """Stop Surek system containers."""
    try:
        from surek.core.config import load_stack_config

        system_dir = get_system_dir()
        system_config = load_stack_config(system_dir / "surek.stack.yml")
        stop_stack(system_config, silent=False)

    except SurekError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1) from None


@app.command(name="prune")
def prune(
    volumes: bool = typer.Option(False, "--volumes", "-v", help="Also remove unused volumes"),
    force: bool = typer.Option(False, "--force", "-f", help="Skip confirmation prompt"),
) -> None:
    """Remove unused Docker resources (containers, networks, images)."""
    try:
        if not force:
            msg = "This will remove unused containers, networks, and images"
            if volumes:
                msg += " [red]and volumes[/red]"
            console.print(msg)
            if not Confirm.ask("Continue?", default=False):
                console.print("[dim]Aborted[/dim]")
                raise typer.Exit(0)

        console.print("Pruning unused Docker resources...")

        # Prune containers
        result = subprocess.run(
            ["docker", "container", "prune", "-f"],
            capture_output=True,
            text=True,
        )
        if result.returncode == 0:
            console.print("[green]✓[/green] Removed unused containers")

        # Prune networks
        result = subprocess.run(
            ["docker", "network", "prune", "-f"],
            capture_output=True,
            text=True,
        )
        if result.returncode == 0:
            console.print("[green]✓[/green] Removed unused networks")

        # Prune images
        result = subprocess.run(
            ["docker", "image", "prune", "-f"],
            capture_output=True,
            text=True,
        )
        if result.returncode == 0:
            console.print("[green]✓[/green] Removed unused images")

        # Prune volumes if requested
        if volumes:
            result = subprocess.run(
                ["docker", "volume", "prune", "-f"],
                capture_output=True,
                text=True,
            )
            if result.returncode == 0:
                console.print("[green]✓[/green] Removed unused volumes")

        console.print("\n[green]Prune completed[/green]")

    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1) from None
