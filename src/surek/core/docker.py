"""Docker client wrapper and utilities."""

import subprocess
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import docker
from docker.errors import DockerException

from surek.exceptions import DockerError
from surek.utils.logging import console, print_dim

# Docker network and labels
SUREK_NETWORK = "surek"
DEFAULT_LABELS = {"surek.managed": "true"}

# Singleton Docker client
_docker_client: docker.DockerClient | None = None


def get_docker_client() -> docker.DockerClient:
    """Get or create the Docker client singleton.

    Returns:
        Docker client instance.

    Raises:
        DockerError: If connection to Docker fails.
    """
    global _docker_client

    if _docker_client is None:
        try:
            _docker_client = docker.from_env()
            _docker_client.ping()
        except DockerException as e:
            raise DockerError(f"Failed to connect to Docker: {e}") from e

    return _docker_client


def ensure_surek_network() -> None:
    """Ensure the Surek Docker network exists.

    Creates the network if it doesn't exist.
    """
    client = get_docker_client()

    # Check if network already exists
    existing = client.networks.list(names=[SUREK_NETWORK])

    if not existing:
        console.print(f"Creating Docker network '{SUREK_NETWORK}'")
        client.networks.create(
            name=SUREK_NETWORK,
            driver="bridge",
            labels=DEFAULT_LABELS,
        )


@dataclass
class ServiceHealth:
    """Health information for a Docker container/service."""

    name: str
    status: str  # "running", "exited", "paused", etc.
    health: str | None  # "healthy", "unhealthy", "starting", None
    cpu_percent: float
    memory_bytes: int


@dataclass
class StackStatusDetailed:
    """Detailed status information for a stack."""

    status_text: str
    services: list[ServiceHealth]
    health_details: list[str]
    health_summary: str
    cpu_percent: float
    memory_bytes: int


def _get_container_stats(container: Any) -> tuple[str, float, int]:
    """Get stats for a single container.

    Args:
        container: Docker container object.

    Returns:
        Tuple of (container_id, cpu_percent, memory_bytes).
    """
    try:
        if container.status == "running":
            stats: dict[str, Any] = container.stats(stream=False)  # type: ignore[assignment]
            cpu_percent = _calculate_cpu_percent(stats)
            memory_stats: dict[str, Any] = stats.get("memory_stats", {})
            memory_bytes = int(memory_stats.get("usage", 0) or 0) if isinstance(memory_stats, dict) else 0
            return (container.id, cpu_percent, memory_bytes)
    except Exception:
        pass
    return (container.id, 0.0, 0)


def get_stack_status_detailed(stack_name: str, include_stats: bool = False) -> StackStatusDetailed:
    """Get detailed status for a stack including health and optionally resources.

    Args:
        stack_name: Name of the stack (Docker Compose project name).
        include_stats: If True, fetch CPU/memory stats (slower, ~1-2s per container).
                      Stats are fetched in parallel when enabled.

    Returns:
        Detailed status information.
    """
    from surek.utils.paths import get_stack_project_dir

    project_dir = get_stack_project_dir(stack_name)
    compose_file = project_dir / "docker-compose.surek.yml"

    if not project_dir.exists() or not compose_file.exists():
        return StackStatusDetailed(
            status_text="× Not deployed",
            services=[],
            health_details=[],
            health_summary="-",
            cpu_percent=0,
            memory_bytes=0,
        )

    try:
        client = get_docker_client()
    except DockerError:
        return StackStatusDetailed(
            status_text="? Docker unavailable",
            services=[],
            health_details=[],
            health_summary="-",
            cpu_percent=0,
            memory_bytes=0,
        )

    # Get containers for this project
    containers = client.containers.list(
        all=True, filters={"label": f"com.docker.compose.project={stack_name}"}
    )

    if not containers:
        return StackStatusDetailed(
            status_text="× Down",
            services=[],
            health_details=[],
            health_summary="-",
            cpu_percent=0,
            memory_bytes=0,
        )

    # Fetch stats in parallel if requested
    stats_by_id: dict[str, tuple[float, int]] = {}
    if include_stats:
        running_containers = [c for c in containers if c.status == "running"]
        if running_containers:
            with ThreadPoolExecutor(max_workers=min(len(running_containers), 10)) as executor:
                futures = {executor.submit(_get_container_stats, c): c for c in running_containers}
                for future in as_completed(futures):
                    container_id, cpu, mem = future.result()
                    stats_by_id[container_id] = (cpu, mem)

    services: list[ServiceHealth] = []
    total_cpu = 0.0
    total_memory = 0
    health_details: list[str] = []

    for container in containers:
        # Get service name from labels
        service_name = container.labels.get("com.docker.compose.service", container.name)

        # Get health status
        health: str | None = None
        state = container.attrs.get("State", {})
        if "Health" in state:
            health = state["Health"].get("Status")

        # Get resource usage from pre-fetched stats
        container_id = container.id or ""
        cpu_percent, memory_bytes = stats_by_id.get(container_id, (0.0, 0))

        services.append(
            ServiceHealth(
                name=service_name,
                status=container.status,
                health=health,
                cpu_percent=cpu_percent,
                memory_bytes=memory_bytes,
            )
        )

        total_cpu += cpu_percent
        total_memory += memory_bytes

        # Build health detail string
        if health:
            health_details.append(f"{service_name}: {health}")

    # Calculate status text
    running = sum(1 for s in services if s.status == "running")
    total = len(services)

    if running == 0:
        status_text = "× Down"
    elif running == total:
        status_text = f"✓ Running ({running}/{total})"
    else:
        status_text = f"⚠ Partial ({running}/{total})"

    # Health summary
    unhealthy = sum(1 for s in services if s.health == "unhealthy")
    starting = sum(1 for s in services if s.health == "starting")
    if unhealthy > 0:
        health_summary = f"⚠ {unhealthy} unhealthy"
    elif starting > 0:
        health_summary = "starting..."
    elif all(s.health in ("healthy", None) for s in services):
        health_summary = "✓ healthy"
    else:
        health_summary = "-"

    return StackStatusDetailed(
        status_text=status_text,
        services=services,
        health_details=health_details,
        health_summary=health_summary,
        cpu_percent=total_cpu,
        memory_bytes=total_memory,
    )


