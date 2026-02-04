"""Stack info screen for TUI."""

import asyncio

from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import ScrollableContainer, Vertical
from textual.screen import Screen
from textual.timer import Timer
from textual.widgets import DataTable, Footer, Static
from textual.worker import get_current_worker

from surek.core.config import load_config
from surek.core.docker import get_stack_status_detailed
from surek.core.variables import expand_variables
from surek.exceptions import SurekError
from surek.models.stack import StackConfig
from surek.tui.widgets import LogsPanel, TopBar
from surek.utils.logging import format_bytes
from surek.utils.paths import get_stack_volumes_dir


class StackInfoScreen(Screen[None]):
    """Screen showing detailed information about a stack."""

    BINDINGS = [
        Binding("escape", "pop_screen", "Back"),
        Binding("q", "pop_screen", "Back"),
        Binding("r", "refresh", "Refresh"),
        Binding("l", "toggle_logs_fullscreen", "Fullscreen logs"),
        Binding("f", "toggle_follow", "Follow logs"),
        Binding("w", "toggle_wrap", "Wrap logs"),
    ]

    CSS = """
    StackInfoScreen {
        background: $surface;
        layout: vertical;
    }

    #info-container {
        height: auto;
        max-height: 50%;
        margin-top: 1;
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

    #logs-section-title {
        height: auto;
    }

    #logs-panel {
        width: 100%;
        height: 1fr;
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
        self._logs_fullscreen = False
        self._stats_timer: Timer | None = None

    def compose(self) -> ComposeResult:
        yield TopBar(f"Stack: {self.stack_config.name}", show_back=True)

        with ScrollableContainer(id="info-container"):
            yield Static("Stack Information", classes="section-title")
            yield Static("Loading...", id="stack-info", classes="info-row")

            yield Static("Endpoints", classes="section-title")
            yield Static(id="endpoints-info", classes="info-row")

            yield Static("Services", classes="section-title")
            yield DataTable(id="services-table", zebra_stripes=True)

            yield Static("Volumes", classes="section-title")
            with Vertical(id="volumes-container"):
                yield Static(id="volumes-info")

        # Logs section - outside ScrollableContainer to take remaining space
        yield Static("Logs", classes="section-title", id="logs-section-title")
        yield LogsPanel(stack_name=self.stack_config.name, id="logs-panel")

        yield Footer()

    def on_top_bar_back_pressed(self, event: TopBar.BackPressed) -> None:
        self.action_pop_screen()

    def on_mount(self) -> None:
        self._setup_services_table()
        self._refresh_stack_info_basic()
        self._refresh_endpoints()
        self._refresh_volumes()
        # Load stats in background
        self.run_worker(self._load_stats_async(), exclusive=True)
        # Auto-refresh stats every 2 seconds
        self._stats_timer = self.set_interval(2, self._refresh_stats)

    def _refresh_stats(self) -> None:
        self.run_worker(self._load_stats_async(), exclusive=True)

    def _setup_services_table(self) -> None:
        table = self.query_one("#services-table", DataTable)
        table.cursor_type = "row"
        table.add_columns("Service", "Status", "Health", "CPU", "Memory")
        table.add_row("Loading...", "-", "-", "-", "-", key="loading")

    def _refresh_stack_info_basic(self) -> None:
        config = self.stack_config
        status = get_stack_status_detailed(config.name, include_stats=False)

        info_text = (
            f"Name: {config.name}\n"
            f"Status: {status.status_text}\n"
            f"Source: {config.source.type}\n"
            f"Compose: {config.compose_file_path}"
        )

        self.query_one("#stack-info", Static).update(info_text)

    def _refresh_endpoints(self) -> None:
        config = self.stack_config

        if not config.public:
            self.query_one("#endpoints-info", Static).update("No public endpoints configured")
            return

        try:
            surek_config = load_config()
            text = Text()
            for i, ep in enumerate(config.public):
                url = f"https://{expand_variables(ep.domain, surek_config)}"
                if i > 0:
                    text.append("\n")
                text.append("  ")
                text.append(url, style=f"link {url}")
                text.append(f" -> {ep.target}")
        except SurekError:
            text = Text()
            for i, ep in enumerate(config.public):
                if i > 0:
                    text.append("\n")
                text.append(f"  {ep.domain} -> {ep.target}")

        self.query_one("#endpoints-info", Static).update(text)

    async def _load_stats_async(self) -> None:
        worker = get_current_worker()

        def get_stats() -> tuple[str, list[tuple[str, str, str, str, str]], list[str]]:
            config = self.stack_config
            status = get_stack_status_detailed(config.name, include_stats=True)

            info_text = (
                f"Name: {config.name}\n"
                f"Status: {status.status_text}\n"
                f"Source: {config.source.type}\n"
                f"Compose: {config.compose_file_path}"
            )

            rows: list[tuple[str, str, str, str, str]] = []
            service_names: list[str] = []
            for service in status.services:
                service_names.append(service.name)
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

                rows.append(
                    (
                        service.name,
                        status_text,
                        health_text,
                        f"{service.cpu_percent:.1f}%",
                        format_bytes(service.memory_bytes),
                    )
                )

            return info_text, rows, service_names

        info_text, rows, service_names = await asyncio.to_thread(get_stats)

        if worker.is_cancelled:
            return

        self.query_one("#stack-info", Static).update(info_text)

        table = self.query_one("#services-table", DataTable)
        table.clear()
        if rows:
            for row in rows:
                table.add_row(*row, key=row[0])
        else:
            table.add_row("No services found", "-", "-", "-", "-", key="empty")

        if service_names:
            await self.query_one("#logs-panel", LogsPanel).update_services(service_names)

    def _refresh_volumes(self) -> None:
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

    def action_refresh(self) -> None:
        self._refresh_stack_info_basic()
        self._refresh_endpoints()
        self._refresh_volumes()
        self.query_one("#logs-panel", LogsPanel).refresh_logs()
        self.run_worker(self._load_stats_async(), exclusive=True)
        self.notify("Data refreshed")

    def action_toggle_logs_fullscreen(self) -> None:
        self._logs_fullscreen = not self._logs_fullscreen

        # Hide/show info container in fullscreen mode (keep logs title visible)
        info_container = self.query_one("#info-container")
        info_container.display = not self._logs_fullscreen

    def action_toggle_follow(self) -> None:
        is_following = self.query_one("#logs-panel", LogsPanel).toggle_follow()
        title = self.query_one("#logs-section-title", Static)
        if is_following:
            title.update("Logs [green](following)[/green]")
        else:
            title.update("Logs")

    def action_toggle_wrap(self) -> None:
        self.query_one("#logs-panel", LogsPanel).toggle_wrap()

    def action_pop_screen(self) -> None:
        if self._stats_timer:
            self._stats_timer.stop()
        self.query_one("#logs-panel", LogsPanel).stop_following()
        self.app.pop_screen()
