"""Stacks screen for TUI."""

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Container
from textual.widgets import DataTable, Static

from surek.core.docker import get_stack_status_detailed
from surek.core.stacks import get_available_stacks
from surek.exceptions import SurekError


class StacksPane(Container):
    """Pane showing all stacks and their status."""

    BINDINGS = [
        Binding("d", "deploy", "Deploy"),
        Binding("s", "start", "Start"),
        Binding("x", "stop", "Stop"),
        Binding("i", "info", "Info"),
    ]

    def compose(self) -> ComposeResult:
        """Compose the stacks pane."""
        yield Static("Stacks", classes="title")
        yield DataTable(id="stacks-table")

    def on_mount(self) -> None:
        """Initialize the table when mounted."""
        table = self.query_one("#stacks-table", DataTable)
        table.cursor_type = "row"
        table.add_columns("Stack", "Status", "Health", "Path")
        self.refresh_data()

    def refresh_data(self) -> None:
        """Refresh the stacks data."""
        table = self.query_one("#stacks-table", DataTable)
        table.clear()

        # System status
        try:
            system_status = get_stack_status_detailed("surek-system")
            table.add_row(
                "System",
                system_status.status_text,
                system_status.health_summary,
                "",
                key="surek-system",
            )
        except Exception:
            table.add_row(
                "System",
                "? Unknown",
                "-",
                "",
                key="surek-system",
            )

        # User stacks
        try:
            stacks = get_available_stacks()
            for stack in stacks:
                if not stack.valid:
                    table.add_row(
                        str(stack.path.parent.name),
                        "Invalid config",
                        "-",
                        str(stack.path.parent.name),
                        key=f"invalid-{stack.path}",
                    )
                    continue

                if stack.config:
                    status = get_stack_status_detailed(stack.config.name)
                    table.add_row(
                        stack.config.name,
                        status.status_text,
                        status.health_summary,
                        str(stack.path.parent.name),
                        key=stack.config.name,
                    )
        except SurekError:
            pass  # No stacks directory

    def _get_selected_stack(self) -> str | None:
        """Get the name of the currently selected stack."""
        table: DataTable[str] = self.query_one("#stacks-table", DataTable)
        if table.cursor_row is not None:
            row_key = table.get_row_at(table.cursor_row)
            if row_key:
                # First column is the name
                coord = (table.cursor_row, 0)
                return str(table.get_cell_at(coord))  # type: ignore[arg-type]
        return None

    def action_deploy(self) -> None:
        """Deploy the selected stack."""
        stack_name = self._get_selected_stack()
        if not stack_name or stack_name == "System":
            self.app.notify("Select a user stack to deploy", severity="warning")
            return

        self.app.notify(f"Deploying {stack_name}...", timeout=2)

        # Run deployment in background
        self.run_worker(self._deploy_stack(stack_name))

    async def _deploy_stack(self, stack_name: str) -> None:
        """Deploy a stack asynchronously."""
        try:
            from surek.core.config import load_config
            from surek.core.deploy import deploy_stack
            from surek.core.stacks import get_stack_by_name

            config = load_config()
            stack = get_stack_by_name(stack_name)
            deploy_stack(stack, config)
            self.app.notify(f"Deployed {stack_name}", severity="information")
            self.refresh_data()
        except Exception as e:
            self.app.notify(f"Deploy failed: {e}", severity="error")

    def action_start(self) -> None:
        """Start the selected stack."""
        stack_name = self._get_selected_stack()
        if not stack_name:
            return

        self.app.notify(f"Starting {stack_name}...", timeout=2)
        self.run_worker(self._start_stack(stack_name))

    async def _start_stack(self, stack_name: str) -> None:
        """Start a stack asynchronously."""
        try:
            from surek.core.deploy import start_stack
            from surek.core.stacks import get_stack_by_name

            if stack_name == "System":
                from surek.core.config import load_config
                from surek.core.deploy import deploy_system_stack
                from surek.core.docker import ensure_surek_network

                config = load_config()
                ensure_surek_network()
                deploy_system_stack(config)
            else:
                stack = get_stack_by_name(stack_name)
                if stack.config:
                    start_stack(stack.config)

            self.app.notify(f"Started {stack_name}", severity="information")
            self.refresh_data()
        except Exception as e:
            self.app.notify(f"Start failed: {e}", severity="error")

    def action_stop(self) -> None:
        """Stop the selected stack."""
        stack_name = self._get_selected_stack()
        if not stack_name:
            return

        self.app.notify(f"Stopping {stack_name}...", timeout=2)
        self.run_worker(self._stop_stack(stack_name))

    async def _stop_stack(self, stack_name: str) -> None:
        """Stop a stack asynchronously."""
        try:
            from surek.core.deploy import stop_stack
            from surek.core.stacks import get_stack_by_name

            if stack_name == "System":
                from surek.core.config import load_stack_config
                from surek.utils.paths import get_system_dir

                system_dir = get_system_dir()
                system_config = load_stack_config(system_dir / "surek.stack.yml")
                stop_stack(system_config, silent=False)
            else:
                stack = get_stack_by_name(stack_name)
                if stack.config:
                    stop_stack(stack.config, silent=False)

            self.app.notify(f"Stopped {stack_name}", severity="information")
            self.refresh_data()
        except Exception as e:
            self.app.notify(f"Stop failed: {e}", severity="error")

    def action_info(self) -> None:
        """Show info for the selected stack."""
        # TODO: pressing `i` on stack shows simple notification, while we should redirect user to separate screen with
        # detailed info about stack, services in it, associated volumes and their stats, and stream logs for stack
        stack_name = self._get_selected_stack()
        if not stack_name or stack_name == "System":
            return

        try:
            from surek.core.stacks import get_stack_by_name

            stack = get_stack_by_name(stack_name)
            if stack.config:
                status = get_stack_status_detailed(stack.config.name)
                info_text = (
                    f"Stack: {stack.config.name}\n"
                    f"Status: {status.status_text}\n"
                    f"Source: {stack.config.source.type}\n"
                    f"Services: {len(status.services)}"
                )
                self.app.notify(info_text, title="Stack Info", timeout=10)
        except Exception as e:
            self.app.notify(f"Error: {e}", severity="error")
