# Surek Architecture

This document describes the main features of Surek and how it works under the hood.

## Overview

Surek is an orchestration layer built on top of Docker Compose. It simplifies deploying and managing self-hosted services by automating:

- Reverse proxy configuration (Caddy)
- Volume management and backups
- Networking between services
- Environment variable injection

## Core Concepts

### Stacks

A **stack** is a collection of related services defined by a `surek.stack.yml` configuration file. Stacks are stored in the `stacks/` directory and can source their Docker Compose files locally or from GitHub.

### System Containers

Surek manages a set of system containers that provide infrastructure:

| Service | Purpose |
|---------|---------|
| **Caddy** | Reverse proxy with automatic HTTPS and Docker label-based configuration |
| **Portainer** | Web UI for container management |
| **Netdata** | Real-time server monitoring |
| **Backup** | Automated volume backups to S3-compatible storage (optional) |

### Data Directory

All Surek-managed data is stored in `surek-data/` within your working directory:

```
surek-data/
├── projects/           # Deployed stack files
│   └── <stack-name>/
│       ├── docker-compose.surek.yml  # Transformed compose file
│       └── ...                        # Other stack files
└── volumes/            # Bound volumes for backup
    └── <stack-name>/
        └── <volume-name>/
```

## How Deployment Works

When you run `surek deploy <stack-name>`, Surek executes the following pipeline:

### 1. Source Resolution

```
┌─────────────────────────────────────────────────────────────┐
│  Source: local                    Source: github            │
│  ─────────────────                ──────────────────────    │
│  Files are already in             Downloads repo as zip     │
│  stacks/<stack>/                  from GitHub API using     │
│                                   configured PAT            │
└─────────────────────────────────────────────────────────────┘
```

For GitHub sources, Surek:
- Parses the slug format: `owner/repo#ref` (ref defaults to HEAD)
- Uses Octokit to download the repository as a zipball
- Unpacks into the project directory

### 2. File Merging

After source resolution, Surek copies all files from the stack's source directory into the project directory, **overwriting existing files**. This allows you to customize GitHub-sourced stacks by placing override files in your local stack folder.

### 3. Compose File Transformation

This is the core of Surek's functionality. The original `docker-compose.yml` is transformed into `docker-compose.surek.yml` with several modifications:

#### Network Injection

All services are connected to a shared `surek` network:

```yaml
# Added to all services (unless network_mode is set)
networks:
  - surek

# Added to networks section
networks:
  surek:
    name: surek
    external: true
```

This enables inter-service communication across all stacks.

#### Volume Binding

Named volumes without custom configuration are converted to local bind mounts:

```yaml
# Original
volumes:
  my_data: {}

# Transformed
volumes:
  my_data:
    driver: local
    driver_opts:
      type: none
      o: bind
      device: /path/to/surek-data/volumes/<stack>/my_data
    labels:
      surek.managed: 'true'
```

This makes volumes easily accessible for backup. The backup container mounts `surek-data/volumes/` and backs up all stack volumes.

#### Caddy Labels

For services marked as public, Surek adds Caddy labels for reverse proxy configuration:

```yaml
# Stack config
public:
  - domain: app.example.com
    target: myapp:8080
    auth: admin:password

# Added to service labels
labels:
  surek.managed: 'true'
  caddy: app.example.com
  caddy.reverse_proxy: '{{upstreams 8080}}'
  caddy.basic_auth: ''
  caddy.basic_auth.admin: <bcrypt-hashed-password>
```

Caddy Docker Proxy watches for these labels and automatically configures routing.

#### Environment Variables

Environment variables from the stack config are merged with existing service environments:

```yaml
# Stack config
env:
  shared:
    - TZ=UTC
  by_container:
    myapp:
      - DATABASE_URL=postgres://...

# Merged into each service's environment section
```

### 4. Docker Compose Execution

Finally, Surek executes:

```bash
docker compose --file docker-compose.surek.yml --project-directory <project-dir> up -d --build
```

## Variable Expansion

Surek supports variable substitution in stack configs (`public.domain`, `public.auth`, and `env` sections):

| Variable | Source |
|----------|--------|
| `<root>` | `root_domain` from surek.yml |
| `<default_auth>` | `<default_user>:<default_password>` |
| `<default_user>` | User from `default_auth` in surek.yml |
| `<default_password>` | Password from `default_auth` in surek.yml |
| `<backup_password>` | `backup.password` from surek.yml |
| `<backup_s3_endpoint>` | `backup.s3_endpoint` from surek.yml |
| `<backup_s3_bucket>` | `backup.s3_bucket` from surek.yml |
| `<backup_s3_access_key>` | `backup.s3_access_key` from surek.yml |
| `<backup_s3_secret_key>` | `backup.s3_secret_key` from surek.yml |

Variables are expanded at deployment time using string replacement.

## Command Reference

| Command | Description |
|---------|-------------|
| `surek system start` | Create Docker network and start system containers |
| `surek system stop` | Stop system containers |
| `surek deploy <name>` | Pull sources, transform compose file, and deploy stack |
| `surek start <name>` | Start a previously deployed stack (no re-transformation) |
| `surek stop <name>` | Stop a deployed stack |
| `surek validate <path>` | Validate a stack configuration file |
| `surek status` | Show status of system and user stacks |

## Authentication

### Basic HTTP Auth

When `auth` is specified for a public service, Surek:
1. Parses the `user:password` format
2. Hashes the password using bcrypt (cost factor 14)
3. Adds Caddy basic_auth labels with the hashed password
4. Escapes `$` characters as `$$` for Docker Compose compatibility

### GitHub Authentication

For private repositories, configure a Personal Access Token in `surek.yml`:

```yaml
github:
  pat: ghp_xxxxxxxxxxxxxxxxxxxx
```

The PAT is passed to Octokit for authenticated GitHub API requests.

## Backup System

The backup container uses [docker-volume-backup](https://github.com/offen/docker-volume-backup) with three schedules:

| Schedule | Retention |
|----------|-----------|
| Daily | Configured in `backup-daily.env` |
| Weekly | Configured in `backup-weekly.env` |
| Monthly | Configured in `backup-monthly.env` |

Backups are encrypted with GPG using the configured password and uploaded to S3-compatible storage.

### Excluding Volumes

To exclude volumes from backup (e.g., caches or temporary data):

```yaml
backup:
  exclude_volumes:
    - cache_volume
    - temp_data
```

Excluded volumes retain their original Docker Compose configuration and are not converted to local bind mounts.

## Networking

All Surek-managed containers are placed on a shared Docker network named `surek`. This enables:

- Direct container-to-container communication using service names
- Caddy to proxy traffic to any container
- Cross-stack service dependencies

The network is created during `surek system start` and marked with the label `surek.managed: true`.

## Development Mode

When `NODE_ENV=development`, Surek adds `caddy.tls: internal` to public services, configuring Caddy to use self-signed certificates instead of requesting real ones.

## File Structure Reference

```
working-directory/
├── surek.yml              # Main configuration
├── stacks/                # User-defined stacks
│   └── my-app/
│       ├── surek.stack.yml    # Stack configuration
│       ├── docker-compose.yml # Compose file (if local source)
│       └── ...                # Additional files
└── surek-data/            # Generated at runtime (gitignore this)
    ├── projects/
    │   └── my-app/
    │       ├── docker-compose.surek.yml
    │       └── ...
    └── volumes/
        └── my-app/
            └── data/
```
