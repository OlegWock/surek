"""Top bar widget."""

from textual.app import ComposeResult
from textual.message import Message
from textual.widget import Widget
from textual.widgets import Button, Static


class TopBar(Widget):
    """Reusable top bar widget with optional back button."""

    DEFAULT_CSS = """
    TopBar {
        width: 100%;
        height: 4;
        padding: 0 1;
        layout: horizontal;
        border-bottom: solid $primary-darken-2;
    }

    TopBar .top-bar-button {
        width: auto;
        min-width: 10;
        height: 100%;
    }

    TopBar .top-bar-title {
        text-style: bold;
        width: 1fr;
        height: 100%;
        text-align: center;
        content-align: center middle;
    }

    TopBar .top-bar-spacer {
        width: 10;
        height: 100%;
    }
    """

    class BackPressed(Message):
        """Message sent when the back button is pressed."""

        pass

    def __init__(
        self,
        title: str,
        show_back: bool = False,
        name: str | None = None,
        id: str | None = None,
        classes: str | None = None,
    ) -> None:
        """Initialize the top bar.

        Args:
            title: The title to display.
            show_back: Whether to show a back button.
            name: Optional widget name.
            id: Optional widget ID.
            classes: Optional CSS classes.
        """
        super().__init__(name=name, id=id, classes=classes)
        self._title = title
        self._show_back = show_back

    def compose(self) -> ComposeResult:
        if self._show_back:
            yield Button("← Back", classes="top-bar-button")
            yield Static(self._title, classes="top-bar-title")
            yield Static("", classes="top-bar-spacer")
        else:
            yield Static(self._title, classes="top-bar-title")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        self.post_message(self.BackPressed())
