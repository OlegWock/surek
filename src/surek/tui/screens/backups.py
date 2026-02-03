"""Backups screen for TUI."""

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Container
from textual.widgets import DataTable

from surek.core.backup import format_bytes, list_backups, trigger_backup
from surek.core.config import load_config
from surek.exceptions import SurekError

# Row height for table padding (1 = default, 3 = extra vertical space)
ROW_HEIGHT = 3
CELL_PADDING = "  "  # Horizontal padding for cells


def _centered(text: str) -> str:
    """Center text vertically and add horizontal padding."""
    return f"\n{CELL_PADDING}{text}{CELL_PADDING}\n"


class BackupsPane(Container):
    """Pane showing available backups."""

    BINDINGS = [
        Binding("b", "run_backup", "Run Backup"),
    ]

    def compose(self) -> ComposeResult:
        """Compose the backups pane."""
        yield DataTable(id="backups-table", zebra_stripes=True)

    def on_mount(self) -> None:
        """Initialize the table when mounted."""
        table = self.query_one("#backups-table", DataTable)
        table.cursor_type = "row"
        table.header_height = ROW_HEIGHT
        table.add_columns(
            _centered("Backup"),
            _centered("Type"),
            _centered("Size"),
            _centered("Created"),
        )
        self.refresh_data()

    def refresh_data(self) -> None:
        """Refresh the backups data."""
        table = self.query_one("#backups-table", DataTable)
        table.clear()

        try:
            config = load_config()

            if not config.backup:
                table.add_row(
                    _centered("Backup not configured"),
                    _centered("-"),
                    _centered("-"),
                    _centered("-"),
                    key="not-configured",
                    height=ROW_HEIGHT,
                )
                return

            backups = list_backups(config.backup)

            if not backups:
                table.add_row(
                    _centered("No backups found"),
                    _centered("-"),
                    _centered("-"),
                    _centered("-"),
                    key="empty",
                    height=ROW_HEIGHT,
                )
                return

            for backup in backups[:50]:  # Limit to 50 for performance
                table.add_row(
                    _centered(backup.name),
                    _centered(backup.backup_type.capitalize()),
                    _centered(format_bytes(backup.size)),
                    _centered(backup.created.strftime("%Y-%m-%d %H:%M")),
                    key=backup.name,
                    height=ROW_HEIGHT,
                )

        except SurekError as e:
            table.add_row(
                _centered(f"Error: {e}"),
                _centered("-"),
                _centered("-"),
                _centered("-"),
                key="error",
                height=ROW_HEIGHT,
            )
        except Exception as e:
            table.add_row(
                _centered(f"Error: {e}"),
                _centered("-"),
                _centered("-"),
                _centered("-"),
                key="error",
                height=ROW_HEIGHT,
            )

    def action_run_backup(self) -> None:
        """Trigger a manual backup."""
        self.app.notify("Starting backup...", timeout=2)
        self.run_worker(self._run_backup())

    async def _run_backup(self) -> None:
        """Run backup asynchronously."""
        try:
            trigger_backup()
            self.app.notify("Backup completed", severity="information")
            self.refresh_data()
        except Exception as e:
            self.app.notify(f"Backup failed: {e}", severity="error")
