"""Init and new commands for creating Surek configurations."""

from pathlib import Path
from typing import Optional

import typer
import yaml
from rich.console import Console
from rich.prompt import Confirm, Prompt

console = Console()


def init_command(
    git_only: bool = typer.Option(False, "--git-only", help="Only add surek-data to .gitignore"),
) -> None:
    """Initialize Surek configuration in the current directory."""
    if git_only:
        _add_to_gitignore("surek-data")
        console.print("[green]Added 'surek-data' to .gitignore[/green]")
        return

    # Interactive prompts
    root_domain = Prompt.ask("Root domain", default="example.com")
    default_user = Prompt.ask("Default username", default="admin")
    default_password = Prompt.ask("Default password", password=True)

    if not default_password:
        console.print("[red]Password cannot be empty[/red]")
        raise typer.Exit(1)

    configure_backup = Confirm.ask("Configure S3 backup?", default=False)
    backup_config: Optional[dict[str, str]] = None
    if configure_backup:
        backup_config = {
            "password": Prompt.ask("Backup encryption password", password=True),
            "s3_endpoint": Prompt.ask("S3 endpoint"),
            "s3_bucket": Prompt.ask("S3 bucket name"),
            "s3_access_key": Prompt.ask("S3 access key"),
            "s3_secret_key": Prompt.ask("S3 secret key", password=True),
        }

    configure_github = Confirm.ask("Configure GitHub access?", default=False)
    github_config: Optional[dict[str, str]] = None
    if configure_github:
        github_config = {"pat": Prompt.ask("GitHub Personal Access Token", password=True)}

    # Build config
    config: dict[str, object] = {
        "root_domain": root_domain,
        "default_auth": f"{default_user}:{default_password}",
    }
    if backup_config:
        config["backup"] = backup_config
    if github_config:
        config["github"] = github_config

    # Write files
    config_path = Path("surek.yml")
    if config_path.exists():
        if not Confirm.ask("surek.yml already exists. Overwrite?", default=False):
            console.print("[yellow]Aborted[/yellow]")
            raise typer.Exit(0)

    with open(config_path, "w") as f:
        yaml.dump(config, f, default_flow_style=False, sort_keys=False)

    Path("stacks").mkdir(exist_ok=True)
    _add_to_gitignore("surek-data")

    console.print("[green]Created surek.yml and stacks/ directory[/green]")


def new_command() -> None:
    """Create a new stack interactively."""
    name = Prompt.ask("Stack name")
    if not name:
        console.print("[red]Stack name cannot be empty[/red]")
        raise typer.Exit(1)

    source_type = Prompt.ask("Source type", choices=["local", "github"], default="local")

    source: dict[str, str] = {"type": source_type}
    if source_type == "github":
        source["slug"] = Prompt.ask("GitHub repo (owner/repo or owner/repo#branch)")

    compose_path = Prompt.ask("Compose file path", default="./docker-compose.yml")

    # Public endpoints
    public: list[dict[str, Optional[str]]] = []
    while Confirm.ask("Add a public endpoint?", default=len(public) == 0):
        domain = Prompt.ask("Domain (e.g., app.<root>)")
        target = Prompt.ask("Target (service:port)")
        add_auth = Confirm.ask("Add authentication?", default=False)
        auth: Optional[str] = None
        if add_auth:
            auth = Prompt.ask("Auth (user:pass or <default_auth>)", default="<default_auth>")
        public.append({"domain": domain, "target": target, "auth": auth})

    # Create stack directory and config
    stack_dir = Path("stacks") / name
    stack_dir.mkdir(parents=True, exist_ok=True)

    config: dict[str, object] = {
        "name": name,
        "source": source,
        "compose_file_path": compose_path,
    }
    if public:
        # Remove None auth values
        config["public"] = [
            {k: v for k, v in endpoint.items() if v is not None} for endpoint in public
        ]

    config_path = stack_dir / "surek.stack.yml"
    with open(config_path, "w") as f:
        yaml.dump(config, f, default_flow_style=False, sort_keys=False)

    # Create empty compose file if local source
    if source_type == "local":
        compose_file = stack_dir / "docker-compose.yml"
        if not compose_file.exists():
            compose_file.write_text("version: '3.8'\n\nservices:\n  # Add your services here\n")

    console.print(f"[green]Created stack '{name}' at {stack_dir}[/green]")


def _add_to_gitignore(entry: str) -> None:
    """Add an entry to .gitignore if not already present."""
    gitignore_path = Path(".gitignore")

    if gitignore_path.exists():
        content = gitignore_path.read_text()
        lines = content.splitlines()
        if entry not in lines:
            with open(gitignore_path, "a") as f:
                if content and not content.endswith("\n"):
                    f.write("\n")
                f.write(f"{entry}\n")
    else:
        gitignore_path.write_text(f"{entry}\n")
