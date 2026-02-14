"""Stacks screen for TUI."""

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Container
from textual.events import Click
from textual.message import Message
from textual.widgets import DataTable

from surek.core.config import load_config, load_stack_config
from surek.core.deploy import deploy_stack, deploy_system_stack, start_stack, stop_stack
from surek.core.docker import ensure_surek_network, get_stack_status_detailed
from surek.core.stacks import SYSTEM_STACK_NAME, get_available_stacks, get_stack_by_name
from surek.exceptions import SurekError
from surek.tui.screens.stack_info import StackInfoScreen
from surek.utils.paths import get_system_dir

# Row height for table padding (1 = default, 3 = extra vertical space)
ROW_HEIGHT = 3
CELL_PADDING = "  "  # Horizontal padding for cells


def _centered(text: str) -> str:
    """Center text vertically and add horizontal padding."""
    return f"\n{CELL_PADDING}{text}{CELL_PADDING}\n"


class ClickableDataTable(DataTable[str]):
    """DataTable that emits double-click events."""

    class DoubleClicked(Message):
        """Message sent when table is double-clicked."""

        pass

    def on_click(self, event: Click) -> None:
        if event.chain == 2:  # Double click
            self.post_message(self.DoubleClicked())


class StacksPane(Container):
    """Pane showing all stacks and their status."""

    BINDINGS = [
        Binding("d", "deploy", "Deploy"),
        Binding("s", "start", "Start"),
        Binding("x", "stop", "Stop"),
        Binding("i", "info", "Info"),
        Binding("right", "info", "Info", show=False),
        Binding("enter", "info", "Info", show=False),
    ]

    def compose(self) -> ComposeResult:
        yield ClickableDataTable(id="stacks-table", zebra_stripes=True)

    def on_mount(self) -> None:
        table = self.query_one("#stacks-table", DataTable)
        table.cursor_type = "row"
        table.header_height = ROW_HEIGHT
        table.add_columns(
            _centered("Stack"),
            _centered("Status"),
            _centered("Health"),
            _centered("Path"),
        )
        self.refresh_data()

    def refresh_data(self) -> None:
        table = self.query_one("#stacks-table", DataTable)
        table.clear()

        try:
            system_status = get_stack_status_detailed(SYSTEM_STACK_NAME)
            table.add_row(
                _centered("System"),
                _centered(system_status.status_text),
                _centered(system_status.health_summary),
                _centered(""),
                key=SYSTEM_STACK_NAME,
                height=ROW_HEIGHT,
            )
        except Exception:
            table.add_row(
                _centered("System"),
                _centered("? Unknown"),
                _centered("-"),
                _centered(""),
                key=SYSTEM_STACK_NAME,
                height=ROW_HEIGHT,
            )

        try:
            stacks = get_available_stacks()
            for stack in stacks:
                if not stack.valid:
                    table.add_row(
                        _centered(str(stack.path.parent.name)),
                        _centered("Invalid config"),
                        _centered("-"),
                        _centered(str(stack.path.parent.name)),
                        key=f"invalid-{stack.path}",
                        height=ROW_HEIGHT,
                    )
                    continue

                if stack.config:
                    status = get_stack_status_detailed(stack.config.name)
                    table.add_row(
                        _centered(stack.config.name),
                        _centered(status.status_text),
                        _centered(status.health_summary),
                        _centered(str(stack.path.parent.name)),
                        key=stack.config.name,
                        height=ROW_HEIGHT,
                    )
        except SurekError:
            pass  # No stacks directory

    def _get_selected_stack(self) -> str | None:
        table: DataTable[str] = self.query_one("#stacks-table", DataTable)
        if table.cursor_row is not None:
            row_key = table.get_row_at(table.cursor_row)
            if row_key:
                # First column is the name (strip centering newlines)
                coord = (table.cursor_row, 0)
                return str(table.get_cell_at(coord)).strip()  # type: ignore[arg-type]
        return None

    def action_deploy(self) -> None:
        stack_name = self._get_selected_stack()
        if not stack_name or stack_name == "System":
            self.app.notify("Select a user stack to deploy", severity="warning")
            return

        self.app.notify(f"Deploying {stack_name}...", timeout=2)

        # Run deployment in background
        self.run_worker(self._deploy_stack(stack_name))

    async def _deploy_stack(self, stack_name: str) -> None:
        try:
            config = load_config()
            stack = get_stack_by_name(stack_name)
            deploy_stack(stack, config)
            self.app.notify(f"Deployed {stack_name}", severity="information")
            self.refresh_data()
        except Exception as e:
            self.app.notify(f"Deploy failed: {e}", severity="error")

    def action_start(self) -> None:
        stack_name = self._get_selected_stack()
        if not stack_name:
            return

        self.app.notify(f"Starting {stack_name}...", timeout=2)
        self.run_worker(self._start_stack(stack_name))

    async def _start_stack(self, stack_name: str) -> None:
        try:
            if stack_name == "System":
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
        stack_name = self._get_selected_stack()
        if not stack_name:
            return

        self.app.notify(f"Stopping {stack_name}...", timeout=2)
        self.run_worker(self._stop_stack(stack_name))

    async def _stop_stack(self, stack_name: str) -> None:
        try:
            if stack_name == "System":
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

    def on_clickable_data_table_double_clicked(
        self, event: ClickableDataTable.DoubleClicked
    ) -> None:
        self.action_info()

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        self.action_info()

    def action_info(self) -> None:
        stack_name = self._get_selected_stack()
        if not stack_name:
            self.app.notify("Select a stack to view info", severity="warning")
            return

        try:
            if stack_name == "System":
                system_dir = get_system_dir()
                system_config = load_stack_config(system_dir / "surek.stack.yml")
                self.app.push_screen(StackInfoScreen(system_config))
            else:
                stack = get_stack_by_name(stack_name)
                if stack.config:
                    self.app.push_screen(StackInfoScreen(stack.config))
        except Exception as e:
            self.app.notify(f"Error: {e}", severity="error")
