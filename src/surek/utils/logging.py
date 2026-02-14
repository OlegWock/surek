"""Logging utilities for Surek."""

import subprocess

from rich.console import Console

from surek.exceptions import SurekError

# Shared console instance for consistent output
console = Console()


def print_error(message: str) -> None:
    """Print an error message."""
    console.print(f"[red]Error:[/red] {message}")


def print_warning(message: str) -> None:
    """Print a warning message."""
    console.print(f"[yellow]Warning:[/yellow] {message}")


def print_success(message: str) -> None:
    """Print a success message."""
    console.print(f"[green]{message}[/green]")


def print_info(message: str) -> None:
    """Print an info message."""
    console.print(message)


def print_dim(message: str) -> None:
    """Print a dimmed/muted message."""
    console.print(f"[dim]{message}[/dim]")


def run_command(
    cmd: list[str],
    capture_output: bool = False,
    silent: bool = False,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    """Execute a shell command with optional logging.

    Args:
        cmd: Command and arguments as a list.
        capture_output: If True, capture stdout and stderr.
        silent: If True, don't print the command.
        check: If True, raise SurekError on non-zero exit code.

    Returns:
        CompletedProcess instance with command results.

    Raises:
        SurekError: If check=True and command fails.
    """
    if not silent:
        print_dim(f"$ {' '.join(cmd)}")

    result = subprocess.run(cmd, capture_output=capture_output, text=True)

    if check and result.returncode != 0:
        error_msg = (
            result.stderr if result.stderr else f"Command exited with code {result.returncode}"
        )
        raise SurekError(f"Command failed: {error_msg}")

    return result


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
