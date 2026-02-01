"""Path utilities and constants for Surek."""

from importlib import resources
from pathlib import Path


def get_data_dir() -> Path:
    """Get the Surek data directory, creating it if necessary.

    Returns:
        Path to surek-data/ in the current working directory.
    """
    data_dir = Path.cwd() / "surek-data"
    data_dir.mkdir(parents=True, exist_ok=True)
    return data_dir


def get_projects_dir() -> Path:
    """Get the projects directory where deployed stacks are stored.

    Returns:
        Path to surek-data/projects/
    """
    projects_dir = get_data_dir() / "projects"
    projects_dir.mkdir(parents=True, exist_ok=True)
    return projects_dir


def get_volumes_dir() -> Path:
    """Get the volumes directory where stack volumes are stored.

    Returns:
        Path to surek-data/volumes/
    """
    volumes_dir = get_data_dir() / "volumes"
    volumes_dir.mkdir(parents=True, exist_ok=True)
    return volumes_dir


def get_stacks_dir() -> Path:
    """Get the stacks directory containing user stack definitions.

    Returns:
        Path to stacks/ in the current working directory.
    """
    return Path.cwd() / "stacks"


def get_system_dir() -> Path:
    """Get the system directory containing system container definitions.

    Returns:
        Path to the bundled system/ resources directory.
    """
    return Path(str(resources.files("surek.resources") / "system"))


def get_stack_project_dir(stack_name: str) -> Path:
    """Get the project directory for a specific stack.

    Args:
        stack_name: Name of the stack.

    Returns:
        Path to surek-data/projects/<stack_name>/
    """
    return get_projects_dir() / stack_name


def get_stack_volumes_dir(stack_name: str) -> Path:
    """Get the volumes directory for a specific stack.

    Args:
        stack_name: Name of the stack.

    Returns:
        Path to surek-data/volumes/<stack_name>/
    """
    return get_volumes_dir() / stack_name
