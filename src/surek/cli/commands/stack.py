"""Stack management commands."""

import contextlib
import json
import shutil
import subprocess
from pathlib import Path

import typer
from rich.console import Console
from rich.prompt import Confirm
from rich.table import Table

from surek.core.config import load_config, load_stack_config
from surek.core.deploy import deploy_stack, deploy_system_stack, start_stack, stop_stack
from surek.core.docker import (
    ensure_surek_network,
    format_bytes,
    get_stack_status_detailed,
    run_docker_compose,
)
from surek.core.stacks import RESERVED_STACK_NAMES, get_available_stacks, get_stack_by_name
from surek.exceptions import StackConfigError, SurekError
from surek.utils.paths import get_data_dir, get_stack_project_dir, get_system_dir

console = Console()


def _is_system_stack(stack_name: str) -> bool:
    """Check if the stack name refers to the system stack."""
    return stack_name.lower() in RESERVED_STACK_NAMES


def _ensure_system_running() -> None:
    """Verify that the system stack is running.

    Raises:
        typer.Exit: If system stack is not running.
    """
    try:
        status = get_stack_status_detailed("surek-system", include_stats=False)
        running_count = sum(1 for svc in status.services if svc.status == "running")
        if running_count == 0:
            console.print("[red]Error:[/red] System stack is not running.")
            console.print("\nThe system stack provides essential services (Caddy reverse proxy, etc.)")
            console.print("that are required for user stacks to work properly.")
            console.print("\n[yellow]Run this command first:[/yellow]")
            console.print("  surek start system")
            raise typer.Exit(1)
    except SurekError:
        # If we can't check status, system is likely not deployed
        console.print("[red]Error:[/red] System stack is not running.")
        console.print("\nThe system stack provides essential services (Caddy reverse proxy, etc.)")
        console.print("that are required for user stacks to work properly.")
        console.print("\n[yellow]Run this command first:[/yellow]")
        console.print("  surek start system")
        raise typer.Exit(1) from None


def _complete_stack_name(incomplete: str) -> list[str]:
    """Provide autocompletion for stack names."""
    try:
        stacks = get_available_stacks()
        names = [s.config.name for s in stacks if s.valid and s.config]
        # Add 'system' for system stack
        names.append("system")
        return [name for name in names if name.startswith(incomplete)]
    except Exception:
        return []


def deploy(
    stack_name: str = typer.Argument(
        ..., help="Name of the stack to deploy (use 'system' for system containers)",
        autocompletion=_complete_stack_name,
    ),
    pull: bool = typer.Option(False, "--pull", help="Force re-pull sources and Docker images"),
) -> None:
    """Deploy a stack (pull sources, transform compose, start containers)."""
    try:
        surek_config = load_config()

        if _is_system_stack(stack_name):
            # Deploy system stack
            console.print("Deploying system containers...")
            ensure_surek_network()

            # Stop existing system containers (silent)
            system_dir = get_system_dir()
            system_config = load_stack_config(system_dir / "surek.stack.yml")
            stop_stack(system_config, silent=True)

            deploy_system_stack(surek_config)
        else:
            _ensure_system_running()
            stack = get_stack_by_name(stack_name)
            console.print(f"Loaded stack config from {stack.path}")
            deploy_stack(stack, surek_config, pull=pull)
    except SurekError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1) from None


def start(
    stack_name: str = typer.Argument(
        ..., help="Name of the stack to start (use 'system' for system containers)",
        autocompletion=_complete_stack_name,
    ),
) -> None:
    """Start an already deployed stack without re-transformation."""
    try:
        if _is_system_stack(stack_name):
            # Start system stack (same as deploy for system)
            surek_config = load_config()
            console.print("Starting system containers...")
            ensure_surek_network()

            system_dir = get_system_dir()
            system_config = load_stack_config(system_dir / "surek.stack.yml")
            stop_stack(system_config, silent=True)

            deploy_system_stack(surek_config)
        else:
            _ensure_system_running()
            stack = get_stack_by_name(stack_name)
            console.print(f"Loaded stack config from {stack.path}")
            if stack.config:
                start_stack(stack.config)
    except SurekError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1) from None


