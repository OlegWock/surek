"""Stack info screen for TUI."""

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import ScrollableContainer, Vertical
from textual.screen import Screen
from textual.widgets import DataTable, Footer, Header, Log, Static

from surek.core.docker import format_bytes, get_stack_status_detailed
from surek.exceptions import SurekError
from surek.models.stack import StackConfig
from surek.utils.paths import get_stack_project_dir, get_stack_volumes_dir


class StackInfoScreen(Screen[None]):
    """Screen showing detailed information about a stack."""

    BINDINGS = [
        Binding("escape", "pop_screen", "Back"),
        Binding("q", "pop_screen", "Back"),
        Binding("r", "refresh", "Refresh"),
        Binding("l", "toggle_logs", "Toggle Logs"),
    ]

    CSS = """
    StackInfoScreen {
        background: $surface;
    }

    .section-title {
        text-style: bold;
        padding: 1 0 0 1;
        color: $primary;
    }

    .info-row {
        padding: 0 1;
    }

    #services-table {
        height: auto;
        max-height: 12;
        margin: 0 1;
    }

    #volumes-container {
        padding: 0 1;
        height: auto;
    }

    #logs-container {
        height: 1fr;
        padding: 0 1;
    }

    #logs-widget {
        height: 100%;
        border: solid $primary;
    }
    """

    def __init__(self, stack_config: StackConfig, name: str | None = None) -> None:
        """Initialize the stack info screen.

        Args:
            stack_config: The stack configuration.
            name: Optional screen name.
        """
        super().__init__(name=name)
        self.stack_config = stack_config
        self._show_logs = True

    def compose(self) -> ComposeResult:
        """Compose the screen layout."""
        yield Header()

        with ScrollableContainer():
            # Stack info section
            yield Static("Stack Information", classes="section-title")
            yield Static(id="stack-info", classes="info-row")

            # Services section
            yield Static("Services", classes="section-title")
            yield DataTable(id="services-table")

            # Volumes section
            yield Static("Volumes", classes="section-title")
            with Vertical(id="volumes-container"):
                yield Static(id="volumes-info")

            # Logs section
            yield Static("Recent Logs", classes="section-title")
            with Vertical(id="logs-container"):
                yield Log(id="logs-widget", highlight=True)

        yield Footer()

    def on_mount(self) -> None:
        """Initialize the screen when mounted."""
        self.sub_title = f"Stack: {self.stack_config.name}"
        self._setup_services_table()
        self.refresh_data()
        self._load_logs()

    def _setup_services_table(self) -> None:
        """Set up the services data table."""
        table = self.query_one("#services-table", DataTable)
        table.cursor_type = "row"
        table.add_columns("Service", "Status", "Health", "CPU", "Memory")

    def refresh_data(self) -> None:
        """Refresh all data on the screen."""
        self._refresh_stack_info()
        self._refresh_services()
        self._refresh_volumes()

    def _refresh_stack_info(self) -> None:
        """Refresh the stack info section."""
        config = self.stack_config
        status = get_stack_status_detailed(config.name, include_stats=True)

        info_text = (
            f"Name: {config.name}\n"
            f"Status: {status.status_text}\n"
            f"Source: {config.source.type}\n"
            f"Compose: {config.compose_file_path}"
        )

        if config.public:
            endpoints = [f"  - {ep.domain} -> {ep.target}" for ep in config.public]
            info_text += "\nEndpoints:\n" + "\n".join(endpoints)

        self.query_one("#stack-info", Static).update(info_text)

    def _refresh_services(self) -> None:
        """Refresh the services table."""
        table = self.query_one("#services-table", DataTable)
        table.clear()

        try:
            status = get_stack_status_detailed(self.stack_config.name, include_stats=True)

            for service in status.services:
                status_text = service.status
                if service.status == "running":
                    status_text = f"[green]{status_text}[/green]"
                elif service.status == "exited":
                    status_text = f"[red]{status_text}[/red]"

                health_text = service.health or "-"
                if service.health == "healthy":
                    health_text = f"[green]{health_text}[/green]"
                elif service.health == "unhealthy":
                    health_text = f"[red]{health_text}[/red]"

                table.add_row(
                    service.name,
                    status_text,
                    health_text,
                    f"{service.cpu_percent:.1f}%",
                    format_bytes(service.memory_bytes),
                    key=service.name,
                )

            if not status.services:
                table.add_row("No services found", "-", "-", "-", "-", key="empty")

        except SurekError as e:
            table.add_row(f"Error: {e}", "-", "-", "-", "-", key="error")

    def _refresh_volumes(self) -> None:
        """Refresh the volumes section."""
        volumes_dir = get_stack_volumes_dir(self.stack_config.name)

        if volumes_dir.exists():
            volumes = list(volumes_dir.iterdir())
            if volumes:
                volume_lines = [f"  - {v.name}" for v in sorted(volumes)]
                text = f"Location: {volumes_dir}\n" + "\n".join(volume_lines)
            else:
                text = f"Location: {volumes_dir}\n  (no volumes)"
        else:
            text = "No volumes directory"

        self.query_one("#volumes-info", Static).update(text)

    def _load_logs(self) -> None:
        """Load recent logs into the log widget."""
        log_widget = self.query_one("#logs-widget", Log)
        log_widget.clear()

        project_dir = get_stack_project_dir(self.stack_config.name)
        compose_file = project_dir / "docker-compose.surek.yml"

        if not compose_file.exists():
            log_widget.write_line("[dim]Stack not deployed - no logs available[/dim]")
            return

        try:
            from surek.core.docker import run_docker_compose

            output = run_docker_compose(
                compose_file=compose_file,
                project_dir=project_dir,
                command="logs",
                args=["--tail", "100", "--no-color"],
                capture_output=True,
                silent=True,
            )

            if output.strip():
                for line in output.strip().split("\n"):
                    log_widget.write_line(line)
            else:
                log_widget.write_line("[dim]No logs available[/dim]")

        except SurekError as e:
            log_widget.write_line(f"[red]Error fetching logs: {e}[/red]")

    def action_refresh(self) -> None:
        """Refresh all data."""
        self.refresh_data()
        self._load_logs()
        self.notify("Data refreshed")

    def action_toggle_logs(self) -> None:
        """Toggle logs visibility."""
        logs_container = self.query_one("#logs-container")
        self._show_logs = not self._show_logs
        logs_container.display = self._show_logs

    def action_pop_screen(self) -> None:
        """Go back to the previous screen."""
        self.app.pop_screen()
