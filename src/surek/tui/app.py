"""Main Textual TUI application."""

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.widgets import DataTable, Footer, TabbedContent, TabPane

from surek.tui.screens.backups import BackupsPane
from surek.tui.screens.stacks import StacksPane
from surek.tui.widgets import TopBar


class SurekApp(App[None]):
    """Main Surek TUI application."""

    TITLE = "Surek"
    SUB_TITLE = "Docker Compose Orchestration"

    CSS = """
    Screen {
        background: $surface;
        overflow: hidden;
    }

    #stacks-pane, #backups-pane {
        padding: 0;
    }

    TabbedContent {
        padding: 0 1;
        height: 1fr;
        margin-top: 1;
    }

    TabPane {
        padding: 1 0;
    }

    DataTable {
        height: 100%;
    }

    DataTable > .datatable--cursor {
        background: $primary 30%;
    }

    .title {
        text-style: bold;
        padding: 1 0;
        margin-bottom: 1;
    }

    .error {
        color: $error;
    }

    .success {
        color: $success;
    }

    .warning {
        color: $warning;
    }
    """

    BINDINGS = [
        Binding("q", "quit", "Quit"),
        Binding("r", "refresh", "Refresh"),
        Binding("?", "help", "Help"),
    ]

    def compose(self) -> ComposeResult:
        yield TopBar("Surek")
        with TabbedContent():
            with TabPane("Stacks", id="stacks-tab"):
                yield StacksPane(id="stacks-pane")
            with TabPane("Backups", id="backups-tab"):
                yield BackupsPane(id="backups-pane")
        yield Footer()

    def on_mount(self) -> None:
        self.query_one("#stacks-table", DataTable).focus()

    def action_refresh(self) -> None:
        stacks_pane = self.query_one("#stacks-pane", StacksPane)
        stacks_pane.refresh_data()

        backups_pane = self.query_one("#backups-pane", BackupsPane)
        backups_pane.refresh_data()

        self.notify("Data refreshed")

    def action_help(self) -> None:
        self.notify(
            "Keyboard shortcuts:\n"
            "  r - Refresh data\n"
            "  d - Deploy selected stack\n"
            "  s - Start selected stack\n"
            "  x - Stop selected stack\n"
            "  q - Quit",
            title="Help",
            timeout=10,
        )


def run_tui() -> None:
    app = SurekApp()
    app.run()