def stop(
    stack_name: str = typer.Argument(
        ..., help="Name of the stack to stop (use 'system' for system containers)",
        autocompletion=_complete_stack_name,
    ),
) -> None:
    """Stop a running stack."""
    try:
        if _is_system_stack(stack_name):
            system_dir = get_system_dir()
            system_config = load_stack_config(system_dir / "surek.stack.yml")
            stop_stack(system_config, silent=False)
        else:
            stack = get_stack_by_name(stack_name)
            console.print(f"Loaded stack config from {stack.path}")
            if stack.config:
                stop_stack(stack.config, silent=False)
    except SurekError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1) from None


def status(
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
    stats: bool = typer.Option(False, "--stats", "-s", help="Include CPU/memory stats (slower)"),
) -> None:
    """Show status of all stacks with health and resource usage."""
    try:
        surek_config = load_config()

        results = []

        # System status
        system_status = get_stack_status_detailed("surek-system", include_stats=stats)
        system_result: dict[str, object] = {
            "name": "system",
            "status": system_status.status_text,
            "health": system_status.health_summary,
            "endpoints": [],
        }
        if stats:
            system_result["cpu"] = f"{system_status.cpu_percent:.1f}%"
            system_result["memory"] = format_bytes(system_status.memory_bytes)
        results.append(system_result)

        # User stacks
        try:
            stacks = get_available_stacks()
            for stack in stacks:
                if not stack.valid:
                    result: dict[str, object] = {
                        "name": str(stack.path.parent.name),
                        "status": "Invalid config",
                        "health": "-",
                        "endpoints": [],
                        "error": stack.error or "Unknown error",
                    }
                    if stats:
                        result["cpu"] = "-"
                        result["memory"] = "-"
                    results.append(result)
                    continue

                if stack.config:
                    stack_status = get_stack_status_detailed(stack.config.name, include_stats=stats)
                    # Expand domains with root
                    endpoints: list[str] = []
                    if stack.config.public:
                        for ep in stack.config.public:
                            domain = ep.domain.replace("<root>", surek_config.root_domain)
                            endpoints.append(f"https://{domain}")

                    stack_result: dict[str, object] = {
                        "name": stack.config.name,
                        "status": stack_status.status_text,
                        "health": stack_status.health_summary,
                        "endpoints": endpoints,
                    }
                    if stats:
                        stack_result["cpu"] = f"{stack_status.cpu_percent:.1f}%"
                        stack_result["memory"] = format_bytes(stack_status.memory_bytes)
                    results.append(stack_result)
        except SurekError:
            pass  # No stacks directory

        if json_output:
            console.print(json.dumps(results, indent=2))
        else:
            table = Table(title="Surek stacks status")
            table.add_column("Stack", style="cyan")
            table.add_column("Status")
            table.add_column("Health")
            if stats:
                table.add_column("CPU")
                table.add_column("Memory")
            table.add_column("Endpoints", style="dim")

            for result in results:
                status_text = str(result["status"])
                if "✓" in status_text:
                    status_text = f"[green]{status_text}[/green]"
                elif "×" in status_text:
                    status_text = f"[red]{status_text}[/red]"
                elif "⚠" in status_text:
                    status_text = f"[yellow]{status_text}[/yellow]"
                elif "Invalid" in status_text:
                    status_text = f"[red]{status_text}[/red]"

                endpoints_obj = result.get("endpoints", [])
                endpoints_list: list[str] = endpoints_obj if isinstance(endpoints_obj, list) else []
                endpoints_str = ", ".join(endpoints_list) if endpoints_list else "-"

                if stats:
                    table.add_row(
                        str(result["name"]),
                        status_text,
                        str(result["health"]),
                        str(result.get("cpu", "-")),
                        str(result.get("memory", "-")),
                        endpoints_str,
                    )
                else:
                    table.add_row(
                        str(result["name"]),
                        status_text,
                        str(result["health"]),
                        endpoints_str,
                    )

            console.print(table)

            # Show errors for invalid stacks
            for result in results:
                if "error" in result:
                    console.print(
                        f"\n[yellow]Warning:[/yellow] Stack '{result['name']}' has invalid config: {result['error']}"
                    )
                    console.print(f"  Run: surek validate stacks/{result['name']}/surek.stack.yml")

    except SurekError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1) from None


