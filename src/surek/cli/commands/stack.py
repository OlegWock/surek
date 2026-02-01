"""Stack management commands."""

import json
import shutil
from pathlib import Path

import typer
from rich.console import Console
from rich.prompt import Confirm
from rich.table import Table

from surek.core.config import load_config, load_stack_config
from surek.core.deploy import deploy_stack, start_stack, stop_stack
from surek.core.docker import format_bytes, get_stack_status_detailed, run_docker_compose
from surek.core.stacks import get_available_stacks, get_stack_by_name
from surek.exceptions import StackConfigError, SurekError
from surek.utils.paths import get_data_dir, get_stack_project_dir

console = Console()


def deploy(
    stack_name: str = typer.Argument(..., help="Name of the stack to deploy"),
    force: bool = typer.Option(False, "--force", help="Force re-download even if cached"),
) -> None:
    """Deploy a stack (pull sources, transform compose, start containers)."""
    try:
        surek_config = load_config()
        stack = get_stack_by_name(stack_name)
        console.print(f"Loaded stack config from {stack.path}")
        deploy_stack(stack, surek_config, force=force)
    except SurekError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1) from None


def start(
    stack_name: str = typer.Argument(..., help="Name of the stack to start"),
) -> None:
    """Start an already deployed stack without re-transformation."""
    try:
        stack = get_stack_by_name(stack_name)
        console.print(f"Loaded stack config from {stack.path}")
        if stack.config:
            start_stack(stack.config)
    except SurekError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1) from None


def stop(
    stack_name: str = typer.Argument(..., help="Name of the stack to stop"),
) -> None:
    """Stop a running stack."""
    try:
        stack = get_stack_by_name(stack_name)
        console.print(f"Loaded stack config from {stack.path}")
        if stack.config:
            stop_stack(stack.config, silent=False)
    except SurekError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1) from None


def status(
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
) -> None:
    """Show status of all stacks with health and resource usage."""
    try:
        surek_config = load_config()

        results = []

        # System status
        system_status = get_stack_status_detailed("surek-system")
        system_result: dict[str, object] = {
            "name": "System containers",
            "status": system_status.status_text,
            "health": system_status.health_summary,
            "cpu": f"{system_status.cpu_percent:.1f}%",
            "memory": format_bytes(system_status.memory_bytes),
            "endpoints": [],
        }
        results.append(system_result)

        # User stacks
        try:
            stacks = get_available_stacks()
            for stack in stacks:
                if not stack.valid:
                    results.append({
                        "name": str(stack.path.parent.name),
                        "status": "Invalid config",
                        "health": "-",
                        "cpu": "-",
                        "memory": "-",
                        "endpoints": [],
                        "error": stack.error or "Unknown error",
                    })
                    continue

                if stack.config:
                    stack_status = get_stack_status_detailed(stack.config.name)
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
                        "cpu": f"{stack_status.cpu_percent:.1f}%",
                        "memory": format_bytes(stack_status.memory_bytes),
                        "endpoints": endpoints,
                    }
                    results.append(stack_result)
        except SurekError:
            pass  # No stacks directory

        if json_output:
            console.print(json.dumps(results, indent=2))
        else:
            table = Table(title="Surek Status")
            table.add_column("Stack", style="cyan")
            table.add_column("Status")
            table.add_column("Health")
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
                table.add_row(
                    str(result["name"]),
                    status_text,
                    str(result["health"]),
                    str(result["cpu"]),
                    str(result["memory"]),
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
    stack_name: str = typer.Argument(..., help="Name of the stack"),
    show_logs: bool = typer.Option(False, "-l", "--logs", help="Include last 100 log lines"),
) -> None:
    """Show detailed information about a stack."""
    try:
        surek_config = load_config()
        stack = get_stack_by_name(stack_name)
        if not stack.config:
            raise SurekError("Invalid stack config")

        config = stack.config
        stack_status = get_stack_status_detailed(config.name)

        console.print(f"\n[bold]Stack:[/bold] {config.name}")
        console.print(f"[bold]Status:[/bold] {stack_status.status_text}")
        console.print(f"[bold]Source:[/bold] {config.source.type}")
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
            project_dir = get_stack_project_dir(config.name)
            compose_file = project_dir / "docker-compose.surek.yml"
            if compose_file.exists():
                try:
                    output = run_docker_compose(
                        compose_file=compose_file,
                        project_dir=project_dir,
                        command="logs",
                        args=["--tail", "100"],
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
    stack_name: str = typer.Argument(..., help="Name of the stack (use 'system' for system containers)"),
    service: str | None = typer.Argument(None, help="Optional specific service name"),
    follow: bool = typer.Option(False, "-f", "--follow", help="Follow log output"),
    tail: int = typer.Option(100, "-t", "--tail", help="Output last N lines"),
) -> None:
    """View logs for a stack or specific service."""
    try:
        # Handle system stack specially
        if stack_name in ("system", "surek-system"):
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
        console.print(f"  Source: {config.source.type}")
        if config.public:
            console.print(f"  Endpoints: {len(config.public)}")
            for ep in config.public:
                console.print(f"    • {ep.domain} → {ep.target}")
    except StackConfigError as e:
        console.print(f"[red]✗[/red] Invalid stack config: {stack_path}")
        console.print(f"  {e}")
        raise typer.Exit(1) from None


def reset(
    stack_name: str = typer.Argument(..., help="Name of the stack to reset"),
    force: bool = typer.Option(False, "--force", "-f", help="Skip confirmation prompt"),
) -> None:
    """Reset a stack by stopping it, removing volumes, and cleaning up files."""
    try:
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
        import contextlib

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