def _calculate_cpu_percent(stats: dict[str, Any]) -> float:
    """Calculate CPU percentage from Docker stats.

    Args:
        stats: Docker container stats dict.

    Returns:
        CPU usage percentage.
    """
    try:
        cpu_stats = stats.get("cpu_stats", {})
        precpu_stats = stats.get("precpu_stats", {})

        cpu_usage = cpu_stats.get("cpu_usage", {})
        precpu_usage = precpu_stats.get("cpu_usage", {})

        cpu_delta = cpu_usage.get("total_usage", 0) - precpu_usage.get("total_usage", 0)
        system_delta = cpu_stats.get("system_cpu_usage", 0) - precpu_stats.get(
            "system_cpu_usage", 0
        )

        if system_delta > 0 and cpu_delta > 0:
            cpu_count = cpu_stats.get("online_cpus", 1)
            return (cpu_delta / system_delta) * cpu_count * 100.0
    except (KeyError, TypeError, ZeroDivisionError):
        pass

    return 0.0


def run_docker_compose(
    compose_file: Path,
    project_dir: Path,
    command: str,
    args: list[str] | None = None,
    capture_output: bool = False,
    silent: bool = False,
) -> str:
    """Execute a docker compose command.

    Args:
        compose_file: Path to the compose file.
        project_dir: Path to the project directory.
        command: The compose command (up, stop, ps, logs, etc.).
        args: Additional arguments for the command.
        capture_output: If True, capture and return stdout.
        silent: If True, don't print the command.

    Returns:
        stdout content if capture_output is True, empty string otherwise.

    Raises:
        DockerError: If the command fails.
    """
    cmd = [
        "docker",
        "compose",
        "--file",
        str(compose_file),
        "--project-directory",
        str(project_dir),
        command,
    ]

    if args:
        cmd.extend(args)

    if not silent:
        print_dim(f"$ {' '.join(cmd)}")

    try:
        if capture_output:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                check=True,
            )
            return result.stdout
        else:
            subprocess.run(cmd, check=True)
            return ""
    except subprocess.CalledProcessError as e:
        error_msg = e.stderr if e.stderr else f"Command exited with code {e.returncode}"
        raise DockerError(f"Docker Compose command failed: {error_msg}") from e


def format_bytes(num_bytes: int) -> str:
    """Format bytes as human-readable string.

    Args:
        num_bytes: Number of bytes.

    Returns:
        Human-readable string (e.g., "1.5 GB").
    """
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if abs(num_bytes) < 1024.0:
            return f"{num_bytes:.1f} {unit}"
        num_bytes = int(num_bytes / 1024.0)
    return f"{num_bytes:.1f} PB"
