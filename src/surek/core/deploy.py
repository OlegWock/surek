"""Stack deployment and lifecycle management."""

import shutil
from pathlib import Path

from surek.core.compose import (
    read_compose_file,
    transform_compose_file,
    transform_system_compose,
    write_compose_file,
)
from surek.core.docker import run_docker_compose
from surek.core.github import (
    get_cached_commit,
    get_latest_commit,
    pull_github_repo,
    save_cached_commit,
)
from surek.core.stacks import StackInfo, get_stack_source_dir
from surek.exceptions import SurekError
from surek.models.config import SurekConfig
from surek.models.stack import GitHubSource, StackConfig
from surek.utils.logging import console, print_dim, print_success
from surek.utils.paths import get_stack_project_dir, get_system_dir


def deploy_stack(
    stack: StackInfo,
    surek_config: SurekConfig,
    pull: bool = False,
) -> None:
    """Deploy a stack.

    This performs the full deployment pipeline:
    1. Resolve source (download from GitHub if needed)
    2. Copy files to project directory
    3. Transform compose file
    4. Start containers

    Args:
        stack: The stack to deploy.
        surek_config: The main Surek configuration.
        pull: If True, force re-pull sources and Docker images.

    Raises:
        SurekError: If deployment fails.
    """
    if not stack.valid or not stack.config:
        raise SurekError(f"Cannot deploy invalid stack: {stack.error}")

    config = stack.config
    source_dir = get_stack_source_dir(stack)
    project_dir = get_stack_project_dir(config.name)

    console.print(f"Deploying stack '{config.name}'")

    if isinstance(config.source, GitHubSource):
        _handle_github_source(config, project_dir, surek_config, pull)
    else:
        if project_dir.exists():
            shutil.rmtree(project_dir)
        project_dir.mkdir(parents=True)

    _copy_folder_recursive(source_dir, project_dir)

    compose_file_path = project_dir / config.compose_file_path
    if not compose_file_path.exists():
        raise SurekError(f"Couldn't find compose file at {compose_file_path}")

    compose_spec = read_compose_file(compose_file_path)
    transformed = transform_compose_file(compose_spec, config, surek_config)
    patched_path = project_dir / "docker-compose.surek.yml"
    write_compose_file(patched_path, transformed)
    print_dim(f"Saved patched compose file at {patched_path}")

    # Start containers
    start_stack(config, pull=pull)


def deploy_system_stack(surek_config: SurekConfig) -> None:
    """Deploy the system stack.

    Args:
        surek_config: The main Surek configuration.
    """
    from surek.core.config import load_stack_config

    system_dir = get_system_dir()
    system_config_path = system_dir / "surek.stack.yml"
    system_config = load_stack_config(system_config_path)

    filtered_public = []
    for endpoint in system_config.public:
        service_name = endpoint.service_name
        if service_name == "portainer" and not surek_config.system_services.portainer:
            continue
        if service_name == "netdata" and not surek_config.system_services.netdata:
            continue
        filtered_public.append(endpoint)

    # Create a modified config with filtered public endpoints
    system_config = StackConfig(
        name=system_config.name,
        source=system_config.source,
        compose_file_path=system_config.compose_file_path,
        public=filtered_public,
        env=system_config.env,
        backup=system_config.backup,
    )

    project_dir = get_stack_project_dir(system_config.name)

    console.print("Deploying system containers")

    if project_dir.exists():
        shutil.rmtree(project_dir)
    project_dir.mkdir(parents=True)

    _copy_folder_recursive(system_dir, project_dir)

    compose_file_path = project_dir / system_config.compose_file_path
    compose_spec = read_compose_file(compose_file_path)
    compose_spec = transform_system_compose(compose_spec, surek_config)
    transformed = transform_compose_file(compose_spec, system_config, surek_config)
    patched_path = project_dir / "docker-compose.surek.yml"
    write_compose_file(patched_path, transformed)
    print_dim(f"Saved patched compose file at {patched_path}")

    start_stack(system_config)


def start_stack(config: StackConfig, pull: bool = False) -> None:
    """Start a deployed stack.

    Args:
        config: The stack configuration.
        pull: If True, force re-pull Docker images before starting.

    Raises:
        SurekError: If start fails.
    """
    project_dir = get_stack_project_dir(config.name)
    patched_path = project_dir / "docker-compose.surek.yml"

    if not patched_path.exists():
        raise SurekError(f"Couldn't find compose file for stack '{config.name}'. Deploy it first.")

    console.print("Starting containers...")
    args = ["-d", "--build"]
    if pull:
        args.extend(["--pull", "always"])
    run_docker_compose(
        compose_file=patched_path,
        project_dir=project_dir,
        command="up",
        args=args,
    )
    print_success("Containers started")


def stop_stack(config: StackConfig, silent: bool = False) -> None:
    """Stop a running stack.

    Args:
        config: The stack configuration.
        silent: If True, don't raise error if compose file doesn't exist.

    Raises:
        SurekError: If stop fails (unless silent is True).
    """
    project_dir = get_stack_project_dir(config.name)
    patched_path = project_dir / "docker-compose.surek.yml"

    if not patched_path.exists():
        if silent:
            return
        raise SurekError(f"Couldn't find compose file for stack '{config.name}'")

    if not silent:
        console.print("Stopping containers...")

    run_docker_compose(
        compose_file=patched_path,
        project_dir=project_dir,
        command="stop",
        silent=silent,
    )

    if not silent:
        print_success("Containers stopped")


def _handle_github_source(
    config: StackConfig,
    project_dir: Path,
    surek_config: SurekConfig,
    pull: bool,
) -> bool:
    """Handle GitHub source for a stack.

    Downloads from GitHub if not cached or pull is True.

    Args:
        config: The stack configuration.
        project_dir: The project directory to extract into.
        surek_config: The main Surek configuration.
        pull: If True, force re-download.

    Returns:
        True if cached version was used (project_dir preserved), False if fresh download.
    """
    if not isinstance(config.source, GitHubSource):
        return False

    source = config.source

    if not pull:
        # Check if we can use cached version
        cached_commit = get_cached_commit(config.name)
        if cached_commit and project_dir.exists():
            try:
                latest_commit = get_latest_commit(source, surek_config)
                if cached_commit == latest_commit:
                    print_dim("No changes detected, using cached version")
                    return True
            except Exception:
                # If we can't check, just download fresh
                pass

    # Clean and download from GitHub
    if project_dir.exists():
        shutil.rmtree(project_dir)
    project_dir.mkdir(parents=True)

    commit = pull_github_repo(source, project_dir, surek_config)
    save_cached_commit(config.name, commit)
    return False


def _copy_folder_recursive(source: Path, destination: Path) -> None:
    """Copy folder contents recursively with overwrite.

    Args:
        source: Source directory.
        destination: Destination directory.
    """
    destination.mkdir(parents=True, exist_ok=True)

    for item in source.iterdir():
        src_path = item
        dst_path = destination / item.name

        if item.is_dir():
            _copy_folder_recursive(src_path, dst_path)
        else:
            shutil.copy2(src_path, dst_path)
