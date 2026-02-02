"""Stack info screen for TUI."""

import asyncio
from pathlib import Path

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, ScrollableContainer, Vertical
from textual.screen import Screen
from textual.widgets import DataTable, Footer, Header, Input, Log, Static
from textual.worker import Worker, get_current_worker

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
        Binding("l", "toggle_logs", "Toggle logs"),
        Binding("f", "toggle_follow", "Follow logs"),
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

    #logs-header {
        height: auto;
        padding: 0 1;
    }

    #logs-filter {
        width: 30;
        margin-right: 1;
    }

    #follow-status {
        width: auto;
        padding: 0 1;
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
        self._follow_logs = False
        self._follow_worker: Worker[None] | None = None
        self._log_filter = ""

    def compose(self) -> ComposeResult:
        """Compose the screen layout."""
        yield Header()

        with ScrollableContainer():
            # Stack info section
            yield Static("Stack Information", classes="section-title")
            yield Static("Loading...", id="stack-info", classes="info-row")

            # Services section
            yield Static("Services", classes="section-title")
            yield DataTable(id="services-table")

            # Volumes section
            yield Static("Volumes", classes="section-title")
            with Vertical(id="volumes-container"):
                yield Static(id="volumes-info")

            # Logs section
            yield Static("Logs", classes="section-title")
            with Horizontal(id="logs-header"):
                yield Input(placeholder="Filter logs...", id="logs-filter")
                yield Static("[dim]Follow: OFF[/dim]", id="follow-status")
            with Vertical(id="logs-container"):
                yield Log(id="logs-widget", highlight=True)

        yield Footer()

    def on_mount(self) -> None:
        """Initialize the screen when mounted."""
        self.sub_title = f"Stack: {self.stack_config.name}"
        self._setup_services_table()
        # Load basic info immediately, stats in background
        self._refresh_stack_info_basic()
        self._refresh_volumes()
        self._load_logs()
        # Load stats in background
        self.run_worker(self._load_stats_async(), exclusive=True)

    def _setup_services_table(self) -> None:
        """Set up the services data table."""
        table = self.query_one("#services-table", DataTable)
        table.cursor_type = "row"
        table.add_columns("Service", "Status", "Health", "CPU", "Memory")
        table.add_row("Loading...", "-", "-", "-", "-", key="loading")

    def _refresh_stack_info_basic(self) -> None:
        """Refresh the stack info section without stats."""
        config = self.stack_config
        status = get_stack_status_detailed(config.name, include_stats=False)

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

    async def _load_stats_async(self) -> None:
        """Load stats in background."""
        worker = get_current_worker()

        def get_stats() -> tuple[str, list[tuple[str, str, str, str, str]]]:
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

            rows: list[tuple[str, str, str, str, str]] = []
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

                rows.append((
                    service.name,
                    status_text,
                    health_text,
                    f"{service.cpu_percent:.1f}%",
                    format_bytes(service.memory_bytes),
                ))

            return info_text, rows

        # Run blocking code in thread
        info_text, rows = await asyncio.to_thread(get_stats)

        if worker.is_cancelled:
            return

        # Update UI
        self.query_one("#stack-info", Static).update(info_text)

        table = self.query_one("#services-table", DataTable)
        table.clear()
        if rows:
            for row in rows:
                table.add_row(*row, key=row[0])
        else:
            table.add_row("No services found", "-", "-", "-", "-", key="empty")

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

    def _get_compose_paths(self) -> tuple[Path, Path] | None:
        """Get project dir and compose file paths if they exist."""
        project_dir = get_stack_project_dir(self.stack_config.name)
        compose_file = project_dir / "docker-compose.surek.yml"
        if not compose_file.exists():
            return None
        return project_dir, compose_file

    def _load_logs(self) -> None:
        """Load recent logs into the log widget."""
        log_widget = self.query_one("#logs-widget", Log)
        log_widget.clear()

        paths = self._get_compose_paths()
        if not paths:
            log_widget.write_line("[dim]Stack not deployed - no logs available[/dim]")
            return

        project_dir, compose_file = paths

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
                    if self._log_filter and self._log_filter.lower() not in line.lower():
                        continue
                    log_widget.write_line(line)
            else:
                log_widget.write_line("[dim]No logs available[/dim]")

        except SurekError as e:
            log_widget.write_line(f"[red]Error fetching logs: {e}[/red]")

    async def _follow_logs_stream(self) -> None:
        """Stream logs in follow mode."""
        import subprocess

        paths = self._get_compose_paths()
        if not paths:
            return

        project_dir, compose_file = paths
        log_widget = self.query_one("#logs-widget", Log)

        cmd = [
            "docker", "compose",
            "--file", str(compose_file),
            "--project-directory", str(project_dir),
            "logs", "--follow", "--tail", "0", "--no-color",
        ]

        try:
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
            )

            worker = get_current_worker()

            while not worker.is_cancelled:
                if process.stdout is None:
                    break
                line = await process.stdout.readline()
                if not line:
                    break
                text = line.decode().rstrip()
                if self._log_filter and self._log_filter.lower() not in text.lower():
                    continue
                log_widget.write_line(text)

            process.terminate()
            await process.wait()

        except Exception as e:
            log_widget.write_line(f"[red]Log streaming error: {e}[/red]")

    def on_input_changed(self, event: Input.Changed) -> None:
        """Handle filter input changes."""
        if event.input.id == "logs-filter":
            self._log_filter = event.value
            # Reload logs with new filter (only if not following)
            if not self._follow_logs:
                self._load_logs()

    def action_refresh(self) -> None:
        """Refresh all data."""
        self._refresh_stack_info_basic()
        self._refresh_volumes()
        self._load_logs()
        self.run_worker(self._load_stats_async(), exclusive=True)
        self.notify("Data refreshed")

    def action_toggle_logs(self) -> None:
        """Toggle logs visibility."""
        logs_container = self.query_one("#logs-container")
        logs_header = self.query_one("#logs-header")
        self._show_logs = not self._show_logs
        logs_container.display = self._show_logs
        logs_header.display = self._show_logs

    def action_toggle_follow(self) -> None:
        """Toggle log following mode."""
        self._follow_logs = not self._follow_logs
        status_widget = self.query_one("#follow-status", Static)

        if self._follow_logs:
            status_widget.update("[green]Follow: ON[/green]")
            self._follow_worker = self.run_worker(self._follow_logs_stream(), exclusive=True)
        else:
            status_widget.update("[dim]Follow: OFF[/dim]")
            if self._follow_worker:
                self._follow_worker.cancel()
                self._follow_worker = None

    def action_pop_screen(self) -> None:
        """Go back to the previous screen."""
        # Stop log following if active
        if self._follow_worker:
            self._follow_worker.cancel()
        self.app.pop_screen()
