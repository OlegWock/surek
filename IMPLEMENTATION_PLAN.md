# Surek Python v2 Implementation Plan

This document outlines the implementation plan for rewriting Surek from TypeScript to Python, including all new features specified in the v2 documentation.

## Overview

**Current State:** TypeScript/Node.js CLI tool distributed via npm
**Target State:** Python CLI tool with TUI, distributed via PyPI using `uv`

**Reference:** The original TypeScript implementation is backed up at `/tmp/surek-ts-backup/` for reference during development.

---

## Phase 1: Project Setup & Core Infrastructure

### 1.1 Project Initialization
- Initialize `uv` project with `pyproject.toml`
- Set up directory structure per spec
- Configure package metadata for PyPI distribution
- Set up development tools: `ruff`, `mypy`, `pytest`

### 1.2 Core Models (Pydantic)
- `SurekConfig` - Main configuration model (`surek.yml`)
- `StackConfig` - Stack configuration model (`surek.stack.yml`)
- `BackupConfig`, `GitHubConfig`, `SystemServicesConfig`, `NotificationConfig`
- `PublicEndpoint`, `EnvConfig`, `LocalSource`, `GitHubSource`

### 1.3 Utility Modules
- `utils/paths.py` - Path constants (`get_data_dir()`, `SYSTEM_DIR`, etc.)
- `utils/logging.py` - Rich console logging setup
- `utils/env.py` - Environment variable expansion (`${VAR}` syntax)
- `core/variables.py` - Surek variable expansion (`<root>`, `<default_auth>`, etc.)

### 1.4 Configuration Loading
- `core/config.py` - Load and validate `surek.yml`
- Environment variable expansion before validation
- Proper error handling with clear messages

**Deliverables:**
- Working `uv` project structure
- All Pydantic models defined and tested
- Config loading with environment variable support

### Commit Instructions (Phase 1)
```bash
# After completing Phase 1:
git add -A
git commit -m "feat: initialize Python project with core models and config loading

- Set up uv project structure with pyproject.toml
- Add Pydantic models for SurekConfig and StackConfig
- Implement environment variable expansion (\${VAR} syntax)
- Add Surek variable expansion (<root>, <default_auth>, etc.)
- Set up utility modules (paths, logging)
- Add basic tests for config loading"
```

---

## Phase 2: Stack Management Core

### 2.1 Stack Discovery
- `core/stacks.py` - `get_available_stacks()`, `get_stack_by_name()`
- Stack loading from `stacks/` directory
- Validation and error collection

### 2.2 Docker Integration
- `core/docker.py` - Docker client wrapper using official Python SDK
- Network management (create `surek` network)
- Container listing and stats (CPU, memory)
- Health check status retrieval

### 2.3 Docker Compose Execution
- Wrapper for `docker compose` CLI commands
- Support for `up`, `stop`, `ps`, `logs` commands
- Proper error handling and output capture

### 2.4 Compose File Transformation
- `core/compose.py` - The core transformation logic
- Network injection (add `surek` external network)
- Volume transformation (bind mounts for backup)
- Caddy label injection for public endpoints
- Environment variable injection
- BCrypt password hashing for basic auth

**Deliverables:**
- Stack discovery and loading
- Docker network and container management
- Compose file transformation (matching v1 behavior)

### Commit Instructions (Phase 2)
```bash
# After completing Phase 2:
git add -A
git commit -m "feat: add stack management and compose transformation

- Implement stack discovery from stacks/ directory
- Add Docker client wrapper with network management
- Add container stats (CPU, memory, health) retrieval
- Implement compose file transformation:
  - Network injection (surek external network)
  - Volume bind mount transformation for backup
  - Caddy label injection for reverse proxy
  - Environment variable injection
  - BCrypt password hashing for basic auth
- Add docker compose CLI wrapper"
```

---

## Phase 3: GitHub Integration & Deployment

### 3.1 GitHub Operations
- `core/github.py` - GitHub API client using `httpx`
- Repository download as zipball
- Zip extraction with root folder handling
- Commit hash caching (`github_cache.json`)

### 3.2 Stack Deployment Pipeline
- Source resolution (local vs GitHub)
- GitHub caching (skip download if unchanged)
- File copying with overwrite
- Compose transformation
- Container startup

### 3.3 Stack Lifecycle
- `start_stack()` - Start existing deployment
- `stop_stack()` - Stop running stack
- `deploy_stack()` - Full deployment pipeline

**Deliverables:**
- GitHub repository pulling with caching
- Complete deployment pipeline
- Stack start/stop functionality

### Commit Instructions (Phase 3)
```bash
# After completing Phase 3:
git add -A
git commit -m "feat: add GitHub integration and deployment pipeline

- Implement GitHub repo download via API
- Add commit hash caching to skip unchanged repos
- Implement full deployment pipeline:
  - Source resolution (local vs GitHub)
  - File copying with overwrite
  - Compose transformation
  - Container startup
- Add start_stack() and stop_stack() functions"
```

