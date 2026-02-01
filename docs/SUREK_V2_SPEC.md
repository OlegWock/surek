# Surek v2 Implementation Specification

A complete specification for implementing Surek v2 in Python. This document covers architecture, all features, configuration formats, algorithms, CLI commands, and the interactive TUI.

## Table of Contents

1. [Overview](#1-overview)
2. [Technology Stack](#2-technology-stack)
3. [Project Structure](#3-project-structure)
4. [Configuration Files](#4-configuration-files)
5. [CLI Interface](#5-cli-interface)
6. [Interactive TUI](#6-interactive-tui)
7. [Core Algorithms](#7-core-algorithms)
8. [System Containers](#8-system-containers)
9. [Backup System](#9-backup-system)
10. [Docker Integration](#10-docker-integration)
11. [Error Handling](#11-error-handling)
12. [Backward Compatibility](#12-backward-compatibility)

---

## 1. Overview

Surek is a Docker Compose orchestration tool for self-hosted services. It provides:

- Automatic reverse proxy configuration via Caddy
- Volume management with bind mounts for backup
- Shared networking across all stacks
- Environment variable injection with template variables
- Automated backups to S3-compatible storage
- Both CLI and interactive TUI interfaces

### 1.1 Design Principles

1. **Backward Compatible** - Must work with existing v1 `surek.yml` and `surek.stack.yml` files
2. **Dual Interface** - CLI for scripting/automation, TUI for interactive management
3. **Informative** - Rich status information including health, resources, and logs

---

## 2. Technology Stack

### 2.1 Core Dependencies

| Package | Purpose |
|---------|---------|
| `pydantic` | Configuration validation and parsing |
| `textual` | Interactive TUI framework |
| `typer` | CLI argument parsing |
| `rich` | Terminal formatting and tables |
| `docker` | Docker Engine API client (official Python SDK) |
| `pyyaml` | YAML parsing and serialization |
| `httpx` | HTTP client for GitHub API |
| `boto3` | S3 client for backup operations |
| `bcrypt` | Password hashing for Caddy basic auth |

### 2.2 Development Dependencies

| Package | Purpose |
|---------|---------|
| `pytest` | Testing framework |
| `pytest-asyncio` | Async test support |
| `mypy` | Type checking |
| `ruff` | Linting and formatting |

### 2.3 Project Management

- **Package Manager:** `uv`
- **Distribution:** PyPI
- **Entry Point:** `surek` command installed via pip/uv

### 2.4 System Requirements

- Python 3.13+
- Docker Engine with Compose plugin
- Domain pointed to server (for HTTPS)

---

## 3. Project Structure

```
surek/
├── pyproject.toml
├── README.md
├── src/
│   └── surek/
│       ├── __init__.py
│       ├── __main__.py          # Entry point
│       ├── cli/
│       │   ├── __init__.py
│       │   ├── main.py          # Typer app definition
│       │   ├── commands/
│       │   │   ├── __init__.py
│       │   │   ├── system.py    # system start/stop
│       │   │   ├── stack.py     # deploy/start/stop/status
│       │   │   ├── backup.py    # backup commands
│       │   │   ├── info.py      # info/logs commands
│       │   │   └── init.py      # init/new commands
│       │   └── help_llm.py      # LLM documentation generator
│       ├── tui/
│       │   ├── __init__.py
│       │   ├── app.py           # Main Textual app
│       │   ├── screens/
│       │   │   ├── __init__.py
│       │   │   ├── stacks.py    # Stack list screen
│       │   │   ├── backups.py   # Backup list screen
│       │   │   └── details.py   # Stack details screen
│       │   └── widgets/
│       │       ├── __init__.py
│       │       ├── stack_table.py
│       │       ├── log_viewer.py
│       │       └── status_bar.py
│       ├── core/
│       │   ├── __init__.py
│       │   ├── config.py        # Configuration loading
│       │   ├── stacks.py        # Stack operations
│       │   ├── compose.py       # Compose file transformation
│       │   ├── docker.py        # Docker client wrapper
│       │   ├── github.py        # GitHub operations
│       │   ├── backup.py        # Backup operations
│       │   └── variables.py     # Variable expansion
│       ├── models/
│       │   ├── __init__.py
│       │   ├── config.py        # Pydantic models for surek.yml
│       │   ├── stack.py         # Pydantic models for stack config
│       │   └── compose.py       # Docker Compose spec types
│       ├── utils/
│       │   ├── __init__.py
│       │   ├── paths.py         # Path constants and helpers
│       │   ├── logging.py       # Logging setup
│       │   └── env.py           # Environment variable handling
│       └── resources/
│           ├── system/          # System container definitions
│           │   ├── surek.stack.yml
│           │   ├── docker-compose.yml
│           │   ├── backup-daily.env
│           │   ├── backup-weekly.env
│           │   └── backup-monthly.env
│           └── llm_docs.md      # Full documentation for --help-llm
└── tests/
    ├── __init__.py
    ├── test_config.py
    ├── test_compose.py
    └── test_stacks.py
```

### 3.1 Package Data

The `resources/` directory must be included in the package distribution. Configure in `pyproject.toml`:

```toml
[tool.setuptools.package-data]
surek = ["resources/**/*"]
```

---

## 4. Configuration Files

### 4.1 Main Configuration (`surek.yml`)

**Location:** Current working directory, filename `surek.yml` or `surek.yaml`

#### 4.1.1 Schema

```python
from pydantic import BaseModel, Field, field_validator
from typing import Optional
import os
import re

class BackupConfig(BaseModel):
    password: str
    s3_endpoint: str
    s3_bucket: str
    s3_access_key: str
    s3_secret_key: str

class GitHubConfig(BaseModel):
    pat: str

class NotificationConfig(BaseModel):
    """
    Optional notification settings for backup failures.
    
    NOTE: In v2.0, notifications are tracked but not sent. The configuration
    is accepted for forward compatibility. Actual notification delivery
    (webhook, email, Telegram) will be implemented in a future release.
    """
    webhook_url: Optional[str] = None
    email: Optional[str] = None
    telegram_chat_id: Optional[str] = None  # Reserved for future use
    
class SystemServicesConfig(BaseModel):
    """Control which system services are enabled."""
    portainer: bool = True
    netdata: bool = True

class SurekConfig(BaseModel):
    root_domain: str
    default_auth: str  # Format: "user:password"
    backup: Optional[BackupConfig] = None
    github: Optional[GitHubConfig] = None
    notifications: Optional[NotificationConfig] = None
    system_services: SystemServicesConfig = Field(default_factory=SystemServicesConfig)
    
    # Parsed from default_auth
    default_user: str = ""
    default_password: str = ""
    
    @field_validator('default_auth')
    @classmethod
    def validate_auth_format(cls, v: str) -> str:
        if ':' not in v or v.count(':') != 1:
            raise ValueError("default_auth must be in 'user:password' format")
        return v
    
    def model_post_init(self, __context) -> None:
        user, password = self.default_auth.split(':')
        object.__setattr__(self, 'default_user', user)
        object.__setattr__(self, 'default_password', password)
```

#### 4.1.2 Environment Variable Expansion

Before validation, expand `${VAR_NAME}` patterns in the raw YAML:

```python
def expand_env_vars(value: str) -> str:
    """Expand ${VAR_NAME} patterns with environment variables."""
    pattern = r'\$\{([^}]+)\}'
    
    def replacer(match: re.Match) -> str:
        var_name = match.group(1)
        env_value = os.environ.get(var_name)
        if env_value is None:
            raise ValueError(f"Environment variable '{var_name}' is not set")
        return env_value
    
    return re.sub(pattern, replacer, value)

def expand_env_vars_in_dict(data: dict) -> dict:
    """Recursively expand environment variables in a dictionary."""
    result = {}
    for key, value in data.items():
        if isinstance(value, str):
            result[key] = expand_env_vars(value)
        elif isinstance(value, dict):
            result[key] = expand_env_vars_in_dict(value)
        elif isinstance(value, list):
            result[key] = [
                expand_env_vars(item) if isinstance(item, str) 
                else expand_env_vars_in_dict(item) if isinstance(item, dict)
                else item
                for item in value
            ]
        else:
            result[key] = value
    return result
```

#### 4.1.3 Example Configuration

```yaml
root_domain: example.com
default_auth: admin:${SUREK_DEFAULT_PASSWORD}

backup:
  password: ${BACKUP_PASSWORD}
  s3_endpoint: s3.eu-central-003.backblazeb2.com
  s3_bucket: my-backups
  s3_access_key: ${AWS_ACCESS_KEY}
  s3_secret_key: ${AWS_SECRET_KEY}

github:
  pat: ${GITHUB_PAT}

notifications:
  webhook_url: https://hooks.slack.com/services/xxx

system_services:
  portainer: true
  netdata: false  # Disable netdata
```

#### 4.1.4 Loading Algorithm

```python
def load_config() -> SurekConfig:
    """Load and validate the main Surek configuration."""
    cwd = Path.cwd()
    
    # Try both extensions
    for filename in ["surek.yml", "surek.yaml"]:
        config_path = cwd / filename
        if config_path.exists():
            break
    else:
        raise SurekError(
            "Config file not found. "
            "Make sure you have surek.yml in current working directory"
        )
    
    # Parse YAML
    with open(config_path) as f:
        raw_data = yaml.safe_load(f)
    
    # Expand environment variables
    expanded_data = expand_env_vars_in_dict(raw_data)
    
    # Convert snake_case to snake_case (Pydantic handles this natively)
    # Validate and create model
    try:
        return SurekConfig(**expanded_data)
    except ValidationError as e:
        raise SurekConfigError(f"Invalid configuration: {e}")
```

### 4.2 Stack Configuration (`surek.stack.yml`)

**Location:** Any subdirectory of `stacks/`, filename must be exactly `surek.stack.yml`

#### 4.2.1 Schema

```python
from pydantic import BaseModel, Field, field_validator
from typing import Optional, Literal, Union
from enum import Enum

class LocalSource(BaseModel):
    type: Literal["local"]

class GitHubSource(BaseModel):
    type: Literal["github"]
    slug: str  # Format: "owner/repo" or "owner/repo#ref"
    
    @property
    def owner(self) -> str:
        return self.slug.split('/')[0]
    
    @property
    def repo(self) -> str:
        repo_with_ref = self.slug.split('/')[1]
        return repo_with_ref.split('#')[0]
    
    @property
    def ref(self) -> str:
        if '#' in self.slug:
            return self.slug.split('#')[1]
        return 'HEAD'

Source = Union[LocalSource, GitHubSource]

class PublicEndpoint(BaseModel):
    domain: str
    target: str  # Format: "service:port" or "service"
    auth: Optional[str] = None  # Format: "user:password" or "<default_auth>"
    
    @property
    def service_name(self) -> str:
        return self.target.split(':')[0]
    
    @property
    def port(self) -> int:
        if ':' in self.target:
            return int(self.target.split(':')[1])
        return 80

class EnvConfig(BaseModel):
    shared: list[str] = Field(default_factory=list)
    by_container: dict[str, list[str]] = Field(default_factory=dict)

class BackupExcludeConfig(BaseModel):
    exclude_volumes: list[str] = Field(default_factory=list)

class StackConfig(BaseModel):
    name: str
    source: Source
    compose_file_path: str = "./docker-compose.yml"
    public: list[PublicEndpoint] = Field(default_factory=list)
    env: Optional[EnvConfig] = None
    backup: BackupExcludeConfig = Field(default_factory=BackupExcludeConfig)
    
    @field_validator('name')
    @classmethod
    def validate_name(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("Stack name cannot be empty")
        # Validate characters suitable for Docker project names
        if not re.match(r'^[a-zA-Z0-9][a-zA-Z0-9_-]*$', v):
            raise ValueError(
                "Stack name must start with alphanumeric and contain only "
                "alphanumeric, underscore, or hyphen characters"
            )
        return v
```

#### 4.2.2 Loading Algorithm

```python
def load_stack_config(path: Path) -> StackConfig:
    """Load and validate a stack configuration file."""
    with open(path) as f:
        raw_data = yaml.safe_load(f)
    
    # Expand environment variables
    expanded_data = expand_env_vars_in_dict(raw_data)
    
    try:
        return StackConfig(**expanded_data)
    except ValidationError as e:
        raise StackConfigError(f"Invalid stack config at {path}: {e}")
```

---

## 5. CLI Interface

### 5.1 Command Structure

The CLI uses Typer with the following structure:

```
surek [OPTIONS] [COMMAND]

Options:
  --help-llm    Print full documentation for LLM consumption
  --version     Show version and exit
  --help        Show help and exit

Commands:
  (no command)  Launch interactive TUI
  init          Initialize Surek configuration
  new           Create a new stack (interactive)
  deploy        Deploy a stack
  start         Start a deployed stack
  stop          Stop a running stack
  status        Show status of all stacks
  info          Show detailed information about a stack
  logs          View logs for a stack or service
  validate      Validate a stack configuration
  backup        Backup management commands
  system        System container management
```

### 5.2 Command Specifications

#### 5.2.1 `surek` (No Command)

**Behavior:** Launch interactive TUI

```python
@app.callback(invoke_without_command=True)
def main(ctx: typer.Context):
    if ctx.invoked_subcommand is None:
        # Launch TUI
        from surek.tui import SurekApp
        app = SurekApp()
        app.run()
```

#### 5.2.2 `surek --help-llm`

**Behavior:** Print comprehensive documentation suitable for LLM consumption

```python
@app.callback()
def main(
    help_llm: bool = typer.Option(False, "--help-llm", help="Print LLM documentation"),
    version: bool = typer.Option(False, "--version", help="Show version"),
):
    if help_llm:
        docs_path = resources.files("surek.resources") / "llm_docs.md"
        print(docs_path.read_text())
        raise typer.Exit()
```

The `llm_docs.md` file should contain:
- Complete command reference with all options
- Configuration file formats with examples
- Variable reference
- Common workflows and examples
- Troubleshooting guide

#### 5.2.3 `surek init`

**Behavior:** Interactive wizard to create `surek.yml` and `.gitignore`

```
surek init [OPTIONS]

Options:
  --git-only    Only add surek-data to .gitignore
```

**Algorithm:**

```python
@init_app.command()
def init(git_only: bool = typer.Option(False, "--git-only")):
    if git_only:
        add_to_gitignore("surek-data")
        console.print("[green]Added 'surek-data' to .gitignore[/green]")
        return
    
    # Interactive prompts
    root_domain = Prompt.ask("Root domain", default="example.com")
    default_user = Prompt.ask("Default username", default="admin")
    default_password = Prompt.ask("Default password", password=True)
    
    configure_backup = Confirm.ask("Configure S3 backup?", default=False)
    backup_config = None
    if configure_backup:
        backup_config = {
            "password": Prompt.ask("Backup encryption password", password=True),
            "s3_endpoint": Prompt.ask("S3 endpoint"),
            "s3_bucket": Prompt.ask("S3 bucket name"),
            "s3_access_key": Prompt.ask("S3 access key"),
            "s3_secret_key": Prompt.ask("S3 secret key", password=True),
        }
    
    configure_github = Confirm.ask("Configure GitHub access?", default=False)
    github_config = None
    if configure_github:
        github_config = {"pat": Prompt.ask("GitHub Personal Access Token", password=True)}
    
    # Build config
    config = {
        "root_domain": root_domain,
        "default_auth": f"{default_user}:{default_password}",
    }
    if backup_config:
        config["backup"] = backup_config
    if github_config:
        config["github"] = github_config
    
    # Write files
    with open("surek.yml", "w") as f:
        yaml.dump(config, f, default_flow_style=False)
    
    Path("stacks").mkdir(exist_ok=True)
    add_to_gitignore("surek-data")
    
    console.print("[green]Created surek.yml and stacks/ directory[/green]")
```

#### 5.2.4 `surek new`

**Behavior:** Interactive wizard to create a new stack

**Algorithm:**

```python
@app.command()
def new():
    """Create a new stack interactively."""
    name = Prompt.ask("Stack name")
    
    source_type = Prompt.ask(
        "Source type",
        choices=["local", "github"],
        default="local"
    )
    
    source = {"type": source_type}
    if source_type == "github":
        source["slug"] = Prompt.ask("GitHub repo (owner/repo#branch)")
    
    compose_path = Prompt.ask(
        "Compose file path",
        default="./docker-compose.yml"
    )
    
    # Public endpoints
    public = []
    while Confirm.ask("Add a public endpoint?", default=len(public) == 0):
        domain = Prompt.ask(f"Domain (e.g., app.<root>)")
        target = Prompt.ask("Target (service:port)")
        add_auth = Confirm.ask("Add authentication?", default=False)
        auth = None
        if add_auth:
            auth = Prompt.ask("Auth (user:pass or <default_auth>)", default="<default_auth>")
        public.append({"domain": domain, "target": target, "auth": auth})
    
    # Create stack directory and config
    stack_dir = Path("stacks") / name
    stack_dir.mkdir(parents=True, exist_ok=True)
    
    config = {
        "name": name,
        "source": source,
        "compose_file_path": compose_path,
    }
    if public:
        config["public"] = public
    
    config_path = stack_dir / "surek.stack.yml"
    with open(config_path, "w") as f:
        yaml.dump(config, f, default_flow_style=False)
    
    # Create empty compose file if local
    if source_type == "local":
        compose_file = stack_dir / "docker-compose.yml"
        if not compose_file.exists():
            compose_file.write_text("version: '3.8'\n\nservices:\n  # Add your services here\n")
    
    console.print(f"[green]Created stack '{name}' at {stack_dir}[/green]")
```

#### 5.2.5 `surek deploy <stack-name>`

**Behavior:** Deploy a stack (pull sources, transform compose, start containers)

```
surek deploy <stack-name> [OPTIONS]

Arguments:
  stack-name    Name of the stack to deploy

Options:
  --force       Force re-download even if cached
```

**Algorithm:** See Section 7.2

#### 5.2.6 `surek start <stack-name>`

**Behavior:** Start an already deployed stack without re-transformation

```
surek start <stack-name>
```

#### 5.2.7 `surek stop <stack-name>`

**Behavior:** Stop a running stack

```
surek stop <stack-name>
```

#### 5.2.8 `surek status`

**Behavior:** Show status of all stacks with health and resource usage

```
surek status [OPTIONS]

Options:
  --json        Output as JSON
```

**Output Format:**

```
┌─────────────────────┬────────────────────┬─────────┬────────┬──────────────────┐
│ Stack               │ Status             │ CPU     │ Memory │ Path             │
├─────────────────────┼────────────────────┼─────────┼────────┼──────────────────┤
│ System containers   │ ✓ Running (3/3)    │ 2.1%    │ 512MB  │                  │
│ gitea               │ ✓ Running (2/2)    │ 0.5%    │ 256MB  │ stacks/gitea     │
│ nextcloud           │ ✓ Running (1/2)    │ 1.2%    │ 1.2GB  │ stacks/nextcloud │
│                     │   ↳ db: healthy    │         │        │                  │
│                     │   ↳ app: starting  │         │        │                  │
│ wordpress           │ × Down             │ -       │ -      │ stacks/wordpress │
└─────────────────────┴────────────────────┴─────────┴────────┴──────────────────┘
```

**Algorithm:**

```python
@app.command()
def status(json_output: bool = typer.Option(False, "--json")):
    config = load_config()
    stacks = get_available_stacks()
    
    results = []
    
    # System status
    system_status = get_stack_status_detailed("surek-system")
    results.append({
        "name": "System containers",
        "status": system_status.status_text,
        "health": system_status.health_details,
        "cpu": system_status.cpu_percent,
        "memory": system_status.memory_mb,
        "path": "",
    })
    
    # User stacks
    for stack in stacks:
        if not stack.valid:
            results.append({
                "name": stack.path,
                "status": "Invalid config",
                "error": stack.error,
            })
            continue
        
        status = get_stack_status_detailed(stack.config.name)
        results.append({
            "name": stack.config.name,
            "status": status.status_text,
            "health": status.health_details,
            "cpu": status.cpu_percent,
            "memory": status.memory_mb,
            "path": str(stack.path.parent.relative_to(Path.cwd())),
        })
    
    if json_output:
        print(json.dumps(results, indent=2))
    else:
        print_status_table(results)
```

#### 5.2.9 `surek info <stack>`

**Behavior:** Show detailed information about a stack

```
surek info <stack-name> [OPTIONS]

Arguments:
  stack-name    Name of the stack

Options:
  -l, --logs    Include last 100 log lines
```

**Output Format:**

```
Stack: gitea
Status: ✓ Running
Source: github (OlegWock/gitea-docker#main)
Compose: ./docker-compose.yml

Services:
┌───────────┬─────────────────────┬──────────┬─────────┬────────┬─────────────┐
│ Service   │ Image               │ Status   │ Health  │ CPU    │ Memory      │
├───────────┼─────────────────────┼──────────┼─────────┼────────┼─────────────┤
│ gitea     │ gitea/gitea:latest  │ Running  │ healthy │ 0.3%   │ 180MB       │
│ db        │ postgres:15         │ Running  │ healthy │ 0.2%   │ 76MB        │
└───────────┴─────────────────────┴──────────┴─────────┴────────┴─────────────┘

Volumes:
┌────────────────┬──────────────────────────────────────────┬───────────┐
│ Volume         │ Path                                     │ Size      │
├────────────────┼──────────────────────────────────────────┼───────────┤
│ gitea_data     │ surek-data/volumes/gitea/gitea_data      │ 1.2 GB    │
│ db_data        │ surek-data/volumes/gitea/db_data         │ 256 MB    │
└────────────────┴──────────────────────────────────────────┴───────────┘

Public Endpoints:
  • https://gitea.example.com → gitea:3000

[Logs output if --logs flag provided]
```

#### 5.2.10 `surek logs <stack> [service]`

**Behavior:** View logs for a stack or specific service

```
surek logs <stack-name> [service] [OPTIONS]

Arguments:
  stack-name    Name of the stack
  service       Optional specific service name

Options:
  -f, --follow  Follow log output (default, launches TUI)
  -t, --tail N  Output last N lines and exit (default: 100)
  --no-follow   Disable follow mode, just print recent logs
```

**Algorithm:**

```python
@app.command()
def logs(
    stack_name: str,
    service: Optional[str] = typer.Argument(None),
    follow: bool = typer.Option(True, "-f", "--follow"),
    tail: int = typer.Option(100, "-t", "--tail"),
    no_follow: bool = typer.Option(False, "--no-follow"),
):
    stack = get_stack_by_name(stack_name)
    project_dir = get_stack_project_dir(stack.config.name)
    compose_file = project_dir / "docker-compose.surek.yml"
    
    if no_follow or not follow:
        # Static mode - print and exit
        output = run_docker_compose(
            compose_file=compose_file,
            project_dir=project_dir,
            command="logs",
            args=["--tail", str(tail)] + ([service] if service else []),
        )
        print(output)
    else:
        # Interactive mode - launch TUI log viewer
        from surek.tui import LogViewerApp
        app = LogViewerApp(stack_name=stack_name, service=service)
        app.run()
```

#### 5.2.11 `surek validate <path>`

**Behavior:** Validate a stack configuration file

```
surek validate <stack-path>

Arguments:
  stack-path    Path to surek.stack.yml file
```

#### 5.2.12 `surek system start`

**Behavior:** Create Docker network and start system containers

```
surek system start
```

**Algorithm:**

```python
@system_app.command()
def start():
    """Ensure correct Docker configuration and run system containers."""
    config = load_config()
    console.print("Loaded config")
    
    docker = get_docker_client()
    
    # Check if Surek network exists
    networks = docker.networks.list(names=[SUREK_NETWORK])
    if not networks:
        console.print("Surek network is missing, creating")
        docker.networks.create(
            name=SUREK_NETWORK,
            driver="bridge",
            labels=DEFAULT_LABELS,
        )
    
    # Stop existing system containers (silent)
    stop_stack_by_config_path(SYSTEM_SERVICES_CONFIG, silent=True)
    
    # Deploy system stack
    deploy_stack_by_config_path(SYSTEM_SERVICES_CONFIG, config)
```

#### 5.2.13 `surek system stop`

**Behavior:** Stop system containers

```
surek system stop
```

#### 5.2.14 `surek backup` / `surek backup list`

**Behavior:** List all backups in S3

```
surek backup [list] [OPTIONS]

Options:
  --stack       Filter by stack name
  --json        Output as JSON
```

**Output Format:**

```
┌─────────────────────────────────────────────┬────────────┬───────────┬──────────────────────┐
│ Backup                                      │ Type       │ Size      │ Created              │
├─────────────────────────────────────────────┼────────────┼───────────┼──────────────────────┤
│ daily-backup-2024-01-15T02-00-00.tar.gz     │ Daily      │ 1.2 GB    │ 2024-01-15 02:00:00  │
│ daily-backup-2024-01-14T02-00-00.tar.gz     │ Daily      │ 1.1 GB    │ 2024-01-14 02:00:00  │
│ weekly-backup-2024-01-08T03-00-00.tar.gz    │ Weekly     │ 1.0 GB    │ 2024-01-08 03:00:00  │
│ monthly-backup-2024-01-01T04-00-00.tar.gz   │ Monthly    │ 950 MB    │ 2024-01-01 04:00:00  │
└─────────────────────────────────────────────┴────────────┴───────────┴──────────────────────┘
```

#### 5.2.15 `surek backup run`

**Behavior:** Trigger an immediate backup

```
surek backup run [OPTIONS]

Options:
  --type        Backup type: daily, weekly, monthly (default: daily)
```

**Algorithm:**

```python
@backup_app.command()
def run(backup_type: str = typer.Option("daily", "--type")):
    config = load_config()
    if not config.backup:
        raise SurekError("Backup is not configured in surek.yml")
    
    # Execute backup command in the backup container
    docker = get_docker_client()
    container = docker.containers.get("surek-system-backup-1")
    
    # Trigger backup by sending signal or running backup command
    exit_code, output = container.exec_run(
        f"/usr/local/bin/backup --config /etc/dockervolumebackup/conf.d/backup-{backup_type}.env"
    )
    
    if exit_code != 0:
        raise SurekError(f"Backup failed: {output.decode()}")
    
    console.print(f"[green]Backup completed successfully[/green]")
```

#### 5.2.16 `surek backup restore`

**Behavior:** Restore volumes from a backup

```
surek backup restore [OPTIONS]

Options:
  --id          Backup filename to restore (required in non-interactive mode)
  --stack       Stack to restore (optional, restores all if not specified)
  --volume      Specific volume to restore (optional)
```

**Interactive Mode:** If called without `--id`, launches TUI to select backup and options.

**Algorithm:**

```python
@backup_app.command()
def restore(
    backup_id: Optional[str] = typer.Option(None, "--id"),
    stack: Optional[str] = typer.Option(None, "--stack"),
    volume: Optional[str] = typer.Option(None, "--volume"),
):
    config = load_config()
    if not config.backup:
        raise SurekError("Backup is not configured")
    
    if backup_id is None:
        # Launch interactive restore TUI
        from surek.tui import BackupRestoreApp
        app = BackupRestoreApp()
        app.run()
        return
    
    # Stop affected stacks
    if stack:
        console.print(f"Stopping stack {stack}...")
        stop_stack(get_stack_by_name(stack).config)
    else:
        console.print("Stopping all stacks...")
        for s in get_available_stacks():
            if s.valid:
                stop_stack(s.config, silent=True)
    
    # Download backup from S3
    console.print(f"Downloading backup {backup_id}...")
    s3 = get_s3_client(config.backup)
    backup_path = Path(tempfile.mkdtemp()) / backup_id
    s3.download_file(config.backup.s3_bucket, backup_id, str(backup_path))
    
    # Decrypt and extract
    console.print("Decrypting and extracting...")
    decrypt_and_extract_backup(backup_path, config.backup.password)
    
    # Restore volumes
    volumes_dir = get_data_dir() / "volumes"
    # ... restore logic
    
    console.print("[green]Restore completed. Start your stacks with 'surek start'[/green]")
```

---

## 6. Interactive TUI

### 6.1 Application Structure

The TUI is built with Textual and provides a dashboard for managing stacks.

```python
from textual.app import App, ComposeResult
from textual.widgets import Header, Footer, TabbedContent, TabPane
from textual.binding import Binding

class SurekApp(App):
    """Main Surek TUI application."""
    
    CSS_PATH = "styles.tcss"
    BINDINGS = [
        Binding("q", "quit", "Quit"),
        Binding("r", "refresh", "Refresh"),
        Binding("?", "help", "Help"),
    ]
    
    def compose(self) -> ComposeResult:
        yield Header()
        with TabbedContent():
            with TabPane("Stacks", id="stacks"):
                yield StacksScreen()
            with TabPane("Backups", id="backups"):
                yield BackupsScreen()
        yield Footer()
    
    def action_refresh(self) -> None:
        """Refresh all data."""
        self.query_one(StacksScreen).refresh_data()
```

### 6.2 Stacks Screen

Displays all stacks with status and available actions.

```python
from textual.screen import Screen
from textual.widgets import DataTable, Static
from textual.containers import Container

class StacksScreen(Screen):
    """Screen showing all stacks and their status."""
    
    BINDINGS = [
        Binding("d", "deploy", "Deploy"),
        Binding("s", "start", "Start"),
        Binding("x", "stop", "Stop"),
        Binding("enter", "details", "Details"),
        Binding("l", "logs", "Logs"),
    ]
    
    def compose(self) -> ComposeResult:
        yield Container(
            Static("Stacks", classes="title"),
            DataTable(id="stacks-table"),
            id="stacks-container"
        )
    
    def on_mount(self) -> None:
        table = self.query_one("#stacks-table", DataTable)
        table.add_columns("Stack", "Status", "Health", "CPU", "Memory", "Actions")
        self.refresh_data()
    
    def refresh_data(self) -> None:
        table = self.query_one("#stacks-table", DataTable)
        table.clear()
        
        # Add system containers row
        system_status = get_stack_status_detailed("surek-system")
        table.add_row(
            "System",
            system_status.status_text,
            system_status.health_summary,
            f"{system_status.cpu_percent:.1f}%",
            format_bytes(system_status.memory_bytes),
            "[d]eploy [s]tart [x]stop",
        )
        
        # Add user stacks
        for stack in get_available_stacks():
            if stack.valid:
                status = get_stack_status_detailed(stack.config.name)
                table.add_row(
                    stack.config.name,
                    status.status_text,
                    status.health_summary,
                    f"{status.cpu_percent:.1f}%",
                    format_bytes(status.memory_bytes),
                    "[d]eploy [s]tart [x]stop",
                )
    
    def action_details(self) -> None:
        """Show stack details."""
        table = self.query_one("#stacks-table", DataTable)
        row_key = table.cursor_row
        if row_key is not None:
            stack_name = table.get_cell(row_key, 0)
            self.app.push_screen(StackDetailsScreen(stack_name))
```

### 6.3 Stack Details Screen

Shows detailed information about a single stack with interactive log viewing.

```python
class StackDetailsScreen(Screen):
    """Detailed view of a single stack."""
    
    BINDINGS = [
        Binding("escape", "pop_screen", "Back"),
        Binding("l", "toggle_logs", "Toggle Logs"),
    ]
    
    def __init__(self, stack_name: str):
        super().__init__()
        self.stack_name = stack_name
    
    def compose(self) -> ComposeResult:
        yield Container(
            Static(f"Stack: {self.stack_name}", classes="title"),
            Container(
                DataTable(id="services-table"),
                DataTable(id="volumes-table"),
                id="info-panel"
            ),
            LogViewer(id="log-viewer"),
            id="details-container"
        )
    
    def on_mount(self) -> None:
        self.load_stack_info()
        self.start_log_stream()
    
    def load_stack_info(self) -> None:
        # Populate services table
        services_table = self.query_one("#services-table", DataTable)
        services_table.add_columns("Service", "Image", "Status", "Health", "CPU", "Memory")
        
        # Populate volumes table
        volumes_table = self.query_one("#volumes-table", DataTable)
        volumes_table.add_columns("Volume", "Path", "Size")
        
        # ... load data
    
    def start_log_stream(self) -> None:
        """Start streaming logs in background."""
        self.log_worker = self.run_worker(self.stream_logs())
    
    async def stream_logs(self) -> None:
        """Stream logs from Docker."""
        log_viewer = self.query_one("#log-viewer", LogViewer)
        async for line in stream_container_logs(self.stack_name):
            log_viewer.write(line)
```

### 6.4 Log Viewer Widget

A scrollable, filterable log viewer.

```python
from textual.widgets import RichLog, Input
from textual.containers import Vertical

class LogViewer(Vertical):
    """Scrollable log viewer with filtering."""
    
    def compose(self) -> ComposeResult:
        yield Input(placeholder="Filter logs...", id="log-filter")
        yield RichLog(id="log-output", highlight=True, markup=True)
    
    def write(self, line: str) -> None:
        filter_text = self.query_one("#log-filter", Input).value
        if not filter_text or filter_text.lower() in line.lower():
            self.query_one("#log-output", RichLog).write(line)
    
    def on_input_changed(self, event: Input.Changed) -> None:
        """Re-filter logs when filter changes."""
        # Would need to maintain log buffer and re-render
        pass
```

### 6.5 Backups Screen

Lists backups with restore functionality.

```python
class BackupsScreen(Screen):
    """Screen showing available backups."""
    
    BINDINGS = [
        Binding("r", "restore", "Restore"),
        Binding("n", "run_backup", "Run Backup Now"),
    ]
    
    def compose(self) -> ComposeResult:
        yield Container(
            Static("Backups", classes="title"),
            DataTable(id="backups-table"),
            id="backups-container"
        )
    
    def on_mount(self) -> None:
        table = self.query_one("#backups-table", DataTable)
        table.add_columns("Backup", "Type", "Size", "Created")
        self.refresh_data()
    
    def refresh_data(self) -> None:
        table = self.query_one("#backups-table", DataTable)
        table.clear()
        
        try:
            config = load_config()
            if config.backup:
                backups = list_backups(config.backup)
                for backup in backups:
                    table.add_row(
                        backup.name,
                        backup.type,
                        format_bytes(backup.size),
                        backup.created.strftime("%Y-%m-%d %H:%M"),
                    )
        except Exception as e:
            self.notify(f"Failed to load backups: {e}", severity="error")
    
    def action_restore(self) -> None:
        """Restore selected backup."""
        table = self.query_one("#backups-table", DataTable)
        row_key = table.cursor_row
        if row_key is not None:
            backup_name = table.get_cell(row_key, 0)
            self.app.push_screen(RestoreConfirmScreen(backup_name))
```

---

## 7. Core Algorithms

### 7.1 Stack Discovery

```python
from pathlib import Path
from dataclasses import dataclass
from typing import Optional

@dataclass
class StackInfo:
    config: Optional[StackConfig]
    path: Path
    valid: bool
    error: str = ""

def get_available_stacks() -> list[StackInfo]:
    """Find all stacks in the stacks/ directory."""
    stacks_dir = Path.cwd() / "stacks"
    
    if not stacks_dir.exists():
        raise SurekError("Folder 'stacks' not found in current working directory")
    
    results = []
    for config_path in stacks_dir.glob("**/surek.stack.yml"):
        try:
            config = load_stack_config(config_path)
            results.append(StackInfo(
                config=config,
                path=config_path,
                valid=True,
            ))
        except Exception as e:
            results.append(StackInfo(
                config=None,
                path=config_path,
                valid=False,
                error=str(e),
            ))
    
    return sorted(results, key=lambda s: str(s.path))

def get_stack_by_name(name: str) -> StackInfo:
    """Find a stack by name."""
    if not name:
        raise SurekError("Invalid stack name")
    
    for stack in get_available_stacks():
        if stack.valid and stack.config.name == name:
            return stack
    
    raise SurekError(f"Stack with name '{name}' not found")
```

### 7.2 Stack Deployment

```python
import shutil
from pathlib import Path

def deploy_stack(config: StackConfig, source_dir: Path, surek_config: SurekConfig) -> None:
    """Deploy a stack."""
    project_dir = get_stack_project_dir(config.name)
    
    # Clean existing project directory
    if project_dir.exists():
        shutil.rmtree(project_dir)
    project_dir.mkdir(parents=True)
    
    # Handle GitHub source
    if isinstance(config.source, GitHubSource):
        cached_commit = get_cached_commit(config.name)
        latest_commit = get_latest_commit(config.source, surek_config)
        
        if cached_commit == latest_commit:
            console.print(f"[dim]No changes detected, using cached version[/dim]")
            # Copy from cache instead of re-downloading
            copy_from_cache(config.name, project_dir)
        else:
            pull_github_repo(config.source, project_dir, surek_config)
            save_cached_commit(config.name, latest_commit)
    
    # Copy local files (overwrite GitHub files if present)
    copy_folder_recursive(source_dir, project_dir)
    
    # Find and transform compose file
    compose_file_path = project_dir / config.compose_file_path
    if not compose_file_path.exists():
        raise SurekError(f"Couldn't find compose file at {compose_file_path}")
    
    compose_spec = read_compose_file(compose_file_path)
    
    # System-specific transformation
    if config.name == "surek-system":
        compose_spec = transform_system_compose(compose_spec, surek_config)
    
    # General transformation
    transformed = transform_compose_file(compose_spec, config, surek_config)
    
    # Write transformed file
    patched_path = project_dir / "docker-compose.surek.yml"
    write_compose_file(patched_path, transformed)
    console.print(f"Saved patched compose file at {patched_path}")
    
    # Start containers
    start_stack(config)
```

### 7.3 GitHub Caching

```python
import json
from pathlib import Path

def get_cache_file() -> Path:
    return get_data_dir() / "github_cache.json"

def get_cached_commit(stack_name: str) -> Optional[str]:
    """Get the cached commit hash for a stack."""
    cache_file = get_cache_file()
    if not cache_file.exists():
        return None
    
    cache = json.loads(cache_file.read_text())
    return cache.get(stack_name, {}).get("commit")

def save_cached_commit(stack_name: str, commit: str) -> None:
    """Save the commit hash for a stack."""
    cache_file = get_cache_file()
    
    if cache_file.exists():
        cache = json.loads(cache_file.read_text())
    else:
        cache = {}
    
    cache[stack_name] = {
        "commit": commit,
        "updated_at": datetime.utcnow().isoformat(),
    }
    
    cache_file.write_text(json.dumps(cache, indent=2))

def get_latest_commit(source: GitHubSource, config: SurekConfig) -> str:
    """Get the latest commit hash from GitHub."""
    if not config.github:
        raise SurekError("GitHub PAT is required")
    
    headers = {"Authorization": f"token {config.github.pat}"}
    
    response = httpx.get(
        f"https://api.github.com/repos/{source.owner}/{source.repo}/commits/{source.ref}",
        headers=headers,
    )
    response.raise_for_status()
    
    return response.json()["sha"]
```

### 7.4 Compose File Transformation

```python
import copy
import bcrypt
from pathlib import Path

SUREK_NETWORK = "surek"
DEFAULT_LABELS = {"surek.managed": "true"}

def transform_compose_file(
    spec: dict,
    config: StackConfig,
    surek_config: SurekConfig
) -> dict:
    """Transform a Docker Compose specification for Surek."""
    spec = copy.deepcopy(spec)
    
    data_dir = get_data_dir()
    volumes_dir = data_dir / "volumes" / config.name
    folders_to_create: list[Path] = []
    
    # 1. Network injection
    if "networks" not in spec:
        spec["networks"] = {}
    
    spec["networks"][SUREK_NETWORK] = {
        "name": SUREK_NETWORK,
        "external": True,
    }
    
    # 2. Volume transformation
    if "volumes" in spec:
        for volume_name, volume_config in spec["volumes"].items():
            if volume_name in config.backup.exclude_volumes:
                continue
            
            # Skip pre-configured volumes
            if volume_config and len(volume_config) > 0:
                console.print(
                    f"[yellow]Warning: Volume {volume_name} is pre-configured. "
                    f"Skipping backup transformation.[/yellow]"
                )
                continue
            
            folder_path = volumes_dir / volume_name
            folders_to_create.append(folder_path)
            
            spec["volumes"][volume_name] = {
                "driver": "local",
                "driver_opts": {
                    "type": "none",
                    "o": "bind",
                    "device": str(folder_path),
                },
                "labels": DEFAULT_LABELS.copy(),
            }
    
    # 3. Public service labels
    for endpoint in config.public:
        service_name = endpoint.service_name
        port = endpoint.port
        
        if "services" not in spec or service_name not in spec["services"]:
            raise SurekError(
                f"Service '{service_name}' not defined in docker-compose config"
            )
        
        service = spec["services"][service_name]
        if "labels" not in service:
            service["labels"] = {}
        
        domain = expand_variables(endpoint.domain, surek_config)
        
        labels = {
            **DEFAULT_LABELS,
            "caddy": domain,
            "caddy.reverse_proxy": f"{{{{upstreams {port}}}}}",
        }
        
        # Development mode
        if os.environ.get("NODE_ENV") == "development":
            labels["caddy.tls"] = "internal"
        
        # Basic auth
        if endpoint.auth:
            auth_str = expand_variables(endpoint.auth, surek_config)
            user, password = auth_str.split(":")
            hashed = bcrypt.hashpw(password.encode(), bcrypt.gensalt(rounds=14))
            # Escape $ for Docker Compose
            escaped_hash = hashed.decode().replace("$", "$$")
            labels["caddy.basic_auth"] = ""
            labels[f"caddy.basic_auth.{user}"] = escaped_hash
        
        # Merge labels
        if isinstance(service["labels"], list):
            service["labels"].extend(
                f"{k}={json.dumps(v)}" for k, v in labels.items()
            )
        else:
            service["labels"].update(labels)
    
    # 4. Environment variable injection
    if config.env and "services" in spec:
        for service_name, service in spec["services"].items():
            container_env = config.env.by_container.get(service_name, [])
            shared_env = config.env.shared
            
            expanded_env = [
                expand_variables(e, surek_config)
                for e in shared_env + container_env
            ]
            
            if "environment" not in service:
                service["environment"] = []
            
            service["environment"] = merge_envs(
                service["environment"],
                expanded_env
            )
    
    # 5. Create volume directories
    for folder in folders_to_create:
        folder.mkdir(parents=True, exist_ok=True)
    
    # 6. Service network injection
    if "services" in spec:
        for service_name, service in spec["services"].items():
            # Skip if network_mode is set
            if "network_mode" in service:
                continue
            
            if "networks" not in service:
                service["networks"] = []
            
            if isinstance(service["networks"], list):
                service["networks"].append(SUREK_NETWORK)
            else:
                service["networks"][SUREK_NETWORK] = None
    
    return spec
```

### 7.5 Variable Expansion

```python
def expand_variables(value: str, config: SurekConfig) -> str:
    """Expand Surek template variables in a string."""
    result = value
    
    # Core variables
    replacements = {
        "<root>": config.root_domain,
        "<default_auth>": config.default_auth,
        "<default_user>": config.default_user,
        "<default_password>": config.default_password,
    }
    
    # Backup variables
    if config.backup:
        replacements.update({
            "<backup_password>": config.backup.password,
            "<backup_s3_endpoint>": config.backup.s3_endpoint,
            "<backup_s3_bucket>": config.backup.s3_bucket,
            "<backup_s3_access_key>": config.backup.s3_access_key,
            "<backup_s3_secret_key>": config.backup.s3_secret_key,
        })
    
    for var, val in replacements.items():
        result = result.replace(var, val)
    
    return result
```

### 7.6 Detailed Stack Status

```python
from dataclasses import dataclass
from typing import Optional

@dataclass
class ServiceHealth:
    name: str
    status: str  # "running", "exited", "paused", etc.
    health: Optional[str]  # "healthy", "unhealthy", "starting", None
    cpu_percent: float
    memory_bytes: int

@dataclass
class StackStatusDetailed:
    status_text: str
    services: list[ServiceHealth]
    health_details: list[str]
    health_summary: str
    cpu_percent: float
    memory_bytes: int

def get_stack_status_detailed(name: str) -> StackStatusDetailed:
    """Get detailed status for a stack including health and resources."""
    project_dir = get_stack_project_dir(name)
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
    
    docker = get_docker_client()
    
    # Get containers for this project
    containers = docker.containers.list(
        all=True,
        filters={"label": f"com.docker.compose.project={name}"}
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
    
    services = []
    total_cpu = 0.0
    total_memory = 0
    health_details = []
    
    for container in containers:
        # Get service name from labels
        service_name = container.labels.get(
            "com.docker.compose.service", 
            container.name
        )
        
        # Get health status
        health = None
        if "Health" in container.attrs.get("State", {}):
            health = container.attrs["State"]["Health"]["Status"]
        
        # Get resource usage
        try:
            stats = container.stats(stream=False)
            cpu_percent = calculate_cpu_percent(stats)
            memory_bytes = stats["memory_stats"].get("usage", 0)
        except Exception:
            cpu_percent = 0.0
            memory_bytes = 0
        
        services.append(ServiceHealth(
            name=service_name,
            status=container.status,
            health=health,
            cpu_percent=cpu_percent,
            memory_bytes=memory_bytes,
        ))
        
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
        status_text = f"✓ Running ({running}/{total})"
    
    # Health summary
    unhealthy = sum(1 for s in services if s.health == "unhealthy")
    if unhealthy > 0:
        health_summary = f"⚠ {unhealthy} unhealthy"
    elif all(s.health in ("healthy", None) for s in services):
        health_summary = "✓ healthy"
    else:
        health_summary = "starting..."
    
    return StackStatusDetailed(
        status_text=status_text,
        services=services,
        health_details=health_details,
        health_summary=health_summary,
        cpu_percent=total_cpu,
        memory_bytes=total_memory,
    )

def calculate_cpu_percent(stats: dict) -> float:
    """Calculate CPU percentage from Docker stats."""
    cpu_delta = (
        stats["cpu_stats"]["cpu_usage"]["total_usage"] -
        stats["precpu_stats"]["cpu_usage"]["total_usage"]
    )
    system_delta = (
        stats["cpu_stats"]["system_cpu_usage"] -
        stats["precpu_stats"]["system_cpu_usage"]
    )
    
    if system_delta > 0 and cpu_delta > 0:
        cpu_count = stats["cpu_stats"]["online_cpus"]
        return (cpu_delta / system_delta) * cpu_count * 100.0
    
    return 0.0
```

---

## 8. System Containers

### 8.1 System Stack Configuration

**File:** `resources/system/surek.stack.yml`

```yaml
name: surek-system
source:
  type: local
compose_file_path: ./docker-compose.yml
public:
  - domain: portainer.<root>
    target: portainer:9000
  - domain: netdata.<root>
    target: netdata:19999
    auth: <default_auth>
env:
  by_container:
    backup:
      - GPG_PASSPHRASE=<backup_password>
      - AWS_ENDPOINT=<backup_s3_endpoint>
      - AWS_S3_BUCKET_NAME=<backup_s3_bucket>
      - AWS_ACCESS_KEY_ID=<backup_s3_access_key>
      - AWS_SECRET_ACCESS_KEY=<backup_s3_secret_key>
```

### 8.2 System Compose Transformation

```python
def transform_system_compose(spec: dict, config: SurekConfig) -> dict:
    """Apply system-specific transformations."""
    spec = copy.deepcopy(spec)
    
    # Remove backup service if not configured
    if not config.backup and "services" in spec:
        spec["services"].pop("backup", None)
    
    # Remove portainer if disabled
    if not config.system_services.portainer and "services" in spec:
        spec["services"].pop("portainer", None)
        # Also remove from public endpoints during stack config loading
    
    # Remove netdata if disabled
    if not config.system_services.netdata and "services" in spec:
        spec["services"].pop("netdata", None)
    
    return spec
```

### 8.3 Docker Compose File

**File:** `resources/system/docker-compose.yml`

```yaml
version: "3.7"

services:
  caddy:
    image: lucaslorentz/caddy-docker-proxy:ci-alpine
    ports:
      - 80:80
      - 443:443
    volumes:
      - /var/run/docker.sock:/var/run/docker.sock
      - caddy_data:/data
    restart: unless-stopped

  portainer:
    image: portainer/portainer-ce:latest
    volumes:
      - portainer_data:/data
      - /var/run/docker.sock:/var/run/docker.sock
    restart: unless-stopped

  netdata:
    image: netdata/netdata
    pid: host
    restart: unless-stopped
    cap_add:
      - SYS_PTRACE
      - SYS_ADMIN
    security_opt:
      - apparmor:unconfined
    volumes:
      - netdata_config:/etc/netdata
      - netdata_lib:/var/lib/netdata
      - netdata_cache:/var/cache/netdata
      - /etc/passwd:/host/etc/passwd:ro
      - /etc/group:/host/etc/group:ro
      - /etc/localtime:/etc/localtime:ro
      - /proc:/host/proc:ro
      - /sys:/host/sys:ro
      - /etc/os-release:/host/etc/os-release:ro
      - /var/log:/host/var/log:ro
      - /var/run/docker.sock:/var/run/docker.sock:ro

  backup:
    image: offen/docker-volume-backup:latest
    restart: unless-stopped
    volumes:
      - ../../volumes:/backup:ro
      - ./backup-daily.env:/etc/dockervolumebackup/conf.d/backup-daily.env
      - ./backup-weekly.env:/etc/dockervolumebackup/conf.d/backup-weekly.env
      - ./backup-monthly.env:/etc/dockervolumebackup/conf.d/backup-monthly.env
      - /etc/timezone:/etc/timezone:ro
      - /etc/localtime:/etc/localtime:ro

volumes:
  caddy_data: {}
  portainer_data: {}
  netdata_config: {}
  netdata_lib: {}
  netdata_cache: {}
```

---

## 9. Backup System

### 9.1 S3 Operations

```python
import boto3
from dataclasses import dataclass
from datetime import datetime

@dataclass
class BackupInfo:
    name: str
    type: str  # "daily", "weekly", "monthly"
    size: int
    created: datetime

def get_s3_client(config: BackupConfig):
    """Create an S3 client for backup operations."""
    return boto3.client(
        "s3",
        endpoint_url=f"https://{config.s3_endpoint}",
        aws_access_key_id=config.s3_access_key,
        aws_secret_access_key=config.s3_secret_key,
    )

def list_backups(config: BackupConfig) -> list[BackupInfo]:
    """List all backups in S3."""
    s3 = get_s3_client(config)
    
    response = s3.list_objects_v2(Bucket=config.s3_bucket)
    
    backups = []
    for obj in response.get("Contents", []):
        name = obj["Key"]
        
        # Determine backup type from filename
        if name.startswith("daily-"):
            backup_type = "daily"
        elif name.startswith("weekly-"):
            backup_type = "weekly"
        elif name.startswith("monthly-"):
            backup_type = "monthly"
        else:
            backup_type = "unknown"
        
        backups.append(BackupInfo(
            name=name,
            type=backup_type,
            size=obj["Size"],
            created=obj["LastModified"],
        ))
    
    return sorted(backups, key=lambda b: b.created, reverse=True)
```

### 9.2 Failure Tracking and Notifications

Surek tracks backup failures for observability. In v2.0, failures are logged to a local file. Actual notification delivery (webhook, email, Telegram) will be implemented in a future release.

**Failure Log Location:** `surek-data/backup_failures.json`

```python
from datetime import datetime
from pathlib import Path
import json

@dataclass
class BackupFailure:
    timestamp: str
    backup_type: str  # "daily", "weekly", "monthly"
    error: str
    notified: bool = False  # Reserved for future notification tracking

def get_failure_log_path() -> Path:
    return get_data_dir() / "backup_failures.json"

def load_failures() -> list[BackupFailure]:
    """Load backup failure history."""
    path = get_failure_log_path()
    if not path.exists():
        return []
    
    data = json.loads(path.read_text())
    return [BackupFailure(**f) for f in data]

def record_backup_failure(backup_type: str, error: str) -> None:
    """Record a backup failure for tracking."""
    failures = load_failures()
    
    failure = BackupFailure(
        timestamp=datetime.utcnow().isoformat(),
        backup_type=backup_type,
        error=error,
        notified=False,
    )
    failures.append(failure)
    
    # Keep last 100 failures
    failures = failures[-100:]
    
    path = get_failure_log_path()
    path.write_text(json.dumps([f.__dict__ for f in failures], indent=2))
    
    console.print(f"[red]Backup failed: {error}[/red]")
    
    # TODO: In future versions, send actual notifications here
    # if config.notifications:
    #     send_webhook(config.notifications.webhook_url, error)
    #     send_email(config.notifications.email, error)
    #     send_telegram(config.notifications.telegram_chat_id, error)

def get_recent_failures(limit: int = 10) -> list[BackupFailure]:
    """Get recent backup failures for display."""
    failures = load_failures()
    return failures[-limit:]
```

**Usage in backup operations:**

```python
try:
    run_backup(backup_type)
except Exception as e:
    record_backup_failure(backup_type, str(e))
    raise
```

### 9.3 Backup Schedule Files

**File:** `resources/system/backup-daily.env`
```
BACKUP_FILENAME="daily-backup-%Y-%m-%dT%H-%M-%S.tar.gz"
BACKUP_CRON_EXPRESSION="0 2 * * *"
BACKUP_PRUNING_PREFIX="daily-backup-"
BACKUP_RETENTION_DAYS="7"
```

**File:** `resources/system/backup-weekly.env`
```
BACKUP_FILENAME="weekly-backup-%Y-%m-%dT%H-%M-%S.tar.gz"
BACKUP_CRON_EXPRESSION="0 3 * * 1"
BACKUP_PRUNING_PREFIX="weekly-backup-"
BACKUP_RETENTION_DAYS="60"
```

**File:** `resources/system/backup-monthly.env`
```
BACKUP_FILENAME="monthly-backup-%Y-%m-%dT%H-%M-%S.tar.gz"
BACKUP_CRON_EXPRESSION="0 4 1 * *"
BACKUP_PRUNING_PREFIX="monthly-backup-"
BACKUP_RETENTION_DAYS="730"
```

---

## 10. Docker Integration

### 10.1 Network Management

Surek requires a shared Docker network for all containers to communicate. This network is **not created automatically by Docker** - Surek must explicitly create it.

**Network Name:** `surek`

**Network Configuration:**
```python
SUREK_NETWORK = "surek"
DEFAULT_LABELS = {"surek.managed": "true"}
```

**Creation Logic:**

```python
def ensure_surek_network() -> None:
    """Ensure the Surek Docker network exists."""
    docker = get_docker_client()
    
    # Check if network already exists
    existing = docker.networks.list(names=[SUREK_NETWORK])
    
    if not existing:
        console.print(f"Creating Docker network '{SUREK_NETWORK}'")
        docker.networks.create(
            name=SUREK_NETWORK,
            driver="bridge",
            labels=DEFAULT_LABELS,
        )
```

**When Network is Created:**
- During `surek system start` (before deploying system containers)

**Network Usage in Compose Files:**

When transforming compose files, Surek adds the network as external (see Section 7.4):

```yaml
networks:
  surek:
    name: surek
    external: true  # References the pre-existing network
```

The `external: true` flag tells Docker Compose to use an existing network rather than create a new one. If the network doesn't exist, Docker Compose will fail with an error.

**Important:** Users must run `surek system start` before deploying any stacks. This command creates the network. If a user tries to deploy a stack without the network existing, Docker Compose will fail.

### 10.2 Docker Client

```python
import docker
from docker.errors import DockerException

_docker_client: Optional[docker.DockerClient] = None

def get_docker_client() -> docker.DockerClient:
    """Get or create Docker client singleton."""
    global _docker_client
    
    if _docker_client is None:
        try:
            _docker_client = docker.from_env()
            _docker_client.ping()
        except DockerException as e:
            raise SurekError(f"Failed to connect to Docker: {e}")
    
    return _docker_client
```

### 10.3 Docker Compose Execution

```python
import subprocess
from pathlib import Path

def run_docker_compose(
    compose_file: Path,
    project_dir: Path,
    command: str,
    args: list[str] = None,
    capture_output: bool = False,
) -> str:
    """Execute a docker compose command."""
    cmd = [
        "docker", "compose",
        "--file", str(compose_file),
        "--project-directory", str(project_dir),
        command,
    ]
    
    if args:
        cmd.extend(args)
    
    console.print(f"[dim]$ {' '.join(cmd)}[/dim]")
    
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
        raise SurekError(f"Docker Compose command failed: {error_msg}")
```

### 10.4 Log Streaming

```python
async def stream_container_logs(
    stack_name: str,
    service: Optional[str] = None,
) -> AsyncGenerator[str, None]:
    """Stream logs from containers."""
    docker = get_docker_client()
    
    filters = {"label": f"com.docker.compose.project={stack_name}"}
    if service:
        filters["label"].append(f"com.docker.compose.service={service}")
    
    containers = docker.containers.list(filters=filters)
    
    # Stream logs from all matching containers
    for container in containers:
        for line in container.logs(stream=True, follow=True, tail=100):
            service_name = container.labels.get(
                "com.docker.compose.service",
                container.name
            )
            yield f"[{service_name}] {line.decode().strip()}"
```

---

## 11. Error Handling

### 11.1 Exception Hierarchy

```python
class SurekError(Exception):
    """Base exception for Surek errors."""
    pass

class SurekConfigError(SurekError):
    """Configuration-related errors."""
    pass

class StackConfigError(SurekError):
    """Stack configuration errors."""
    pass

class DockerError(SurekError):
    """Docker-related errors."""
    pass

class BackupError(SurekError):
    """Backup operation errors."""
    pass

class GitHubError(SurekError):
    """GitHub API errors."""
    pass
```

### 11.2 Error Messages

| Condition | Error Message |
|-----------|---------------|
| Config not found | `"Config file not found. Make sure you have surek.yml in current working directory"` |
| Stacks folder missing | `"Folder 'stacks' not found in current working directory"` |
| Stack not found | `"Stack with name '{name}' not found"` |
| Invalid stack name | `"Invalid stack name"` |
| Compose file missing | `"Couldn't find compose file at {path}"` |
| Service not in compose | `"Service '{name}' not defined in docker-compose config"` |
| GitHub PAT missing | `"GitHub PAT is required"` |
| Docker connection failed | `"Failed to connect to Docker: {error}"` |
| Docker command failed | `"Docker Compose command failed: {error}"` |
| Backup not configured | `"Backup is not configured in surek.yml"` |
| Environment variable missing | `"Environment variable '{name}' is not set"` |

### 11.3 CLI Error Handler

```python
from rich.console import Console

console = Console()

def handle_error(e: Exception) -> None:
    """Handle exceptions in CLI commands."""
    if isinstance(e, SurekError):
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)
    else:
        console.print(f"[red]Unexpected error:[/red] {e}")
        console.print_exception()
        raise typer.Exit(1)
```

---

## 12. Backward Compatibility

### 12.1 Configuration Compatibility

Surek v2 must accept all valid v1 configuration files without modification.

**Preserved:**
- `surek.yml` schema (all existing fields)
- `surek.stack.yml` schema (all existing fields)
- Variable syntax (`<root>`, `<default_auth>`, etc.)
- File locations and naming

**Added (v2 only):**
- `${ENV_VAR}` syntax for environment variables
- `system_services` section in `surek.yml`
- `notifications` section in `surek.yml`

### 12.2 Data Directory Compatibility

The `surek-data/` directory structure remains unchanged:

```
surek-data/
├── projects/
│   └── <stack-name>/
│       └── docker-compose.surek.yml
├── volumes/
│   └── <stack-name>/
│       └── <volume-name>/
└── github_cache.json  # New in v2
```

### 12.3 Docker Labels Compatibility

All Docker labels remain unchanged:
- `surek.managed: "true"`
- Caddy labels (`caddy`, `caddy.reverse_proxy`, `caddy.basic_auth.*`)

### 12.4 Network Compatibility

The Docker network name remains `surek`.

### 12.5 Testing Compatibility

Include integration tests that:
1. Load v1 example configurations
2. Verify they parse without errors
3. Verify transformed compose files match expected output
4. Verify deployed stacks function correctly
