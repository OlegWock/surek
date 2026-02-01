"""System container management commands."""

import typer

app = typer.Typer(help="System container management")


@app.command(name="start")
def start() -> None:
    """Ensure correct Docker configuration and run system containers."""
    typer.echo("system start - not yet implemented")


@app.command(name="stop")
def stop() -> None:
    """Stop Surek system containers."""
    typer.echo("system stop - not yet implemented")