---

## Phase 4: CLI Commands (Typer)

### 4.1 CLI Framework Setup
- `cli/main.py` - Typer app initialization
- Command groups: `system`, `backup`
- Version flag, help text

### 4.2 Core Commands
- `surek deploy <stack>` - Deploy a stack
- `surek start <stack>` - Start deployed stack
- `surek stop <stack>` - Stop running stack
- `surek status` - Show all stacks with status/health/resources
- `surek validate <path>` - Validate stack config

### 4.3 System Commands
- `surek system start` - Create network, deploy system containers
- `surek system stop` - Stop system containers

### 4.4 New Commands
- `surek init` - Interactive wizard for `surek.yml`
- `surek init --git-only` - Just add to `.gitignore`
- `surek new` - Interactive stack creation wizard
- `surek info <stack>` - Detailed stack info with services/volumes
- `surek info <stack> --logs` - Include recent logs
- `surek logs <stack> [service]` - View logs (with `--follow`, `--tail`)
- `surek --help-llm` - Print full documentation for LLM usage

**Deliverables:**
- All CLI commands implemented
- Rich output with tables and formatting
- Interactive wizards for `init` and `new`

### Commit Instructions (Phase 4)
```bash
# After completing Phase 4:
git add -A
git commit -m "feat: implement CLI commands with Typer

- Add Typer CLI framework with command groups
- Implement core commands: deploy, start, stop, status, validate
- Implement system commands: system start, system stop
- Add new commands:
  - init: interactive wizard for surek.yml
  - new: interactive stack creation
  - info: detailed stack information
  - logs: log viewing with follow/tail
  - --help-llm: LLM documentation output
- Add rich table output for status display"
```

---

## Phase 5: Backup System

### 5.1 S3 Operations
- `core/backup.py` - S3 client using `boto3`
- List backups from S3
- Download/upload backup files
- Parse backup types from filenames

### 5.2 Backup Commands
- `surek backup` / `surek backup list` - List all backups
- `surek backup run` - Trigger manual backup
- `surek backup restore` - Restore from backup (CLI and interactive)

### 5.3 Failure Tracking
- `backup_failures.json` for tracking failures
- Log failures locally (notification delivery for future version)

### 5.4 System Backup Container
- Copy system resources (backup env files)
- System compose transformation (remove backup if not configured)

**Deliverables:**
- S3 backup listing
- Manual backup trigger
- Restore functionality (stop stacks, download, decrypt, extract)
- Failure tracking

### Commit Instructions (Phase 5)
```bash
# After completing Phase 5:
git add -A
git commit -m "feat: implement backup system with S3 integration

- Add S3 client using boto3
- Implement backup list command
- Add manual backup trigger (backup run)
- Implement backup restore functionality
- Add failure tracking (backup_failures.json)
- Handle system compose transformation for backup service"
```

---

## Phase 6: Interactive TUI (Textual)

### 6.1 TUI Framework
- `tui/app.py` - Main Textual application
- Tab-based navigation (Stacks, Backups)
- Keyboard bindings (quit, refresh, help)

### 6.2 Stacks Screen
- DataTable with stack status
- Health and resource usage columns
- Actions: deploy, start, stop, view details, logs
- Navigate to details screen

### 6.3 Stack Details Screen
- Services table (image, status, health, resources)
- Volumes table (path, size)
- Public endpoints list
- Scrollable log viewer with filtering

### 6.4 Log Viewer Widget
- `tui/widgets/log_viewer.py`
- Real-time log streaming
- Filter input
- Scrollable output

### 6.5 Backups Screen
- Backup list with type, size, date
- Restore action
- Run backup now action

### 6.6 Entry Point Integration
- `surek` without command launches TUI
- `surek logs --follow` launches log viewer TUI

**Deliverables:**
- Full TUI application
- Real-time log streaming
- Interactive backup restore

### Commit Instructions (Phase 6)
```bash
# After completing Phase 6:
git add -A
git commit -m "feat: add interactive TUI with Textual

- Implement main TUI application with tab navigation
- Add Stacks screen with status table and actions
- Add Stack Details screen with services/volumes info
- Implement log viewer widget with filtering
- Add Backups screen with restore functionality
- Integrate TUI launch from CLI (surek without command)"
```

---

## Phase 7: System Services & Polish

### 7.1 Optional System Services
- Respect `system_services.portainer` and `system_services.netdata` config
- Remove disabled services from system compose
- Remove corresponding public endpoints

### 7.2 Resource Files
- Bundle `system/` directory in package
- Bundle `llm_docs.md` for `--help-llm`
- Configure `pyproject.toml` package data

### 7.3 Development Mode
- `NODE_ENV=development` for internal TLS certificates
- (Consider renaming to `SUREK_ENV` or similar)

### 7.4 Error Handling Polish
- Consistent error messages matching spec
- Proper Docker error surfacing
- Validation error formatting

