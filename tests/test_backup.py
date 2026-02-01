"""Tests for backup operations."""

from pathlib import Path

import pytest

from surek.core.backup import (
    get_recent_failures,
    load_failures,
    record_backup_failure,
)


class TestBackupFailureTracking:
    """Tests for backup failure tracking."""

    def test_record_and_load_failure(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Test recording and loading backup failures."""
        monkeypatch.chdir(tmp_path)
        (tmp_path / "surek-data").mkdir()

        record_backup_failure("daily", "Test error message")

        failures = load_failures()
        assert len(failures) == 1
        assert failures[0].backup_type == "daily"
        assert failures[0].error == "Test error message"

    def test_load_empty_failures(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Test loading when no failures exist."""
        monkeypatch.chdir(tmp_path)
        (tmp_path / "surek-data").mkdir()

        failures = load_failures()
        assert failures == []

    def test_multiple_failures(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Test recording multiple failures."""
        monkeypatch.chdir(tmp_path)
        (tmp_path / "surek-data").mkdir()

        record_backup_failure("daily", "Error 1")
        record_backup_failure("weekly", "Error 2")
        record_backup_failure("monthly", "Error 3")

        failures = load_failures()
        assert len(failures) == 3

    def test_get_recent_failures(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Test getting recent failures with limit."""
        monkeypatch.chdir(tmp_path)
        (tmp_path / "surek-data").mkdir()

        for i in range(15):
            record_backup_failure("daily", f"Error {i}")

        recent = get_recent_failures(limit=5)
        assert len(recent) == 5
        # Should be the last 5
        assert recent[-1].error == "Error 14"

    def test_failure_limit(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Test that only 100 failures are kept."""
        monkeypatch.chdir(tmp_path)
        (tmp_path / "surek-data").mkdir()

        # Record more than 100 failures
        for i in range(110):
            record_backup_failure("daily", f"Error {i}")

        failures = load_failures()
        # Should only keep last 100
        assert len(failures) == 100
        # First one should be error 10 (oldest kept)
        assert failures[0].error == "Error 10"
