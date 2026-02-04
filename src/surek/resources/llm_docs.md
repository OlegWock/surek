# Surek v2 Documentation

Complete documentation for Surek, the Docker Compose orchestration tool for self-hosted services.

## Overview

Surek simplifies deploying and managing self-hosted services by automating:
- Reverse proxy configuration via Caddy with automatic HTTPS
- Volume management with bind mounts for backup
- Shared networking across all stacks
- Environment variable injection with template variables
- Automated backups to S3-compatible storage
- Interactive TUI and CLI interfaces

## Installation

```bash
# Using pip
pip install surek

# Using uv
uv add surek
```

Requirements:
- Python 3.12+
- Docker Engine with Compose plugin
- Domain pointed to server (for HTTPS)

## Quick Start

```bash
# Initialize a new Surek project
surek init

# Create a new stack
surek new

# Deploy system containers (Caddy, Portainer, Netdata)
surek start system

# Deploy a stack
surek deploy my-stack

# Check status
surek status

# Launch interactive TUI
surek
```

## Commands

### Core Commands

| Command | Description |
|---------|-------------|
| `surek` | Launch interactive TUI |
| `surek deploy <stack>` | Deploy a stack (pull sources, transform compose, start) |
| `surek deploy <stack> --pull` | Deploy and force re-pull sources and Docker images |
| `surek start <stack>` | Start an already deployed stack |
| `surek stop <stack>` | Stop a running stack |
| `surek status` | Show status of all stacks with health |
| `surek status --stats` | Include CPU/memory usage (slower) |
| `surek info <stack>` | Show detailed stack information |
| `surek logs <stack> [service]` | View logs for stack or service (`-f` to follow) |
| `surek validate <path>` | Validate a stack configuration file |
| `surek reset <stack>` | Stop stack and delete all its data (volumes, project files) |
| `surek prune` | Remove unused Docker resources (containers, networks, images) |
| `surek prune --volumes` | Also remove unused Docker volumes and orphan volume folders |

### System Stack

The `system` stack name is reserved for Surek's system containers. Use it like any other stack:

| Command | Description |
|---------|-------------|
| `surek start system` | Create Docker network and start system containers |
| `surek stop system` | Stop system containers |
| `surek deploy system` | Redeploy system containers |
| `surek info system` | Show system container details |
| `surek logs system` | View system container logs |

**Note:** `surek reset system` is not allowed. Use `surek stop system` instead.

### Backup Commands

| Command | Description |
|---------|-------------|
| `surek backup` | List all backups (alias for `backup list`) |
| `surek backup list` | List all backups in S3 |
| `surek backup run` | Trigger immediate backup |
| `surek backup restore` | Restore from backup (interactive or with --id) |

### Setup Commands

| Command | Description |
|---------|-------------|
| `surek init` | Interactive wizard to create surek.yml |
| `surek init --git-only` | Only add surek-data to .gitignore |
| `surek new` | Interactive wizard to create a new stack |
| `surek schema` | Generate JSON schemas for editor autocompletion |

### Options

| Option | Description |
|--------|-------------|
| `--version, -v` | Show version |
| `--help-llm` | Print this documentation |
| `--help` | Show help |

## Configuration Files

### Main Configuration (`surek.yml`)

Location: Current working directory

```yaml
# Required: Root domain for all services
root_domain: example.com

# Required: Default auth in "user:password" format
default_auth: admin:${SUREK_PASSWORD}

# Optional: S3 backup configuration
backup:
  password: ${BACKUP_PASSWORD}      # GPG encryption password
  s3_endpoint: s3.example.com       # S3 endpoint URL
  s3_bucket: my-backups             # Bucket name
  s3_access_key: ${AWS_ACCESS_KEY}
  s3_secret_key: ${AWS_SECRET_KEY}

# Optional: GitHub access for private repos
github:
  pat: ${GITHUB_PAT}

# Optional: System service configuration
system_services:
  portainer: true   # Enable/disable Portainer
  netdata: true     # Enable/disable Netdata
```

### Stack Configuration (`surek.stack.yml`)

Location: `stacks/<stack-name>/surek.stack.yml`

```yaml
# Required: Unique stack name (cannot be 'system' or 'surek-system')
name: my-stack

# Required: Source of stack files
source:
  type: local  # Files in same directory
  # OR
  type: github
  slug: owner/repo#branch  # Format: owner/repo or owner/repo#ref

# Optional: Path to compose file (default: ./docker-compose.yml)
compose_file_path: ./docker-compose.yml

# Optional: Public endpoints for reverse proxy
public:
  - domain: app.<root>           # Domain (supports variables)
    target: myapp:8080           # service:port
    auth: <default_auth>         # Optional: basic auth

# Optional: Environment variables
env:
  shared:                        # Added to all services
    - TZ=UTC
  by_container:                  # Per-service variables
    myapp:
      - DATABASE_URL=postgres://...

# Optional: Backup exclusion
backup:
  exclude_volumes:
    - cache_data                 # Volumes to skip for backup
```

