"""Stack discovery and management."""

from dataclasses import dataclass
from pathlib import Path

from surek.core.config import load_stack_config
from surek.exceptions import SurekError
from surek.models.stack import StackConfig
from surek.utils.paths import get_stacks_dir


@dataclass
class StackInfo:
    """Information about a discovered stack."""

    config: StackConfig | None
    path: Path
    valid: bool
    error: str = ""

    @property
    def name(self) -> str:
        """Get the stack name, or path if invalid."""
        if self.config:
            return self.config.name
        return str(self.path)


def get_available_stacks() -> list[StackInfo]:
    """Find all stacks in the stacks/ directory.

    Returns:
        List of StackInfo objects for all discovered stacks.

    Raises:
        SurekError: If the stacks directory doesn't exist.
    """
    stacks_dir = get_stacks_dir()

    if not stacks_dir.exists():
        raise SurekError("Folder 'stacks' not found in current working directory")

    results: list[StackInfo] = []

    for config_path in stacks_dir.glob("**/surek.stack.yml"):
        try:
            config = load_stack_config(config_path)
            results.append(
                StackInfo(
                    config=config,
                    path=config_path,
                    valid=True,
                )
            )
        except Exception as e:
            results.append(
                StackInfo(
                    config=None,
                    path=config_path,
                    valid=False,
                    error=str(e),
                )
            )

    return sorted(results, key=lambda s: str(s.path))


def get_stack_by_name(name: str) -> StackInfo:
    """Find a stack by name.

    Args:
        name: The stack name to find.

    Returns:
        StackInfo for the matching stack.

    Raises:
        SurekError: If the stack name is invalid or not found.
    """
    if not name:
        raise SurekError("Invalid stack name")

    for stack in get_available_stacks():
        if stack.valid and stack.config and stack.config.name == name:
            return stack

    raise SurekError(f"Stack with name '{name}' not found")


def get_stack_source_dir(stack: StackInfo) -> Path:
    """Get the source directory for a stack.

    Args:
        stack: The stack info.

    Returns:
        Path to the directory containing the stack's source files.
    """
    return stack.path.parent
