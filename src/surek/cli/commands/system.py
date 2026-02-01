"""System container management commands."""

import typer
from rich.console import Console

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
        raise typer.Exit(1)


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
        raise typer.Exit(1)