## Template Variables

Use these in `surek.stack.yml` (in `public.domain`, `public.auth`, `env` sections) and in Docker Compose files:

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

## Environment Variables

Use `${VAR_NAME}` or `${VAR_NAME:-default}` syntax in any configuration file:

```yaml
default_auth: admin:${SUREK_PASSWORD}
backup:
  password: ${BACKUP_ENCRYPTION_KEY:-default_password}
```

## Directory Structure

```
project/
├── surek.yml              # Main configuration
├── surek.config.schema.json  # Generated schema for surek.yml
├── surek.stack.schema.json   # Generated schema for stack configs
├── stacks/                # User-defined stacks
│   └── my-app/
│       ├── surek.stack.yml
│       ├── docker-compose.yml
│       └── ...
└── surek-data/            # Generated at runtime (gitignore this)
    ├── projects/          # Deployed stack files
    │   └── my-app/
    │       └── docker-compose.surek.yml
    └── volumes/           # Bound volumes for backup
        └── my-app/
            └── data/
```

## System Containers

Surek manages these system services:

| Service | Purpose | Domain |
|---------|---------|--------|
| Caddy | Reverse proxy with auto-HTTPS | - |
| Portainer | Container management UI | portainer.<root> |
| Netdata | Server monitoring | netdata.<root> |
| Backup | Automated S3 backups | - |

### Backup Schedule

| Type | Schedule | Retention |
|------|----------|-----------|
| Daily | 2:00 AM | 7 days |
| Weekly | 3:00 AM Monday | 60 days |
| Monthly | 4:00 AM 1st | 730 days |
| Manual | On-demand only | 3650 days (~10 years) |

Note: `surek backup run` creates a "manual" backup with long retention. Scheduled backups (daily/weekly/monthly) run automatically.

## How Deployment Works

When you run `surek deploy <stack>`:

1. **Source Resolution**: Downloads from GitHub (if configured) or uses local files
2. **File Merging**: Copies stack files to project directory
3. **Compose Transformation**:
   - Expands template variables (`<root>`, etc.) and env variables (`${VAR}`)
   - Adds `surek` network to all services
   - Converts volumes to bind mounts for backup
   - Adds Caddy labels for reverse proxy
   - Injects environment variables
   - Hashes passwords for basic auth
4. **Container Startup**: Runs `docker compose up -d --build` (with `--pull always` if `--pull` flag is used)

## TUI Keyboard Shortcuts

### Main Screen

| Key | Action |
|-----|--------|
| `Tab` | Switch between Stacks/Backups tabs |
| `r` | Refresh data |
| `d` | Deploy selected stack |
| `s` | Start selected stack |
| `x` | Stop selected stack |
| `i` / `Enter` / `→` | Show stack info |
| `b` | Run backup (Backups tab) |
| `q` | Quit |

### Stack Info Screen

| Key | Action |
|-----|--------|
| `Esc` / `q` | Go back |
| `r` | Refresh data |
| `l` | Toggle logs visibility |
| `f` | Toggle log following mode |

## Troubleshooting

### Docker connection issues
Ensure Docker is running and your user has permission to access the Docker socket.

### Network not found
Run `surek start system` to create the Surek network before deploying stacks.

### Certificate issues
Caddy automatically provisions Let's Encrypt certificates. Ensure ports 80 and 443 are open and your domain points to the server.

### Backup failures
Check `surek-data/backup_failures.json` for error details. Ensure S3 credentials are correct and the bucket exists.

## Reserved Names

The following stack names are reserved and cannot be used for user stacks:
- `system`
- `surek-system`

## Backward Compatibility

Surek v2 is backward compatible with v1 configuration files. All existing `surek.yml` and `surek.stack.yml` files work without modification.

New v2 features:
- `${ENV_VAR}` and `${ENV_VAR:-default}` syntax for environment variables
- Variables expanded in Docker Compose files
- `system_services` section to disable Portainer/Netdata
- Interactive TUI with stack info screen
- `surek init`, `surek new`, `surek schema` commands
- `surek info`, `surek logs`, `surek reset`, `surek prune` commands
- Backup listing and restore commands
- Shell completion for commands and stack names

## License

GPL-3.0-or-later
