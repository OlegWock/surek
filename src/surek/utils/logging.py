"""Logging utilities for Surek."""

from rich.console import Console

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
