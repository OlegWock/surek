"""Backups screen for TUI."""

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Container
from textual.widgets import DataTable, Static

from surek.core.backup import format_bytes, list_backups
from surek.core.config import load_config
from surek.exceptions import SurekError


class BackupsPane(Container):
    """Pane showing available backups."""

    BINDINGS = [
        Binding("b", "run_backup", "Run Backup"),
    ]

    def compose(self) -> ComposeResult:
        """Compose the backups pane."""
        yield Static("Backups", classes="title")
        yield DataTable(id="backups-table")

    def on_mount(self) -> None:
        """Initialize the table when mounted."""
        table = self.query_one("#backups-table", DataTable)
        table.cursor_type = "row"
        table.add_columns("Backup", "Type", "Size", "Created")
        self.refresh_data()

    def refresh_data(self) -> None:
        """Refresh the backups data."""
        table = self.query_one("#backups-table", DataTable)
        table.clear()

        try:
            config = load_config()

            if not config.backup:
                table.add_row(
                    "Backup not configured",
                    "-",
                    "-",
                    "-",
                    key="not-configured",
                )
                return

            backups = list_backups(config.backup)

            if not backups:
                table.add_row(
                    "No backups found",
                    "-",
                    "-",
                    "-",
                    key="empty",
                )
                return

            for backup in backups[:50]:  # Limit to 50 for performance
                table.add_row(
                    backup.name,
                    backup.backup_type.capitalize(),
                    format_bytes(backup.size),
                    backup.created.strftime("%Y-%m-%d %H:%M"),
                    key=backup.name,
                )

        except SurekError as e:
            table.add_row(
                f"Error: {e}",
                "-",
                "-",
                "-",
                key="error",
            )
        except Exception as e:
            table.add_row(
                f"Error: {e}",
                "-",
                "-",
                "-",
                key="error",
            )

    def action_run_backup(self) -> None:
        """Trigger a manual backup."""
        self.app.notify("Starting backup...", timeout=2)
        self.run_worker(self._run_backup())

    async def _run_backup(self) -> None:
        """Run backup asynchronously."""
        try:
            from surek.core.backup import trigger_backup

            trigger_backup("daily")
            self.app.notify("Backup completed", severity="information")
            self.refresh_data()
        except Exception as e:
            self.app.notify(f"Backup failed: {e}", severity="error")