**Deliverables:**
- Optional portainer/netdata
- Bundled resources
- Polished error messages

### Commit Instructions (Phase 7)
```bash
# After completing Phase 7:
git add -A
git commit -m "feat: add optional system services and polish

- Implement optional portainer/netdata via config
- Bundle system resources in package
- Add llm_docs.md for --help-llm
- Improve error messages and Docker error handling
- Add development mode support"
```

---

## Phase 8: Testing & Documentation

### 8.1 Unit Tests
- Config loading and validation
- Compose transformation
- Variable expansion
- Stack discovery

### 8.2 Integration Tests
- v1 config compatibility
- End-to-end deployment (with Docker mocking)
- GitHub pull simulation

### 8.3 Documentation
- `llm_docs.md` - Complete documentation for `--help-llm`
- Update `README.md` for Python version
- Migration guide from v1

**Deliverables:**
- Comprehensive test suite
- Full documentation
- v1 compatibility verified

### Commit Instructions (Phase 8)
```bash
# After completing Phase 8:
git add -A
git commit -m "test: add comprehensive test suite and documentation

- Add unit tests for config, compose, variables, stacks
- Add integration tests for v1 compatibility
- Update README.md for Python version
- Add migration guide from v1
- Complete llm_docs.md documentation"
```

---

## Phase 9: Distribution & Release

### 9.1 PyPI Packaging
- Finalize `pyproject.toml` metadata
- Configure build system
- Entry point: `surek` command

### 9.2 Release
- Version 2.0.0
- Publish to PyPI
- Update installation instructions

**Deliverables:**
- Published to PyPI
- Installable via `pip install surek` or `uv add surek`

### Commit Instructions (Phase 9)
```bash
# After completing Phase 9:
git add -A
git commit -m "chore: prepare for PyPI release

- Finalize pyproject.toml metadata
- Configure build system for distribution
- Update installation instructions"

# Tag the release
git tag -a v2.0.0 -m "Surek v2.0.0 - Python rewrite"

# Push with tags
git push origin main --tags
```

---

## Dependency Summary

### Runtime
| Package | Purpose |
|---------|---------|
| `pydantic` | Configuration validation |
| `textual` | Interactive TUI |
| `typer` | CLI framework |
| `rich` | Terminal formatting |
| `docker` | Docker SDK |
| `pyyaml` | YAML parsing |
| `httpx` | HTTP client for GitHub |
| `boto3` | S3 client |
| `bcrypt` | Password hashing |

### Development
| Package | Purpose |
|---------|---------|
| `pytest` | Testing |
| `pytest-asyncio` | Async test support |
| `mypy` | Type checking |
| `ruff` | Linting/formatting |

---

## Implementation Order (Recommended)

1. **Phase 1** - Get the foundation right: project structure, models, config loading
2. **Phase 2** - Core functionality: stack discovery, Docker integration, compose transformation
3. **Phase 3** - GitHub pulling and deployment pipeline
4. **Phase 4** - CLI commands (can start testing end-to-end)
5. **Phase 5** - Backup system
6. **Phase 6** - TUI (can be done in parallel with Phase 5)
7. **Phase 7** - Polish and optional features
8. **Phase 8** - Testing and documentation
9. **Phase 9** - Release

Phases 5 and 6 can be worked on in parallel since they're relatively independent.

---

## Key Technical Decisions

### 1. Docker Compose Execution
Use subprocess to call `docker compose` CLI rather than trying to replicate all compose logic. The Docker Python SDK is used for container inspection and stats.

### 2. Async vs Sync
The TUI will need async for log streaming. CLI commands can be synchronous. Consider using `asyncio` where needed and keeping simple commands sync.

### 3. Config Key Naming
Pydantic uses `snake_case` by default which matches the YAML format. No need for camelCase conversion like in TypeScript version.

### 4. Environment Variable Expansion
Do expansion before Pydantic validation so that validators see actual values.

### 5. Backward Compatibility
All v1 configs must work without modification. New features are additive.

---

## Risk Mitigation

| Risk | Mitigation |
|------|------------|
| Docker Compose CLI changes | Pin to minimum version, test with multiple versions |
| bcrypt platform issues | Use `bcrypt` package which has prebuilt wheels |
| TUI terminal compatibility | Textual handles most cases; test on common terminals |
| S3 provider differences | Test with multiple S3-compatible providers |

---

## Success Criteria

1. All v1 `surek.yml` and `surek.stack.yml` files work without modification
2. All existing CLI commands produce equivalent results
3. New features work as specified
4. TUI provides functional dashboard
5. Installable from PyPI
6. Tests pass on Linux and macOS

---

## Quick Reference: Git Workflow

After each phase, use the provided commit message. For intermediate progress within a phase:

```bash
# Work-in-progress commits (squash later if desired)
git add -A
git commit -m "wip: <brief description of progress>"
```

To verify the repo state before committing:
```bash
git status
git diff --staged
```

To check what will be committed:
```bash
git diff HEAD
```
