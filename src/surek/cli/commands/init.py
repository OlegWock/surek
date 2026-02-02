"""Init and new commands for creating Surek configurations."""

import json
from pathlib import Path

import typer
import yaml
from rich.console import Console
from rich.prompt import Confirm, Prompt

console = Console()

# Schema file names
SUREK_CONFIG_SCHEMA = "surek.config.schema.json"
STACK_CONFIG_SCHEMA = "surek.stack.schema.json"


def generate_schemas(output_dir: Path = Path(".")) -> tuple[Path, Path]:
    """Generate JSON schemas for surek configuration files.

    Args:
        output_dir: Directory to write schema files.

    Returns:
        Tuple of (surek_config_schema_path, stack_config_schema_path).
    """
    from surek.models.config import SurekConfig
    from surek.models.stack import StackConfig

    output_dir.mkdir(parents=True, exist_ok=True)

    # Generate surek config schema
    surek_schema = SurekConfig.model_json_schema()
    surek_schema_path = output_dir / SUREK_CONFIG_SCHEMA
    surek_schema_path.write_text(json.dumps(surek_schema, indent=2))

    # Generate stack config schema
    stack_schema = StackConfig.model_json_schema()
    stack_schema_path = output_dir / STACK_CONFIG_SCHEMA
    stack_schema_path.write_text(json.dumps(stack_schema, indent=2))

    return surek_schema_path, stack_schema_path


def schema_command() -> None:
    """Generate JSON schemas for configuration files."""
    surek_path, stack_path = generate_schemas()
    console.print("[green]Generated schemas:[/green]")
    console.print(f"  • {surek_path}")
    console.print(f"  • {stack_path}")
    console.print("\nAdd to your YAML files for autocompletion:")
    console.print(f"  # yaml-language-server: $schema=./{SUREK_CONFIG_SCHEMA}")
    console.print(f"  # yaml-language-server: $schema=../../{STACK_CONFIG_SCHEMA}")


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
        raise typer.Exit(1) from None

    configure_backup = Confirm.ask("Configure S3 backup?", default=False)
    backup_config: dict[str, str] | None = None
    if configure_backup:
        backup_config = {
            "password": Prompt.ask("Backup encryption password", password=True),
            "s3_endpoint": Prompt.ask("S3 endpoint"),
            "s3_bucket": Prompt.ask("S3 bucket name"),
            "s3_access_key": Prompt.ask("S3 access key"),
            "s3_secret_key": Prompt.ask("S3 secret key", password=True),
        }

    configure_github = Confirm.ask("Configure GitHub access?", default=False)
    github_config: dict[str, str] | None = None
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
    if config_path.exists() and not Confirm.ask(
        "surek.yml already exists. Overwrite?", default=False
    ):
        console.print("[yellow]Aborted[/yellow]")
        raise typer.Exit(0)

    # Generate schemas
    generate_schemas()

    # Write config with schema reference
    with open(config_path, "w") as f:
        f.write(f"# yaml-language-server: $schema=./{SUREK_CONFIG_SCHEMA}\n")
        yaml.dump(config, f, default_flow_style=False, sort_keys=False)

    Path("stacks").mkdir(exist_ok=True)
    _add_to_gitignore("surek-data")

    console.print("[green]Created surek.yml and stacks/ directory[/green]")
    console.print("[dim]Generated JSON schemas for editor autocompletion[/dim]")


def new_command() -> None:
    """Create a new stack interactively."""
    # Load root domain from config if available
    root_domain = "example.com"
    config_path = Path("surek.yml")
    if config_path.exists():
        try:
            with open(config_path) as f:
                surek_config = yaml.safe_load(f)
                if surek_config and "root_domain" in surek_config:
                    root_domain = surek_config["root_domain"]
        except Exception:
            pass

    name = Prompt.ask("Stack name")
    if not name:
        console.print("[red]Stack name cannot be empty[/red]")
        raise typer.Exit(1) from None

    source_type = Prompt.ask("Source type", choices=["local", "github"], default="local")

    source: dict[str, str] = {"type": source_type}
    if source_type == "github":
        source["slug"] = Prompt.ask("GitHub repo (owner/repo or owner/repo#branch)")

    compose_path = Prompt.ask("Compose file path", default="./docker-compose.yml")

    # Public endpoints
    public: list[dict[str, str | None]] = []
    endpoint_num = 1
    while True:
        if endpoint_num == 1:
            prompt = "Add a public endpoint?"
        else:
            prompt = f"Add another public endpoint? ({len(public)} configured)"

        if not Confirm.ask(prompt, default=(endpoint_num == 1)):
            break

        console.print(f"[dim]Tip: Use <root> for domain, e.g., 'app' becomes 'app.{root_domain}'[/dim]")
        subdomain = Prompt.ask("Subdomain (without .<root>)")
        domain = f"{subdomain}.<root>" if subdomain else "app.<root>"
        console.print(f"[dim]  → Will be accessible at: https://{subdomain}.{root_domain}[/dim]")

        target = Prompt.ask("Target (service:port)")
        add_auth = Confirm.ask("Add authentication?", default=False)
        auth: str | None = None
        if add_auth:
            auth = Prompt.ask("Auth (user:pass or <default_auth>)", default="<default_auth>")
        public.append({"domain": domain, "target": target, "auth": auth})
        endpoint_num += 1

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

    # Write stack config with schema reference
    config_path = stack_dir / "surek.stack.yml"
    with open(config_path, "w") as f:
        f.write(f"# yaml-language-server: $schema=../../{STACK_CONFIG_SCHEMA}\n")
        yaml.dump(config, f, default_flow_style=False, sort_keys=False)

    # Create empty compose file if local source
    if source_type == "local":
        compose_file = stack_dir / "docker-compose.yml"
        if not compose_file.exists():
            compose_file.write_text("services:\n  # Add your services here\n")

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
