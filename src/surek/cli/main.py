"""Main CLI entry point for Surek."""


import typer
from rich.console import Console

from surek import __version__
from surek.cli.commands import backup, init, stack
from surek.exceptions import SurekError

console = Console()

# Main app with shell completion enabled
app = typer.Typer(
    name="surek",
    help="Docker Compose orchestration tool for self-hosted services.",
    no_args_is_help=False,
    add_completion=True,
)

# Register command groups
app.add_typer(backup.app, name="backup", help="Backup management commands")

# Register individual commands from modules
app.command(name="init")(init.init_command)
app.command(name="new")(init.new_command)
app.command(name="schema")(init.schema_command)
app.command(name="deploy")(stack.deploy)
app.command(name="start")(stack.start)
app.command(name="stop")(stack.stop)
app.command(name="status")(stack.status)
app.command(name="info")(stack.info)
app.command(name="logs")(stack.logs)
app.command(name="validate")(stack.validate)
app.command(name="reset")(stack.reset)
app.command(name="prune")(stack.prune)


def version_callback(value: bool) -> None:
    """Print version and exit."""
    if value:
        console.print(f"surek {__version__}")
        raise typer.Exit()


def help_llm_callback(value: bool) -> None:
    """Print LLM documentation and exit."""
    if value:
        try:
            from importlib import resources

            docs_path = resources.files("surek.resources") / "llm_docs.md"
            console.print(docs_path.read_text())
        except FileNotFoundError:
            console.print("[yellow]LLM documentation not yet available.[/yellow]")
        raise typer.Exit()


def help_readme_callback(value: bool) -> None:
    """Print README and exit."""
    if value:
        try:
            from importlib import resources

            readme_path = resources.files("surek.resources") / "README.md"
            console.print(readme_path.read_text())
        except FileNotFoundError:
            console.print("[yellow]README not available.[/yellow]")
        raise typer.Exit()


@app.callback(invoke_without_command=True)
def main(
    ctx: typer.Context,
    version: bool | None = typer.Option(
        None, "--version", "-v", callback=version_callback, is_eager=True, help="Show version"
    ),
    help_llm: bool | None = typer.Option(
        None, "--help-llm", callback=help_llm_callback, is_eager=True,
        help="Print full documentation for LLM consumption"
    ),
    help_readme: bool | None = typer.Option(
        None, "--help-readme", callback=help_readme_callback, is_eager=True,
        help="Print README documentation"
    ),
) -> None:
    """Surek - Docker Compose orchestration for self-hosted services.

    Run without arguments to launch the interactive TUI.
    """
    if ctx.invoked_subcommand is None:
        # Launch TUI when no command is given
        try:
            from surek.tui import run_tui

            run_tui()
        except SurekError as e:
            console.print(f"[red]Error:[/red] {e}")
            raise typer.Exit(1) from None


def run() -> None:
    """Entry point for the CLI."""
    try:
        app()
    except SurekError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1) from None


if __name__ == "__main__":
    run()
