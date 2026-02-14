"""Logs panel widget with tabbed interface."""

import asyncio
import subprocess
from enum import Enum, auto
from pathlib import Path

from textual.app import ComposeResult
from textual.widget import Widget
from textual.widgets import Input, RichLog, TabbedContent, TabPane
from textual.worker import Worker, get_current_worker

from surek.core.docker import run_docker_compose
from surek.exceptions import SurekError
from surek.utils.paths import get_stack_project_dir


class _UseCurrentTab(Enum):
    """Sentinel value to indicate using current tab."""

    TOKEN = auto()


_USE_CURRENT_TAB = _UseCurrentTab.TOKEN


class LogsPanel(Widget):
    """Logs panel with tabs for each service."""

    DEFAULT_CSS = """
    LogsPanel {
        width: 100%;
        height: 100%;
        padding: 0 1;
    }

    LogsPanel #logs-filter {
        width: 100%;
        border: solid $primary-darken-2;
        margin-bottom: 1;
    }

    LogsPanel ContentSwitcher {
        width: 100%;
        height: 1fr;
    }

    LogsPanel TabPane {
        width: 100%;
        height: 100%;
    }

    LogsPanel RichLog {
        width: 100%;
        height: 1fr;
        border: solid $primary-darken-2;
    }
    """

    def __init__(
        self,
        stack_name: str,
        services: list[str] | None = None,
        name: str | None = None,
        id: str | None = None,
        classes: str | None = None,
    ) -> None:
        """Initialize the logs panel.

        Args:
            stack_name: Name of the stack.
            services: List of service names. If None, only "All" tab is shown.
            name: Optional widget name.
            id: Optional widget ID.
            classes: Optional CSS classes.
        """
        super().__init__(name=name, id=id, classes=classes)
        self._stack_name = stack_name
        self._services = services or []
        self._log_filter = ""
        self._follow_logs = False
        self._wrap_logs = False
        self._follow_worker: Worker[None] | None = None
        self._current_service: str | None = None  # None means "All"

    def compose(self) -> ComposeResult:
        yield Input(placeholder="Filter logs...", id="logs-filter")

        with TabbedContent():
            with TabPane("All", id="logs-tab-all"):
                yield RichLog(id="log-all", highlight=True, wrap=False)
            for service in self._services:
                with TabPane(service, id=f"logs-tab-{service}"):
                    yield RichLog(id=f"log-{service}", highlight=True, wrap=False)

    def on_mount(self) -> None:
        self._load_logs(_USE_CURRENT_TAB)

    def _get_compose_paths(self) -> tuple[Path, Path] | None:
        project_dir = get_stack_project_dir(self._stack_name)
        compose_file = project_dir / "docker-compose.surek.yml"
        if not compose_file.exists():
            return None
        return project_dir, compose_file

    def _get_current_log_widget(self) -> RichLog:
        service = self._get_current_service()
        log_id = "log-all" if service is None else f"log-{service}"
        return self.query_one(f"#{log_id}", RichLog)

    def _get_current_service(self) -> str | None:
        tabbed = self.query_one(TabbedContent)
        active_tab = tabbed.active
        if active_tab == "logs-tab-all":
            return None
        return active_tab.replace("logs-tab-", "")

    @staticmethod
    def _extract_timestamp(line: str) -> str:
        """Extract timestamp from log line for sorting.

        Log format: 'container-name  | 2024-01-15T10:30:45.123456789Z message'
        Returns the timestamp or empty string if not found.
        """
        try:
            # Find the timestamp after the pipe separator
            if " | " in line:
                after_pipe = line.split(" | ", 1)[1]
                # Timestamp is at the start, format: 2024-01-15T10:30:45.123456789Z
                if len(after_pipe) > 30 and after_pipe[4] == "-" and after_pipe[10] == "T":
                    return after_pipe[:30]
        except Exception:
            pass
        return ""

    def _load_logs(self, service: str | None | _UseCurrentTab = _USE_CURRENT_TAB) -> None:
        if isinstance(service, _UseCurrentTab):
            service = self._get_current_service()

        log_id = "log-all" if service is None else f"log-{service}"
        try:
            log_widget = self.query_one(f"#{log_id}", RichLog)
        except Exception:
            return

        log_widget.clear()

        paths = self._get_compose_paths()
        if not paths:
            log_widget.write("Stack not deployed - no logs available")
            return

        project_dir, compose_file = paths

        try:
            # Use timestamps for proper chronological sorting
            args = ["--tail", "100", "--no-color", "--timestamps"]
            if service:
                args.append(service)

            output = run_docker_compose(
                compose_file=compose_file,
                project_dir=project_dir,
                command="logs",
                args=args,
                capture_output=True,
                silent=True,
            )

            if output.strip():
                # Sort lines by timestamp for chronological order
                lines = output.strip().split("\n")
                lines.sort(key=self._extract_timestamp)

                for line in lines:
                    if self._log_filter and self._log_filter.lower() not in line.lower():
                        continue
                    log_widget.write(line)
            else:
                log_widget.write("No logs available")

        except SurekError as e:
            log_widget.write(f"Error fetching logs: {e}")

    def refresh_logs(self) -> None:
        self._load_logs(_USE_CURRENT_TAB)

    def on_tabbed_content_tab_activated(self, event: TabbedContent.TabActivated) -> None:
        service = self._get_current_service()

        if self._follow_worker:
            self._follow_worker.cancel()
            self._follow_worker = None
            self._follow_logs = False

        self._load_logs(service)

    def on_input_changed(self, event: Input.Changed) -> None:
        if event.input.id == "logs-filter":
            self._log_filter = event.value
            if not self._follow_logs:
                self._load_logs()

    def toggle_follow(self) -> bool:
        self._follow_logs = not self._follow_logs

        if self._follow_logs:
            self._follow_worker = self.run_worker(self._follow_logs_stream())
        else:
            if self._follow_worker:
                self._follow_worker.cancel()
                self._follow_worker = None

        return self._follow_logs

    @property
    def is_following(self) -> bool:
        return self._follow_logs

    def toggle_wrap(self) -> None:
        self._wrap_logs = not self._wrap_logs
        for log_widget in self.query(RichLog):
            log_widget.wrap = self._wrap_logs

        self._load_logs(_USE_CURRENT_TAB)

    async def _follow_logs_stream(self) -> None:
        paths = self._get_compose_paths()
        if not paths:
            return

        project_dir, compose_file = paths
        service = self._get_current_service()
        log_widget = self._get_current_log_widget()

        cmd = [
            "docker",
            "compose",
            "--file",
            str(compose_file),
            "--project-directory",
            str(project_dir),
            "logs",
            "--follow",
            "--tail",
            "0",
            "--no-color",
        ]
        if service:
            cmd.append(service)

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
                log_widget.write(text)

            process.terminate()
            await process.wait()

        except Exception as e:
            log_widget.write(f"Log streaming error: {e}")

    def stop_following(self) -> None:
        if self._follow_worker:
            self._follow_worker.cancel()
            self._follow_worker = None

    async def update_services(self, services: list[str]) -> None:
        tabbed = self.query_one(TabbedContent)

        for service in services:
            if service not in self._services:
                tab_pane = TabPane(service, id=f"logs-tab-{service}")
                log_widget = RichLog(id=f"log-{service}", highlight=True, wrap=self._wrap_logs)
                await tabbed.add_pane(tab_pane)
                await tab_pane.mount(log_widget)

        self._services = services
