# Surek

Surek is a Docker Compose orchestration tool for self-hosted services.

It manages Caddy reverse proxy for your containers with automatic HTTPS, backs up Docker volumes to S3-compatible storage, and includes Portainer and Netdata for container management and server monitoring.

## Features

- **Reverse proxy**: Automatic Caddy configuration with Let's Encrypt HTTPS
- **Volume backups**: Scheduled backups to S3-compatible storage with encryption
- **Shared networking**: All stacks on a common network for easy inter-service communication
- **Interactive TUI**: Terminal UI for managing stacks and backups
- **GitHub integration**: Pull stacks from public or private repositories

## Installation

Surek requires Python 3.12+, Docker with Compose plugin, and a domain pointed to your server.

```bash
# Using uv (recommended)
uv tool install surek

# Using pip
pip install surek
```

If your Docker requires `sudo`, install and run Surek with `sudo` as well.

## Concepts

### How Surek Works

Surek acts as a layer on top of Docker Compose. Main entity in Surek is "stack". Stack is a collection of related services. Each stack lives in its own directory under `stacks/`.

Minimally, stack consist of config file `surek.stack.yml` which describes where files should be pulled from (GitHub or local filesystem), which services should be exposed and on which subdomains, what volumes should be included or excluded in backup.

Another important piece is `docker-compose.yml`. If you're pulling project from GitHub and it already has `docker-compose.yml` in the repository (and you're happy with configuration in it), you can use it. Surek allows you to pass environment variables to containers directly in stack config, but if you need bigger customization you'll need to write your own `docker-compose.yml`.

Good news is: you can write your compose file as you used to. Surek doesn't require any special format except couple of conventions (see below).

Surek then will use stack config and `docker-compose.yml` to deploy described services according to config and expose them on pre-defined subdomains, and will take care of backup.

### System Stack

Surek includes a special **system stack** that provides core infrastructure:

- **Caddy** - Reverse proxy with automatic HTTPS
- **Portainer** - Web UI for container management (optional)
- **Netdata** - Server monitoring dashboard (optional)
- **Backup** - Scheduled volume backups to S3 (if configured)

You'll need to start the system stack before deploying your own stacks.

## Quick Start

Surek works great with LLM agents. So if you'd prefer to outsource the work to them, here is prompt template for you. Just add to it what you want to deploy.

```plaintext
Deploy <you service name and details> using `surek`. 

Surek is a Docker Compose orchestration tool for self-hosted services. Run `surek --help-readme` to get quickstart documentation or `surek --help-llm` to get full documentation. Check whether current folder is already initialized as Surek project. Initialize if not. If you require additional data from me (like root domain) —pause and ask. Then create new stack and configure it according to deployed service. Make no mistake. 
```

You can make your favorite LLM agent do the work for you. Agents can get complete Surek documentation by running `surek --help-llm`. Just tell it what you want to deploy and let metal head figure out the rest. Here is prompt template for you.


Initialize a new Surek project. This creates `surek.yml` where you'll configure your root domain, default credentials, and optional backup settings.

```bash
surek init
```

If you need to edit this configuration later, just edit `surek.yml` file. Now start the system stack. This launches Caddy (reverse proxy), Portainer, and Netdata. Required before deploying your own stacks.

```bash
surek start system
```

**Visit `portainer.<your domain>` within 5 minutes after first start to complete setup or it will lock you out and require removing volume and re-installing it.**

Next step is to create your first stack. You can use interactive wizard to prefil basic info. This scaffolds a stack directory with `surek.stack.yml` and optionally a `docker-compose.yml`.

```bash
surek new
```

Or you can manually create the folder `stacks/my-stack` and `surek.stack.yml` inside it.

After configuring your stack, deploy it. This pulls sources (if stack source is GitHub), transforms the compose file, and starts containers. 

Content of stack folder will be available to be used in your `docker-compose.yml`. You can use this to provide additional files that can be used by stack (e.g. service-specific configuration files). For stacks pulled from GitHub, content of stack folder will be recursively merged with repository content. You can use this to provide additional files or override existing files in the repository.

```bash
surek deploy my-stack
```

If your stack exposes any public services, you can now visit respective subdomain and see your service running.

Check the status of all stacks, or launch the interactive TUI for a dashboard view.

```bash
surek status

# Or launch TUI
surek
```

## Configuration schemas

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
| `surek deploy <stack> --pull` | Deploy and force re-pull sources and Docker images |
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

Use these in stack configs (e.g. in `public.domain`, `public.auth`, `env`) or `docker-compose.yml`:

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

1. **Use named volumes**: Surek can reliably backup only named volumes without additional configuration (like custom driver). Bind mounts or volumes with custom configuration will still work, but won't be backed up.

2. **Unique service names**: since all stacks share same network, each of services in your `docker-compose.yml` have to have unique name. For example, if you have two separate web apps both of which use Postgres, and you want to use separate Postgres instance for each, you have to give each of them unique name, they can't both be `postgres`. You can name them something like `postgres-foo` and `postgres-bar`.

3. **No port exposure needed**: Caddy will route incoming traffic directly through shared network, so there is no need to expose ports from container (though doing that won't brake anything either).

## Examples

See the [example-stacks](example-stacks/) folder for sample configurations.

## LLM Integration

For AI assistants, run `surek --help-llm` to get complete documentation.

## Backward Compatibility

Surek v2 is fully backward compatible with v1 configuration files. All existing `surek.yml` and `surek.stack.yml` files work without modification. Source code for v1 can be found in `v1` branch.