def info(
    stack_name: str = typer.Argument(
        ..., help="Name of the stack", autocompletion=_complete_stack_name
    ),
    show_logs: bool = typer.Option(False, "-l", "--logs", help="Include last 40 log lines"),
) -> None:
    """Show detailed information about a stack."""
    try:
        surek_config = load_config()

        if _is_system_stack(stack_name):
            # System stack info
            stack_status = get_stack_status_detailed("surek-system", include_stats=True)

            console.print("\n[bold]Stack:[/bold] system")
            console.print(f"[bold]Status:[/bold] {stack_status.status_text}")
            console.print("[bold]Source:[/bold] built-in")

            # Services table
            if stack_status.services:
                console.print("\n[bold]Services:[/bold]")
                services_table = Table()
                services_table.add_column("Service")
                services_table.add_column("Status")
                services_table.add_column("Health")
                services_table.add_column("CPU")
                services_table.add_column("Memory")

                for svc in stack_status.services:
                    status_text = svc.status
                    if svc.status == "running":
                        status_text = f"[green]{status_text}[/green]"
                    elif svc.status == "exited":
                        status_text = f"[red]{status_text}[/red]"

                    services_table.add_row(
                        svc.name,
                        status_text,
                        svc.health or "-",
                        f"{svc.cpu_percent:.1f}%",
                        format_bytes(svc.memory_bytes),
                    )

                console.print(services_table)
        else:
            stack = get_stack_by_name(stack_name)
            if not stack.config:
                raise SurekError("Invalid stack config")

            config = stack.config
            stack_status = get_stack_status_detailed(config.name, include_stats=True)

            console.print(f"\n[bold]Stack:[/bold] {config.name}")
            console.print(f"[bold]Status:[/bold] {stack_status.status_text}")
            console.print(f"[bold]Source:[/bold] {config.source.pretty}")
            console.print(f"[bold]Compose:[/bold] {config.compose_file_path}")

            # Services table
            if stack_status.services:
                console.print("\n[bold]Services:[/bold]")
                services_table = Table()
                services_table.add_column("Service")
                services_table.add_column("Status")
                services_table.add_column("Health")
                services_table.add_column("CPU")
                services_table.add_column("Memory")

                for svc in stack_status.services:
                    status_text = svc.status
                    if svc.status == "running":
                        status_text = f"[green]{status_text}[/green]"
                    elif svc.status == "exited":
                        status_text = f"[red]{status_text}[/red]"

                    services_table.add_row(
                        svc.name,
                        status_text,
                        svc.health or "-",
                        f"{svc.cpu_percent:.1f}%",
                        format_bytes(svc.memory_bytes),
                    )

                console.print(services_table)

            # Public endpoints
            if config.public:
                console.print("\n[bold]Public Endpoints:[/bold]")
                for endpoint in config.public:
                    domain = endpoint.domain.replace("<root>", surek_config.root_domain)
                    console.print(f"  • https://{domain} → {endpoint.target}")

        # Logs
        if show_logs:
            console.print("\n[bold]Recent Logs:[/bold]")
            if _is_system_stack(stack_name):
                project_dir = get_stack_project_dir("surek-system")
            else:
                project_dir = get_stack_project_dir(stack.config.name)  # type: ignore[union-attr]
            compose_file = project_dir / "docker-compose.surek.yml"
            if compose_file.exists():
                try:
                    output = run_docker_compose(
                        compose_file=compose_file,
                        project_dir=project_dir,
                        command="logs",
                        args=["--tail", "40"],
                        capture_output=True,
                        silent=True,
                    )
                    console.print(output)
                except SurekError as e:
                    console.print(f"[yellow]Could not fetch logs: {e}[/yellow]")

    except SurekError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1) from None


