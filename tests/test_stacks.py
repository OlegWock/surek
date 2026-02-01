"""Tests for stack discovery and management."""

from pathlib import Path
from textwrap import dedent

import pytest

from surek.core.stacks import get_available_stacks, get_stack_by_name
from surek.exceptions import SurekError


class TestGetAvailableStacks:
    """Tests for get_available_stacks function."""

    def test_find_valid_stacks(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test finding valid stacks in stacks directory."""
        monkeypatch.chdir(tmp_path)

        # Create stacks directory with two stacks
        stacks_dir = tmp_path / "stacks"
        stacks_dir.mkdir()

        stack1_dir = stacks_dir / "stack1"
        stack1_dir.mkdir()
        (stack1_dir / "surek.stack.yml").write_text(
            dedent("""
            name: stack1
            source:
              type: local
        """)
        )

        stack2_dir = stacks_dir / "stack2"
        stack2_dir.mkdir()
        (stack2_dir / "surek.stack.yml").write_text(
            dedent("""
            name: stack2
            source:
              type: local
        """)
        )

        stacks = get_available_stacks()
        assert len(stacks) == 2
        assert all(s.valid for s in stacks)
        names = [s.config.name for s in stacks if s.config]
        assert "stack1" in names
        assert "stack2" in names

    def test_handle_invalid_stack(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test handling of invalid stack config."""
        monkeypatch.chdir(tmp_path)

        stacks_dir = tmp_path / "stacks"
        stacks_dir.mkdir()

        stack_dir = stacks_dir / "bad-stack"
        stack_dir.mkdir()
        (stack_dir / "surek.stack.yml").write_text("invalid: yaml: content:")

        stacks = get_available_stacks()
        assert len(stacks) == 1
        assert not stacks[0].valid
        assert stacks[0].error

    def test_no_stacks_directory(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test error when stacks directory doesn't exist."""
        monkeypatch.chdir(tmp_path)

        with pytest.raises(SurekError) as exc_info:
            get_available_stacks()
        assert "stacks" in str(exc_info.value).lower()

    def test_empty_stacks_directory(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test empty stacks directory returns empty list."""
        monkeypatch.chdir(tmp_path)
        (tmp_path / "stacks").mkdir()

        stacks = get_available_stacks()
        assert len(stacks) == 0


class TestGetStackByName:
    """Tests for get_stack_by_name function."""

    def test_find_stack_by_name(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test finding a stack by name."""
        monkeypatch.chdir(tmp_path)

        stacks_dir = tmp_path / "stacks"
        stacks_dir.mkdir()

        stack_dir = stacks_dir / "mystack"
        stack_dir.mkdir()
        (stack_dir / "surek.stack.yml").write_text(
            dedent("""
            name: my-stack
            source:
              type: local
        """)
        )

        stack = get_stack_by_name("my-stack")
        assert stack.valid
        assert stack.config is not None
        assert stack.config.name == "my-stack"

    def test_stack_not_found(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test error when stack is not found."""
        monkeypatch.chdir(tmp_path)
        (tmp_path / "stacks").mkdir()

        with pytest.raises(SurekError) as exc_info:
            get_stack_by_name("nonexistent")
        assert "not found" in str(exc_info.value)

    def test_empty_name(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test error when name is empty."""
        monkeypatch.chdir(tmp_path)
        (tmp_path / "stacks").mkdir()

        with pytest.raises(SurekError) as exc_info:
            get_stack_by_name("")
        assert "Invalid" in str(exc_info.value)
