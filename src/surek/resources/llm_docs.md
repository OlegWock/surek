# Surek Documentation for LLMs

This document provides comprehensive documentation for Surek, intended for LLM consumption.

## Overview

Surek is a Docker Compose orchestration tool for self-hosted services. It provides:

- Automatic reverse proxy configuration via Caddy
- Volume management with bind mounts for backup
- Shared networking across all stacks
- Environment variable injection with template variables
- Automated backups to S3-compatible storage

## Commands

### Core Commands

- `surek deploy <stack>` - Deploy a stack (pull sources, transform compose, start containers)
- `surek start <stack>` - Start an already deployed stack
- `surek stop <stack>` - Stop a running stack
- `surek status` - Show status of all stacks
- `surek info <stack>` - Show detailed stack information
- `surek logs <stack> [service]` - View logs

### System Commands

- `surek system start` - Create Docker network and start system containers
- `surek system stop` - Stop system containers

### Backup Commands

- `surek backup list` - List all backups in S3
- `surek backup run` - Trigger immediate backup
- `surek backup restore` - Restore from backup

### Configuration Commands

- `surek init` - Interactive wizard to create surek.yml
- `surek new` - Interactive wizard to create a new stack
- `surek validate <path>` - Validate a stack configuration

## Configuration Files

### surek.yml (Main Configuration)

```yaml
root_domain: example.com
default_auth: admin:password

backup:  # Optional
  password: encryption_password
  s3_endpoint: s3.example.com
  s3_bucket: my-backups
  s3_access_key: ACCESS_KEY
  s3_secret_key: SECRET_KEY

github:  # Optional
  pat: github_personal_access_token

system_services:  # Optional
  portainer: true
  netdata: true
```

### surek.stack.yml (Stack Configuration)

```yaml
name: my-stack
source:
  type: local  # or github with slug: owner/repo#ref
compose_file_path: ./docker-compose.yml

public:
  - domain: app.<root>
    target: myapp:8080
    auth: <default_auth>  # Optional

env:
  shared:
    - TZ=UTC
  by_container:
    myapp:
      - DATABASE_URL=postgres://...

backup:
  exclude_volumes:
    - cache_data
```

## Template Variables

- `<root>` - root_domain from surek.yml
- `<default_auth>` - default_auth (user:password)
- `<default_user>` - username from default_auth
- `<default_password>` - password from default_auth
- `<backup_password>` - backup encryption password
- `<backup_s3_endpoint>` - S3 endpoint URL
- `<backup_s3_bucket>` - S3 bucket name
- `<backup_s3_access_key>` - S3 access key
- `<backup_s3_secret_key>` - S3 secret key

## Environment Variable Expansion

Use `${VAR_NAME}` syntax to reference environment variables in configuration files.

---

*Full documentation will be added in a future release.*
