"""System container management commands."""

import shutil
import subprocess

import typer
from rich.console import Console
from rich.prompt import Confirm

from surek.core.config import load_config
from surek.core.deploy import deploy_system_stack, stop_stack
from surek.core.docker import ensure_surek_network
from surek.core.stacks import get_available_stacks
from surek.exceptions import SurekError
from surek.utils.paths import get_data_dir, get_system_dir

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


def _find_orphan_volume_folders() -> list[tuple[str, str]]:
    """Find volume folders that don't belong to any known stack.

    Returns:
        List of (stack_name, folder_path) tuples for orphan folders.
    """
    volumes_base = get_data_dir() / "volumes"
    if not volumes_base.exists():
        return []

    # Get all known stack names (including system)
    known_stacks = {"surek-system"}
    try:
        stacks = get_available_stacks()
        for stack in stacks:
            if stack.valid and stack.config:
                known_stacks.add(stack.config.name)
    except SurekError:
        pass

    # Find folders that don't match any known stack
    orphans: list[tuple[str, str]] = []
    for folder in volumes_base.iterdir():
        if folder.is_dir() and folder.name not in known_stacks:
            orphans.append((folder.name, str(folder)))

    return orphans


@app.command(name="prune")
def prune(
    volumes: bool = typer.Option(False, "--volumes", "-v", help="Also remove unused volumes"),
    force: bool = typer.Option(False, "--force", "-f", help="Skip confirmation prompt"),
) -> None:
    """Remove unused Docker resources (containers, networks, images)."""
    try:
        # Find orphan volume folders
        orphan_folders = _find_orphan_volume_folders()

        if not force:
            msg = "This will remove unused containers, networks, and images"
            if volumes:
                msg += " [red]and volumes[/red]"
            if orphan_folders:
                msg += f"\n\nFound {len(orphan_folders)} orphan volume folder(s):"
                for name, path in orphan_folders:
                    msg += f"\n  • {name} ({path})"
            console.print(msg)
            if not Confirm.ask("\nContinue?", default=False):
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
                console.print("[green]✓[/green] Removed unused Docker volumes")

            # Remove orphan volume folders
            if orphan_folders:
                for name, path in orphan_folders:
                    try:
                        shutil.rmtree(path)
                        console.print(f"[green]✓[/green] Removed orphan folder: {name}")
                    except OSError as e:
                        console.print(f"[yellow]Warning:[/yellow] Could not remove {name}: {e}")

        console.print("\n[green]Prune completed[/green]")

    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1) from None