def logs(
    stack_name: str = typer.Argument(
        ..., help="Name of the stack (use 'system' for system containers)",
        autocompletion=_complete_stack_name,
    ),
    service: str | None = typer.Argument(None, help="Optional specific service name"),
    follow: bool = typer.Option(False, "-f", "--follow", help="Follow log output"),
    tail: int = typer.Option(100, "-t", "--tail", help="Output last N lines"),
) -> None:
    """View logs for a stack or specific service."""
    try:
        # Handle system stack specially
        if _is_system_stack(stack_name):
            project_dir = get_stack_project_dir("surek-system")
            compose_file = project_dir / "docker-compose.surek.yml"
        else:
            stack = get_stack_by_name(stack_name)
            if not stack.config:
                raise SurekError("Invalid stack config")
            project_dir = get_stack_project_dir(stack.config.name)
            compose_file = project_dir / "docker-compose.surek.yml"

        if not compose_file.exists():
            raise SurekError(f"Stack '{stack_name}' is not deployed")

        args = ["--tail", str(tail)]
        if follow:
            args.append("--follow")
        if service:
            args.append(service)

        # For follow mode, we can't capture output - let it stream
        if follow:
            run_docker_compose(
                compose_file=compose_file,
                project_dir=project_dir,
                command="logs",
                args=args,
            )
        else:
            output = run_docker_compose(
                compose_file=compose_file,
                project_dir=project_dir,
                command="logs",
                args=args,
                capture_output=True,
                silent=True,
            )
            console.print(output)

    except SurekError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1) from None


def validate(
    stack_path: Path = typer.Argument(..., help="Path to surek.stack.yml file"),
) -> None:
    """Validate a stack configuration file."""
    try:
        config = load_stack_config(stack_path)
        console.print("[green]✓[/green] Stack config is valid")
        console.print(f"  Name: {config.name}")
        console.print(f"  Source: {config.source.pretty}")
        if config.public:
            console.print(f"  Endpoints: {len(config.public)}")
            for ep in config.public:
                console.print(f"    • {ep.domain} → {ep.target}")
    except StackConfigError as e:
        console.print(f"[red]✗[/red] Invalid stack config: {stack_path}")
        console.print(f"  {e}")
        raise typer.Exit(1) from None


def reset(
    stack_name: str = typer.Argument(
        ..., help="Name of the stack to reset", autocompletion=_complete_stack_name
    ),
    force: bool = typer.Option(False, "--force", "-f", help="Skip confirmation prompt"),
) -> None:
    """Reset a stack by stopping it, removing volumes, and cleaning up files."""
    try:
        if _is_system_stack(stack_name):
            raise SurekError("Cannot reset the system stack. Use 'surek stop system' instead.")

        stack = get_stack_by_name(stack_name)
        if not stack.config:
            raise SurekError("Invalid stack config")

        config = stack.config
        project_dir = get_stack_project_dir(config.name)
        volumes_dir = get_data_dir() / "volumes" / config.name

        # Show what will be removed
        console.print(f"\n[bold]Reset stack:[/bold] {config.name}")
        console.print("\nThis will:")
        console.print("  • Stop all containers")
        console.print(f"  • Remove project files: {project_dir}")
        if volumes_dir.exists():
            console.print(f"  • [red]Delete all volume data:[/red] {volumes_dir}")

        if not force and not Confirm.ask("\n[yellow]Are you sure? This cannot be undone.[/yellow]", default=False):
            console.print("[dim]Aborted[/dim]")
            raise typer.Exit(0)

        # Stop the stack
        console.print("\nStopping containers...")
        with contextlib.suppress(SurekError):
            stop_stack(config, silent=True)

        # Remove project directory
        if project_dir.exists():
            console.print(f"Removing {project_dir}...")
            shutil.rmtree(project_dir)

        # Remove volumes
        if volumes_dir.exists():
            console.print(f"Removing {volumes_dir}...")
            shutil.rmtree(volumes_dir)

        console.print(f"\n[green]✓[/green] Stack '{config.name}' has been reset")
        console.print(f"  Run 'surek deploy {config.name}' to redeploy")

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

    # Get all known stack names (including system and invalid stacks)
    known_stacks = {"surek-system"}
    try:
        stacks = get_available_stacks()
        for stack in stacks:
            if stack.valid and stack.config:
                known_stacks.add(stack.config.name)
            else:
                # For invalid stacks, use the folder name as the stack name
                # to avoid accidentally deleting their volumes
                known_stacks.add(stack.path.parent.name)
    except SurekError:
        pass

    # Find folders that don't match any known stack
    orphans: list[tuple[str, str]] = []
    for folder in volumes_base.iterdir():
        if folder.is_dir() and folder.name not in known_stacks:
            orphans.append((folder.name, str(folder)))

    return orphans


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
