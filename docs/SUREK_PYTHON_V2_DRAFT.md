* Rewrite in Python instead of TypeScript
* Use `uv` for project management
* Use PyPI for distribution
* New version should be backward compatible with stacks from previous version of the app and could be used as dropin replacement. Commands can be different though
* Use Pydantic in place of zod for data validation




## New features

* Provide two kinds of interface: commands and interactive
* Commands are same as in surek-ts: user enters command, it's executed, results are printed, and program exits
* Intractive mode will render interactive TUI allowing user to do multiple actions in the terminal, provide live data, and require explicit exit via Ctrl+C
  * Use [Textual](https://textual.textualize.io/) for TUI of interactive parts
  * Interactive mode will be launched when running `surek` without command or when command requires intractivity
  * In interactive mode by default user will be presented with table of detected stacks, their status, and actions (stop, start, deploy, etc)
  * There should be tabs or menu to switch to see backups (similar to what `surek backup list` will display)
  * There should be also option to see details about service. This should show info similar to `surek info <stack>` but interactive, e.g. logs panel should be scrollable and filterable

* New commands
  * `--help-llm` -- instead of normal help prints whole documentation for surek, intended for use by LLMs.
  * `surek new` -- creates new stack in intractive mode
  * `surek init` -- interactive wizard to create root config and .gitignore file
  * `surek init git` -- add `surek-data` to .gitignore and exit
  * `surek info <stack>` -- print info about stack, including services (with info like docker image, status, etc), volumes (incl. storage usage by each volume)
    * Allow optional `-l`/`--logs` to include latest 100 log lines into output
  * `surek logs <stack> [service]` -- output logs for stack or specific service
    * Allow for `--follow`/`-f` option to run in interactive mode (default)
    * Allow for `--tail`/`-t` option to run in static mode and tail results
  * `surek backup` / `surek backup list` -- list all backups present on S3
  * `surek backup run` -- trigger manual backup
  * `surek backup restore <stack> [service] --id <backup_name>` -- restore backup for stack/service from S3
  * `surek backup restore` -- same, but interactive

* New features
  * Option to disable netdata and/or portainer
  * If service has healthchecks defined, we should display them along with running/stopped status
  * Resource usage in status** - Show CPU/memory usage alongside running status. The data is available from Docker.
  * Notification on backup failure** - Currently backups fail silently. Could add webhook or email notifications.
  * Allow using machine's env variables in surek config using `${VAR_NAME}` syntax
  * Allow using machine's env variables in stack configs

* Bug fixes / tech debt
  * Caching for GitHub pulls** - The code has a TODO noting that re-downloading triggers unnecessary rebuilds. Could cache commit hashes and skip if unchanged.
  * Better Docker error handling** - The code has a TODO about properly surfacing Docker command errors to users.
