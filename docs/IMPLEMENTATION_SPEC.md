# Surek Implementation Specification

This document provides a complete specification for reimplementing Surek from scratch while maintaining backward compatibility. It covers every feature, configuration format, algorithm, and edge case.

## Table of Contents

1. [Overview](#overview)
2. [Dependencies](#dependencies)
3. [Directory Structure](#directory-structure)
4. [Configuration Files](#configuration-files)
5. [Constants and Labels](#constants-and-labels)
6. [CLI Commands](#cli-commands)
7. [Core Algorithms](#core-algorithms)
8. [System Containers](#system-containers)
9. [Error Handling](#error-handling)

---

## Overview

Surek is a CLI tool that orchestrates Docker Compose deployments with automatic:
- Reverse proxy configuration via Caddy
- Volume management with bind mounts for backup
- Shared networking across all stacks
- Environment variable injection with template variables

The tool is distributed as an npm package and installed globally.

---

## Dependencies

### Runtime Dependencies

| Package | Version | Purpose |
|---------|---------|---------|
| `@octokit/rest` | ^21.0.1 | GitHub API client for downloading repositories |
| `adm-zip` | ^0.5.14 | Extracting downloaded GitHub repository archives |
| `bcrypt` | ^5.1.1 | Hashing passwords for Caddy basic auth |
| `camelcase-keys` | ^9.1.3 | Converting YAML snake_case to camelCase |
| `cmd-ts` | ^0.13.0 | CLI argument parsing and command structure |
| `console-table-printer` | ^2.12.1 | Formatting status output as tables |
| `dockerode` | ^4.0.2 | Docker Engine API client |
| `fast-glob` | ^3.3.2 | Finding stack configuration files |
| `fs-extra` | ^11.2.0 | Enhanced filesystem operations |
| `js-yaml` | ^4.1.0 | YAML parsing and serialization |
| `signale` | ^1.4.0 | Styled console logging |
| `type-fest` | ^4.21.0 | TypeScript utility types |
| `zod` | ^3.23.8 | Schema validation |
| `zod-validation-error` | ^3.3.0 | Human-readable validation errors |

### System Requirements

- Node.js v22+ (tested version)
- Docker Engine with Compose plugin (`docker compose` command)
- Domain pointed to the server (for HTTPS)

---

## Directory Structure

### Installation Directory

The package installs to npm's global modules. The `system/` directory containing system container definitions must be located relative to the package root:

```
<package-root>/
├── dist/
│   └── index.js          # Compiled entry point (bin target)
├── system/
│   ├── surek.stack.yml   # System stack configuration
│   ├── docker-compose.yml
│   ├── backup-daily.env
│   ├── backup-weekly.env
│   └── backup-monthly.env
└── package.json
```

The `SYSTEM_DIR` constant is computed by resolving the real path of the executing script and navigating to `../system` from there.

### Working Directory (User's Project)

```
<working-directory>/
├── surek.yml             # Main configuration (required)
├── stacks/               # User-defined stacks (required for user stacks)
│   └── <stack-name>/
│       ├── surek.stack.yml   # Stack configuration
│       ├── docker-compose.yml
│       └── <additional-files>
└── surek-data/           # Generated at runtime (should be gitignored)
    ├── projects/
    │   └── <stack-name>/
    │       ├── docker-compose.surek.yml  # Transformed compose file
    │       └── <copied-files>
    └── volumes/
        └── <stack-name>/
            └── <volume-name>/
```

---

## Configuration Files

### Main Configuration (`surek.yml`)

**Location:** Current working directory, filename `surek.yml` or `surek.yaml`

**Schema:**

```yaml
# Required. The root domain for all services.
root_domain: string

# Required. Default authentication in "user:password" format.
# Used for Netdata and available as template variable.
default_auth: string  # Format: "<user>:<password>"

# Optional. S3 backup configuration.
backup:
  password: string        # GPG encryption password
  s3_endpoint: string     # S3 endpoint URL (e.g., "s3.eu-central-003.backblazeb2.com")
  s3_bucket: string       # Bucket name
  s3_access_key: string   # AWS access key ID
  s3_secret_key: string   # AWS secret access key

# Optional. GitHub authentication for private repos.
github:
  pat: string             # Personal Access Token
```

**Validation Rules:**
- `root_domain`: Required, non-empty string
- `default_auth`: Required, must contain exactly one colon (`:`) separator
- `backup`: All fields required if section is present
- `github`: `pat` field required if section is present

**Parsing:**
1. Look for `surek.yml` in current working directory
2. If not found, look for `surek.yaml`
3. If neither exists, exit with error: `"Config file not found. Make sure you have file surek.yml in current working directory"`
4. Parse YAML content
5. Validate against schema using Zod
6. Transform keys from snake_case to camelCase (except `env.shared` and `env.by_container`)
7. Parse `default_auth` into `{ user: string, password: string }` object

### Stack Configuration (`surek.stack.yml`)

**Location:** Any subdirectory of `stacks/`, filename must be exactly `surek.stack.yml`

**Schema:**

```yaml
# Required. Unique identifier for the stack.
name: string

# Required. Source of the stack files.
source:
  # For local sources (files already present):
  type: local
  
  # OR for GitHub sources:
  type: github
  slug: string  # Format: "owner/repo" or "owner/repo#ref"

# Optional. Path to compose file. Default: "./docker-compose.yml"
compose_file_path: string

# Optional. Services to expose publicly via reverse proxy.
public:
  - domain: string      # Domain/subdomain for the service
    target: string      # Format: "<service-name>:<port>" or "<service-name>" (default port 80)
    auth: string        # Optional. Format: "<user>:<password>" or "<default_auth>"

# Optional. Environment variables to inject.
env:
  # Variables added to ALL services in the stack
  shared:
    - "KEY=value"
  # Variables added to specific services only
  by_container:
    <service-name>:
      - "KEY=value"

# Optional. Backup exclusion settings.
backup:
  exclude_volumes:
    - "volume-name"
```

**Validation Rules:**
- `name`: Required, non-empty string
- `source.type`: Must be either `"local"` or `"github"`
- `source.slug`: Required when `type` is `"github"`, format `owner/repo` with optional `#ref` suffix
- `compose_file_path`: Defaults to `"./docker-compose.yml"` if not specified
- `public[].domain`: Required string
- `public[].target`: Required string, format `service:port` or just `service`
- `public[].auth`: Optional, must be `"<default_auth>"` literal or `"user:password"` format
- `env.shared`: Array of strings in `KEY=value` format
- `env.by_container`: Object mapping service names to arrays of `KEY=value` strings
- `backup.exclude_volumes`: Array of volume names, defaults to empty array

**Parsing:**
1. Read file content as UTF-8
2. Parse YAML
3. Validate against schema
4. Transform keys to camelCase (preserving `env.shared` and `env.by_container` as-is)
5. Apply defaults for optional fields

---

## Constants and Labels

### Network Name

```
SUREK_NETWORK = "surek"
```

All Surek-managed containers connect to this Docker network.

### Default Labels

```javascript
DEFAULT_SUREK_LABELS = {
  "surek.managed": "true"
}
```

These labels are added to:
- The Surek Docker network
- All transformed volumes
- All services with public endpoints

### Development Mode

When `NODE_ENV=development`:
- Caddy uses internal (self-signed) TLS certificates
- Add label `caddy.tls: "internal"` to public services

### Paths

| Constant | Computation |
|----------|-------------|
| `PROJECT_ROOT` | `path.join(path.dirname(fs.realpathSync(process.argv[1])), '..')` |
| `SYSTEM_DIR` | `path.join(PROJECT_ROOT, 'system')` |
| `SYSTEM_SERVICES_CONFIG` | `path.join(SYSTEM_DIR, 'surek.stack.yml')` |
| `getDataDir()` | `path.join(process.cwd(), 'surek-data')` - created if not exists |

---

## CLI Commands

### Entry Point

```
surek <command> [options]
```

The CLI uses the `cmd-ts` library for argument parsing. Version is read from `package.json`.

### `surek system start`

**Description:** Ensure correct Docker configuration and run system containers.

**Arguments:** None

**Algorithm:**

```
1. Load main config (surek.yml)
2. Connect to Docker daemon via dockerode
3. List all Docker networks
4. If network named "surek" does not exist:
   a. Create network with name "surek"
   b. Add labels: { "surek.managed": "true" }
5. Stop system containers if running (silent mode)
6. Deploy system stack from SYSTEM_SERVICES_CONFIG
```

**Docker Network Creation Parameters:**
```javascript
{
  Name: "surek",
  Labels: {
    "surek.managed": "true"
  }
}
```

### `surek system stop`

**Description:** Stop Surek system containers.

**Arguments:** None

**Algorithm:**

```
1. Load stack config from SYSTEM_SERVICES_CONFIG
2. Call stopStack() with silent=false
```

### `surek deploy <stack-name>`

**Description:** Deploy a stack (pull sources, transform compose file, start containers).

**Arguments:**
- `stack-name` (positional, required): Name of the stack as defined in `surek.stack.yml`

**Algorithm:**

```
1. Load main config (surek.yml)
2. Find stack by name in stacks/ directory
3. Log: "Loaded stack config from <path>"
4. Call deployStack(config, sourceDir, surekConfig)
```

### `surek start <stack-name>`

**Description:** Start an already deployed stack without re-transformation.

**Arguments:**
- `stack-name` (positional, required): Name of the stack

**Algorithm:**

```
1. Find stack by name
2. Log: "Loaded stack config from <path>"
3. Call startStack(config)
```

### `surek stop <stack-name>`

**Description:** Stop a deployed stack.

**Arguments:**
- `stack-name` (positional, required): Name of the stack

**Algorithm:**

```
1. Find stack by name
2. Log: "Loaded stack config from <path>"
3. Call stopStack(config, sourceDir, silent=false)
```

### `surek validate <stack-path>`

**Description:** Validate a stack configuration file.

**Arguments:**
- `stack-path` (positional, required): Path to `surek.stack.yml` file

**Algorithm:**

```
1. Try to load and parse stack config at given path
2. If successful:
   a. Log: "Loaded stack config with name <name> from <path>"
   b. Log success: "Config is valid"
3. If validation fails:
   a. Log error: "Error while loading config <path>"
   b. Log the validation error message
```

### `surek status`

**Description:** Output status of system containers and user stacks.

**Arguments:** None

**Algorithm:**

```
1. Load main config
2. Get list of all available stacks
3. Log: "Loaded available stacks"
4. Get status of "surek-system" stack
5. For each stack (in parallel):
   a. If stack config is invalid: status = "Invalid config"
   b. Otherwise: get stack status
6. Print table with columns: Stack, Status, Path
   - First row: "System containers" with system status
   - Remaining rows: user stacks
```

**Status Values:**
- `"× Not deployed"` - Project directory or compose file doesn't exist
- `"× Down"` - Compose file exists but no containers running
- `"✓ Running"` - All containers running
- `"✓ Running (X/Y)"` - X of Y containers running

---

## Core Algorithms

### Stack Discovery (`getAvailableStacks`)

**Input:** None (uses current working directory)

**Output:** Array of stack info objects

**Algorithm:**

```
1. stacksDir = path.join(process.cwd(), 'stacks')
2. If stacksDir doesn't exist: exit with error "Folder 'stacks' not found in current working directory"
3. Find all files matching "**/surek.stack.yml" in stacksDir using fast-glob
4. For each found file:
   a. configPath = path.join(stacksDir, relativePath)
   b. Try to load stack config
   c. If successful: return { name, config, path: configPath, valid: true, error: '' }
   d. If failed: return { name: '', config: null, path: configPath, valid: false, error: validationError }
5. Sort results by path (alphabetically)
6. Return array
```

### Stack Lookup (`getStackByName`)

**Input:** `name: string`

**Output:** Stack info object or exit

**Algorithm:**

```
1. If name is empty/falsy: exit with "Invalid stack name"
2. Get all available stacks
3. Find stack where stack.name === name
4. If not found: exit with "Stack with name '<name>' not found"
5. Return stack (cast to valid stack type)
```

### Stack Deployment (`deployStack`)

**Input:**
- `config: StackConfig` - Parsed stack configuration
- `sourceDir: string` - Directory containing the stack files
- `surekConfig: SurekConfig` - Main configuration

**Algorithm:**

```
1. projectDir = path.join(getDataDir(), "projects", config.name)
2. If projectDir exists: delete it recursively
3. Create projectDir recursively

4. If source.type === "github":
   a. Call pullGithubRepo(config, projectDir, surekConfig)

5. Copy all files from sourceDir to projectDir (recursive, overwrite)

6. composeFilePath = path.resolve(projectDir, config.composeFilePath)
7. If composeFilePath doesn't exist: exit with "Couldn't find compose file at <path>"

8. Read and parse compose file as YAML

9. If this is the system stack (config.name === 'surek-system' AND sourceDir === SYSTEM_DIR):
   a. Apply system-specific transformations

10. Transform compose file (see Compose Transformation algorithm)

11. patchedFilePath = path.join(projectDir, 'docker-compose.surek.yml')
12. Write transformed compose file to patchedFilePath
13. Log: "Saved patched compose file at <path>"

14. Start the stack
```

### GitHub Repository Pull (`pullGithubRepo`)

**Input:**
- `config: StackConfig` - Stack config with github source
- `targetDir: string` - Directory to extract into
- `surekConfig: SurekConfig` - Main config with GitHub PAT

**Algorithm:**

```
1. Validate source.type === "github", exit if not
2. Validate surekConfig.github exists, exit if not: "Github PAT is required for this"

3. Parse slug:
   a. Split by '/' to get [owner, repoWithRef]
   b. Split repoWithRef by '#' to get [repo, ref]
   c. Default ref to 'HEAD' if not specified

4. Create Octokit client with auth: surekConfig.github.pat

5. Log: "Downloading GitHub repo <slug>"

6. Call octokit.rest.repos.downloadZipballArchive({
     request: { parseSuccessResponseBody: false },
     owner,
     repo,
     ref
   })

7. Unpack the zip stream to targetDir:
   a. Convert ReadableStream to Buffer
   b. Create AdmZip from buffer
   c. Extract all entries to targetDir

8. Move contents up one level:
   a. GitHub zipballs have a single root folder (e.g., "owner-repo-commitsha/")
   b. List contents of targetDir
   c. If not exactly one item: exit "Expected a single root folder in the zip file"
   d. If the item is not a directory: exit "The single item in the zip is not a folder"
   e. Move all contents of the root folder up to targetDir
   f. Remove the now-empty root folder

9. Log: "Downloaded and unpacked repo content."
```

### Compose File Transformation (`transformComposeFile`)

**Input:**
- `originalSpec: ComposeSpecification` - Parsed Docker Compose file
- `config: StackConfig` - Stack configuration
- `surekConfig: SurekConfig` - Main configuration

**Output:** Transformed `ComposeSpecification`

**Algorithm:**

```
1. Deep clone the original spec using structuredClone()

2. Initialize paths:
   dataDir = getDataDir()
   volumesDir = path.join(dataDir, 'volumes', config.name)
   foldersToCreate = []

3. NETWORK INJECTION:
   a. If spec.networks is undefined: spec.networks = {}
   b. Add Surek network:
      spec.networks["surek"] = {
        name: "surek",
        external: true
      }

4. VOLUME TRANSFORMATION:
   For each volume in spec.volumes:
   a. If volume name is in config.backup.excludeVolumes: skip
   b. Get volume descriptor (default to {})
   c. If descriptor has any keys (pre-configured): 
      - Log warning: "Volume <name> is already pre-configured. This volume will be skipped on backup."
      - Skip
   d. folderPath = path.join(volumesDir, volumeName)
   e. Add folderPath to foldersToCreate
   f. Replace volume definition:
      spec.volumes[name] = {
        driver: "local",
        driver_opts: {
          type: "none",
          o: "bind",
          device: folderPath
        },
        labels: { "surek.managed": "true" }
      }

5. PUBLIC SERVICE LABELS:
   For each public entry in config.public:
   a. Parse target: split by ':' to get [service, port]
      - Default port to 80 if not specified
   b. If service not in spec.services: exit "Service <name> not defined in docker-compose config"
   c. If service.labels is undefined: service.labels = {}
   d. Build labels object:
      {
        "surek.managed": "true",
        "caddy": expandVariables(domain, surekConfig),
        "caddy.reverse_proxy": "{{upstreams <port>}}"
      }
   e. If NODE_ENV === "development":
      - Add "caddy.tls": "internal"
   f. If auth is specified:
      - Expand variables in auth string
      - Split by ':' to get [user, password]
      - Hash password with bcrypt (cost factor 14)
      - Add "caddy.basic_auth": ""
      - Add "caddy.basic_auth.<user>": <hashed_password with $ replaced by $$>
   g. Merge labels into service:
      - If service.labels is array: push entries as "key=JSON.stringify(value)" strings
      - If service.labels is object: Object.assign()

6. ENVIRONMENT VARIABLE INJECTION:
   If config.env exists and spec.services exists:
   For each service in spec.services:
   a. Get container-specific env: config.env.byContainer[serviceName] ?? []
   b. Get shared env: config.env.shared ?? []
   c. Expand variables in all env strings
   d. Merge into service.environment using mergeEnvs()

7. CREATE VOLUME DIRECTORIES:
   For each path in foldersToCreate:
   - mkdirSync(path, { recursive: true })

8. SERVICE NETWORK INJECTION:
   For each service in spec.services:
   a. If service.network_mode is set: skip (can't add networks with network_mode)
   b. If service.networks is undefined: service.networks = []
   c. If service.networks is array: push "surek"
   d. If service.networks is object: set service.networks["surek"] = null

9. Return transformed spec
```

### System Compose Transformation (`transformSystemComposeFile`)

**Input:**
- `originalSpec: ComposeSpecification`
- `config: SurekConfig`

**Output:** Modified `ComposeSpecification`

**Algorithm:**

```
1. If config.backup is not configured AND spec.services exists:
   a. Delete spec.services['backup']
2. Return spec
```

This removes the backup service when backup is not configured.

### Environment Merge (`mergeEnvs`)

**Input:**
- `original: ListOrDict` - Existing environment (array or object)
- `...extensions: string[][]` - Arrays of "KEY=value" strings to add

**Output:** Merged environment

**Algorithm:**

```
If original is array:
  Return [...original, ...extensions.flat()]
Else (original is object):
  Return {
    ...original,
    ...Object.fromEntries(extensions.flat().map(e => e.split('=')))
  }
```

### Variable Expansion (`expandVariables`)

**Input:**
- `val: string` - String potentially containing variables
- `config: SurekConfig` - Main configuration

**Output:** String with variables replaced

**Algorithm:**

```
1. result = val
2. Replace all occurrences:
   - "<root>" -> config.rootDomain
   - "<default_auth>" -> config.defaultAuth.user + ":" + config.defaultAuth.password
   - "<default_user>" -> config.defaultAuth.user
   - "<default_password>" -> config.defaultAuth.password
3. If config.backup exists, also replace:
   - "<backup_password>" -> config.backup.password
   - "<backup_s3_endpoint>" -> config.backup.s3Endpoint
   - "<backup_s3_bucket>" -> config.backup.s3Bucket
   - "<backup_s3_access_key>" -> config.backup.s3AccessKey
   - "<backup_s3_secret_key>" -> config.backup.s3SecretKey
4. Return result
```

### Stack Start (`startStack`)

**Input:** `config: StackConfig`

**Algorithm:**

```
1. patchedFilePath = path.join(getDataDir(), "projects", config.name, "docker-compose.surek.yml")
2. projectDir = path.join(getDataDir(), "projects", config.name)
3. Log: "Starting containers..."
4. Execute: docker compose --file <patchedFilePath> --project-directory <projectDir> up -d --build
5. Log: "Containers started"
```

### Stack Stop (`stopStack`)

**Input:**
- `config: StackConfig`
- `sourceDir: string`
- `silent: boolean`

**Algorithm:**

```
1. patchedComposeFile = path.join(getDataDir(), "projects", config.name, "docker-compose.surek.yml")
2. If patchedComposeFile doesn't exist:
   a. If silent: return (do nothing)
   b. Else: exit "Couldn't find compose file for this stack"
3. Execute: docker compose --file <patchedComposeFile> --project-directory <sourceDir> stop
4. Log: "Containers stopped"
```

### Stack Status (`getStackStatus`)

**Input:** `name: string`

**Output:** Status string

**Algorithm:**

```
1. dir = path.join(getDataDir(), "projects", name)
2. composeFile = path.join(dir, "docker-compose.surek.yml")
3. If dir or composeFile doesn't exist: return "× Not deployed"

4. Execute (silent): docker compose --file <composeFile> --project-directory <dir> ps --format json
5. Parse output: split by newline, parse each line as JSON, filter out parse failures
6. Count running containers: filter where State === "running"

7. If runningContainers.length === 0: return "× Down"
8. If runningContainers.length === total: return "✓ Running"
9. Else: return "✓ Running (<running>/<total>)"
```

### Docker Compose Execution (`execDockerCompose`)

**Input:**
```typescript
{
  composeFile: string,      // Path to compose file
  projectFolder?: string,   // Project directory
  command: 'up' | 'stop' | 'ps',
  options?: string[],       // Command options (e.g., ['-d', '--build'])
  args?: string[],          // Command arguments
  silent?: boolean          // Suppress output
}
```

**Output:** Promise<string> - stdout content

**Algorithm:**

```
1. Build command args array: ['compose']
2. Add: '--file', composeFile
3. If projectFolder: add '--project-directory', projectFolder
4. Add command
5. If options: add all options (flattened)
6. If args: add all args

7. If not silent:
   a. Log: "Executing docker command"
   b. Log: "$ docker <args joined by space>"

8. Spawn child process: 'docker' with args
9. Capture stdout chunks, write to process.stdout if not silent
10. Write stderr to process.stderr if not silent

11. Return promise:
    - On exit code 0: resolve with stdout
    - On non-zero exit: reject with Error("Command exited with code <code>.")
    - On error event: reject with error
```

### File Copy (`copyFolderRecursivelyWithOverwrite`)

**Input:**
- `source: string` - Source directory
- `destination: string` - Destination directory

**Algorithm:**

```
1. Ensure destination directory exists
2. List all items in source
3. For each item:
   a. sourcePath = path.join(source, item)
   b. destPath = path.join(destination, item)
   c. If item is directory: recurse
   d. If item is file: copy with overwrite
```

---

## System Containers

### Stack Configuration

**File:** `system/surek.stack.yml`

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

### Docker Compose

**File:** `system/docker-compose.yml`

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

### Backup Configuration

**File:** `system/backup-daily.env`
```
BACKUP_FILENAME="daily-backup-%Y-%m-%dT%H-%M-%S.tar.gz"
BACKUP_CRON_EXPRESSION="0 2 * * *"
BACKUP_PRUNING_PREFIX="daily-backup-"
BACKUP_RETENTION_DAYS="7"
```

**File:** `system/backup-weekly.env`
```
BACKUP_FILENAME="weekly-backup-%Y-%m-%dT%H-%M-%S.tar.gz"
BACKUP_CRON_EXPRESSION="0 3 * * 1"
BACKUP_PRUNING_PREFIX="weekly-backup-"
BACKUP_RETENTION_DAYS="60"
```

**File:** `system/backup-monthly.env`
```
BACKUP_FILENAME="monthly-backup-%Y-%m-%dT%H-%M-%S.tar.gz"
BACKUP_CRON_EXPRESSION="0 4 1 * *"
BACKUP_PRUNING_PREFIX="monthly-backup-"
BACKUP_RETENTION_DAYS="730"
```

### Backup Schedule Summary

| Schedule | Cron Expression | Retention |
|----------|-----------------|-----------|
| Daily | `0 2 * * *` (2:00 AM daily) | 7 days |
| Weekly | `0 3 * * 1` (3:00 AM Monday) | 60 days |
| Monthly | `0 4 1 * *` (4:00 AM 1st of month) | 730 days (2 years) |

---

## Error Handling

### Exit Function

All fatal errors call a centralized exit function:

```typescript
function exit(message: string = '', code: number = 1): never {
  if (message) {
    log.error(message);
  }
  process.exit(code);
}
```

### Error Messages

| Condition | Error Message |
|-----------|---------------|
| Config file missing | `"Config file not found. Make sure you have file surek.yml in current working directory"` |
| Config validation failed | Zod validation error (formatted by zod-validation-error) |
| Stack folder missing | `"Folder 'stacks' not found in current working directory"` |
| Invalid stack name | `"Invalid stack name"` |
| Stack not found | `"Stack with name '<name>' not found"` |
| Compose file missing | `"Couldn't find compose file at <path>"` |
| Patched compose missing | `"Couldn't find compose file for this stack"` |
| Service not in compose | `"Service <name> not defined in docker-compose config"` |
| GitHub PAT missing | `"Github PAT is required for this"` |
| Invalid GitHub zip | `"Expected a single root folder in the zip file"` |
| Invalid GitHub zip | `"The single item in the zip is not a folder"` |
| File copy error | `"Error while copying files"` |
| Docker command failed | `"Command exited with code <code>."` |

### Logging

Surek uses the `signale` library for styled console output:

- `log.info()` - Informational messages
- `log.warn()` - Warnings (e.g., pre-configured volumes)
- `log.error()` - Error messages
- `log.success()` - Success messages (e.g., validation passed)

---

## Appendix: Bcrypt Password Hashing

When generating basic auth passwords for Caddy:

1. Use bcrypt with cost factor **14**
2. After hashing, replace all `$` characters with `$$` (Docker Compose escape sequence)

Example:
```javascript
const hashedPassword = bcrypt.hashSync(password, 14);
const escapedPassword = hashedPassword.replaceAll('$', '$$$$');
// Note: '$$$$' in replaceAll produces '$$' in output due to special replacement patterns
```

---

## Appendix: YAML Key Transformation

When parsing YAML configs, all keys are converted from snake_case to camelCase using `camelcase-keys`, EXCEPT:

- `env.shared` - preserved as-is (array of environment strings)
- `env.by_container` - preserved as-is (object mapping service names to env arrays)

This is configured via the `stopPaths` option:
```javascript
camelcaseKeys(val, {
  deep: true,
  stopPaths: ['env.shared', 'env.by_container']
})
```

---

## Appendix: Docker Compose Label Formats

Docker Compose supports two formats for labels:

**Array format:**
```yaml
labels:
  - "key=value"
  - "another.key=another value"
```

**Object format:**
```yaml
labels:
  key: value
  another.key: another value
```

Surek must handle both formats when adding labels:
- For arrays: push `"key=JSON.stringify(value)"` strings
- For objects: use `Object.assign()` to merge
