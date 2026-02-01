"""Stack management commands."""

import json
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table

from surek.core.config import load_config, load_stack_config
from surek.core.deploy import deploy_stack, start_stack, stop_stack
from surek.core.docker import format_bytes, get_stack_status_detailed, run_docker_compose
from surek.core.stacks import get_available_stacks, get_stack_by_name
from surek.exceptions import StackConfigError, SurekError
from surek.utils.paths import get_stack_project_dir

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
        raise typer.Exit(1)


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
        raise typer.Exit(1)


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
        raise typer.Exit(1)


def status(
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
) -> None:
    """Show status of all stacks with health and resource usage."""
    try:
        load_config()  # Validate config exists

        results = []

        # System status
        system_status = get_stack_status_detailed("surek-system")
        results.append({
            "name": "System containers",
            "status": system_status.status_text,
            "health": system_status.health_summary,
            "cpu": f"{system_status.cpu_percent:.1f}%",
            "memory": format_bytes(system_status.memory_bytes),
            "path": "",
        })

        # User stacks
        try:
            stacks = get_available_stacks()
            for stack in stacks:
                if not stack.valid:
                    results.append({
                        "name": str(stack.path),
                        "status": "Invalid config",
                        "health": "-",
                        "cpu": "-",
                        "memory": "-",
                        "path": str(stack.path.parent.relative_to(Path.cwd())),
                    })
                    continue

                if stack.config:
                    stack_status = get_stack_status_detailed(stack.config.name)
                    results.append({
                        "name": stack.config.name,
                        "status": stack_status.status_text,
                        "health": stack_status.health_summary,
                        "cpu": f"{stack_status.cpu_percent:.1f}%",
                        "memory": format_bytes(stack_status.memory_bytes),
                        "path": str(stack.path.parent.relative_to(Path.cwd())),
                    })
        except SurekError:
            # No stacks directory, that's OK
            pass

        if json_output:
            console.print(json.dumps(results, indent=2))
        else:
            table = Table(title="Surek Status")
            table.add_column("Stack", style="cyan")
            table.add_column("Status")
            table.add_column("Health")
            table.add_column("CPU")
            table.add_column("Memory")
            table.add_column("Path", style="dim")

            for result in results:
                # Color status
                status_text = result["status"]
                if "✓" in status_text:
                    status_text = f"[green]{status_text}[/green]"
                elif "×" in status_text:
                    status_text = f"[red]{status_text}[/red]"
                elif "⚠" in status_text:
                    status_text = f"[yellow]{status_text}[/yellow]"

                table.add_row(
                    result["name"],
                    status_text,
                    result["health"],
                    result["cpu"],
                    result["memory"],
                    result["path"],
                )

            console.print(table)

    except SurekError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)


def info(
    stack_name: str = typer.Argument(..., help="Name of the stack"),
    logs: bool = typer.Option(False, "-l", "--logs", help="Include last 100 log lines"),
) -> None:
    """Show detailed information about a stack."""
    try:
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
                console.print(f"  • https://{endpoint.domain} → {endpoint.target}")

        # Logs
        if logs:
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
        raise typer.Exit(1)


def logs(
    stack_name: str = typer.Argument(..., help="Name of the stack"),
    service: Optional[str] = typer.Argument(None, help="Optional specific service name"),
    follow: bool = typer.Option(True, "-f", "--follow", help="Follow log output"),
    tail: int = typer.Option(100, "-t", "--tail", help="Output last N lines"),
    no_follow: bool = typer.Option(False, "--no-follow", help="Disable follow mode"),
) -> None:
    """View logs for a stack or specific service."""
    try:
        stack = get_stack_by_name(stack_name)
        if not stack.config:
            raise SurekError("Invalid stack config")

        project_dir = get_stack_project_dir(stack.config.name)
        compose_file = project_dir / "docker-compose.surek.yml"

        if not compose_file.exists():
            raise SurekError(f"Stack '{stack_name}' is not deployed")

        args = ["--tail", str(tail)]
        if follow and not no_follow:
            args.append("--follow")
        if service:
            args.append(service)

        # For follow mode, we can't capture output - let it stream
        if follow and not no_follow:
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
        raise typer.Exit(1)


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
