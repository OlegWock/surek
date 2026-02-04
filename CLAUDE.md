# Surek - Project Guide

Surek is a Docker Compose orchestration tool for self-hosted services. It manages Caddy reverse proxy, volume backups to S3, and system services (Portainer, Netdata).

## Development

```bash
# Install dependencies
uv sync

# Run tests
uv run pytest

# Type checking
uv run mypy src/surek

# Linting
uv run ruff check src/surek

# Run the CLI (development)
uv run surek
```

## User Flow

A typical user journey from idea to deployed service:

1. **Initialize project**: `surek init` creates `surek.yml` with root domain, auth, and optional S3 backup config
2. **Create stack**: `surek new` scaffolds a new stack in `stacks/<name>/` with `surek.stack.yml` and `docker-compose.yml`
3. **Configure stack**: Edit `surek.stack.yml` to define public endpoints, environment variables, and backup settings
4. **Start system**: `surek start system` launches Caddy (reverse proxy), Portainer, and Netdata
5. **Deploy stack**: `surek deploy <stack>` pulls sources, transforms compose file, and starts containers
6. **Manage**: Use `surek status`, `surek logs`, `surek info` for monitoring; `surek backup` for backups
7. **Stop/Reset**: `surek stop <stack>` stops containers (`surek start <stack>` to start again); `surek reset <stack>` stops and deletes all data like volumes and project files (will require redeploy to start stack again).

### CLI vs TUI

- **CLI** (`surek <command>`): For scripting, automation, CI/CD, and one-off operations. Full feature set.
- **TUI** (`surek` with no args): Interactive dashboard for monitoring and quick actions. Shows stack status, logs, and allows deploy/start/stop with keyboard shortcuts. Subset of CLI features focused on daily operations.

## Key Concepts

### Deployment Pipeline

When `surek deploy <stack>` runs:
1. Download from GitHub if `source.type: github` (cached by commit hash)
2. Copy stack files to `surek-data/projects/<name>/`
3. Transform compose file:
   - Expand template variables (`<root>`, `<default_auth>`, etc.)
   - Expand env variables (`${VAR}`, `${VAR:-default}`)
   - Add `surek` network to all services
   - Convert named volumes to bind mounts for backup support
   - Add Caddy labels for reverse proxy routing
4. Write transformed file as `docker-compose.surek.yml`
5. Run `docker compose up -d --build`

### Configuration Files

- `surek.yml` - Main config (root_domain, default_auth, backup settings, github PAT)
- `stacks/<name>/surek.stack.yml` - Stack config (name, source, public endpoints, env)
- `surek-data/` - Runtime data (generated compose files, volume bind mounts)

### System Stack

The "system" stack is reserved for Surek's infrastructure:
- Caddy (reverse proxy with auto-HTTPS)
- Portainer (container management UI)
- Netdata (server monitoring)
- Backup container (scheduled S3 backups)

Defined in `src/surek/resources/system/`. Cannot be reset, only stopped.

## Code Conventions

- Python 3.12+ with type hints
- Pydantic for config validation
- Typer for CLI, Textual for TUI, Rich for console output
- Use `SurekError` for user-facing errors
- Commit messages: `feat:`, `fix:`, `docs:`, `refactor:`

## Documentation

- `README.md` - User-facing documentation
- `src/surek/resources/llm_docs.md` - Detailed docs (output of `--help-llm`)

Keep both in sync when adding/changing commands.
