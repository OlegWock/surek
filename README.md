# Surek

Surek is a Docker Compose orchestration tool for self-hosted services.

It manages Caddy reverse proxy for your containers with automatic HTTPS, backs up Docker volumes to S3-compatible storage, and includes Portainer and Netdata for container management and server monitoring.

## Features

- **Reverse proxy**: Automatic Caddy configuration with Let's Encrypt HTTPS
- **Volume backups**: Scheduled backups to S3-compatible storage with encryption
- **Shared networking**: All stacks on a common network for easy inter-service communication
- **Template variables**: Use `<root>`, `<default_auth>`, etc. in stack configs
- **Environment variables**: Support for `${VAR}` syntax in all config files
- **Interactive TUI**: Terminal UI for managing stacks and backups
- **GitHub integration**: Pull stacks from public or private repositories

## Installation

Surek requires Python 3.12+, Docker with Compose plugin, and a domain pointed to your server.

```bash
# Using pip
pip install surek

# Using uv (recommended)
uv tool install surek
```

If your Docker requires `sudo`, install and run Surek with `sudo` as well.

## Quick Start

```bash
# Initialize a new project (creates surek.yml)
surek init

# Create a new stack interactively
surek new

# Start system containers (Caddy, Portainer, Netdata)
surek start system

# Deploy a stack
surek deploy my-stack

# Check status
surek status

# Launch interactive TUI
surek
```

## Configuration

### Main Config (`surek.yml`)

Create this file in your project directory:

```yaml
# Required: Root domain for all services
root_domain: example.com

# Required: Default auth in "user:password" format
default_auth: admin:${SUREK_PASSWORD}

# Optional: S3 backup configuration
backup:
  password: ${BACKUP_PASSWORD}
  s3_endpoint: s3.example.com
  s3_bucket: my-backups
  s3_access_key: ${AWS_ACCESS_KEY}
  s3_secret_key: ${AWS_SECRET_KEY}

# Optional: GitHub access for private repos
github:
  pat: ${GITHUB_PAT}

# Optional: Enable/disable system services
system_services:
  portainer: true
  netdata: true
```

### Stack Config (`stacks/<name>/surek.stack.yml`)

```yaml
name: my-app

# Source: local files or GitHub
source:
  type: local
  # OR
  # type: github
  # slug: owner/repo#branch

# Path to compose file (default: ./docker-compose.yml)
compose_file_path: ./docker-compose.yml

# Public endpoints for reverse proxy
public:
  - domain: app.<root>
    target: myapp:8080
    auth: <default_auth>  # Optional: basic auth

# Environment variables
env:
  shared:
    - TZ=UTC
  by_container:
    myapp:
      - DATABASE_URL=postgres://...

# Backup settings
backup:
  exclude_volumes:
    - cache_data
```

## Commands

| Command | Description |
|---------|-------------|
| `surek` | Launch interactive TUI |
| `surek init` | Create surek.yml interactively |
| `surek new` | Create a new stack interactively |
| `surek schema` | Generate JSON schemas for editor autocompletion |
| `surek deploy <stack>` | Deploy a stack (use `system` for system containers) |
| `surek start <stack>` | Start an already deployed stack |
| `surek stop <stack>` | Stop a running stack |
| `surek status` | Show status of all stacks |
| `surek status --stats` | Include CPU/memory usage (slower) |
| `surek info <stack>` | Show detailed stack information |
| `surek logs <stack> [service]` | View stack logs (`-f` to follow) |
| `surek validate <path>` | Validate a stack config |
| `surek reset <stack>` | Stop stack and delete all its data |
| `surek prune` | Remove unused Docker resources |
| `surek prune --volumes` | Also remove unused volumes |
| `surek backup list` | List all backups |
| `surek backup run` | Trigger immediate backup |
| `surek backup restore` | Restore from backup |

**Note:** The `system` stack name is reserved for Surek's system containers (Caddy, Portainer, Netdata, Backup). Use `surek start system`, `surek stop system`, etc.

## Template Variables

Use these in stack configs (`public.domain`, `public.auth`, `env`):

| Variable | Description |
|----------|-------------|
| `<root>` | Root domain from surek.yml |
| `<default_auth>` | Default auth (user:password) |
| `<default_user>` | Username from default_auth |
| `<default_password>` | Password from default_auth |
| `<backup_password>` | Backup encryption password |
| `<backup_s3_endpoint>` | S3 endpoint URL |
| `<backup_s3_bucket>` | S3 bucket name |
| `<backup_s3_access_key>` | S3 access key |
| `<backup_s3_secret_key>` | S3 secret key |

## Directory Structure

```
project/
├── surek.yml              # Main configuration
├── stacks/                # User-defined stacks
│   └── my-app/
│       ├── surek.stack.yml
│       └── docker-compose.yml
└── surek-data/            # Generated (add to .gitignore)
    ├── projects/          # Deployed stack files
    └── volumes/           # Bound volumes for backup
```

## Writing Compose Files

When writing Docker Compose files for Surek:

- **No port exposure needed**: Caddy handles routing via labels
- **Use named volumes**: For backup support (don't set driver options)
- **Unique service names**: All stacks share a network, avoid name collisions

## System Services

| Service | Purpose | Domain |
|---------|---------|--------|
| Caddy | Reverse proxy with auto-HTTPS | - |
| Portainer | Container management UI | portainer.\<root\> |
| Netdata | Server monitoring | netdata.\<root\> |
| Backup | Scheduled S3 backups | - |

Visit `portainer.<root>` within 5 minutes of first start to complete setup.

## Examples

See the [example-stacks](example-stacks/) folder for sample configurations.

## LLM Integration

For AI assistants, run `surek --help-llm` to get complete documentation.

## Backward Compatibility

Surek v2 is fully backward compatible with v1 configuration files. All existing `surek.yml` and `surek.stack.yml` files work without modification.

## License

GPL-3.0-or-later
