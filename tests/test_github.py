"""Tests for GitHub operations."""

from pathlib import Path

import pytest

from surek.core.github import (
    get_cached_commit,
    save_cached_commit,
)
from surek.models.stack import GitHubSource


class TestGitHubCache:
    """Tests for GitHub caching functions."""

    def test_save_and_get_cached_commit(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Test saving and retrieving cached commits."""
        monkeypatch.chdir(tmp_path)
        (tmp_path / "surek-data").mkdir()

        save_cached_commit("my-stack", "abc123")

        result = get_cached_commit("my-stack")
        assert result == "abc123"

    def test_get_nonexistent_cache(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Test getting cache for non-cached stack."""
        monkeypatch.chdir(tmp_path)
        (tmp_path / "surek-data").mkdir()

        result = get_cached_commit("nonexistent")
        assert result is None

    def test_get_cache_no_file(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Test getting cache when file doesn't exist."""
        monkeypatch.chdir(tmp_path)
        (tmp_path / "surek-data").mkdir()

        result = get_cached_commit("any-stack")
        assert result is None

    def test_cache_persists_multiple_stacks(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Test that cache handles multiple stacks."""
        monkeypatch.chdir(tmp_path)
        (tmp_path / "surek-data").mkdir()

        save_cached_commit("stack1", "commit1")
        save_cached_commit("stack2", "commit2")

        assert get_cached_commit("stack1") == "commit1"
        assert get_cached_commit("stack2") == "commit2"

    def test_cache_updates_existing(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Test that cache updates existing entries."""
        monkeypatch.chdir(tmp_path)
        (tmp_path / "surek-data").mkdir()

        save_cached_commit("my-stack", "old-commit")
        save_cached_commit("my-stack", "new-commit")

        assert get_cached_commit("my-stack") == "new-commit"


class TestGitHubSource:
    """Tests for GitHubSource model."""

    def test_parse_simple_slug(self) -> None:
        """Test parsing simple owner/repo slug."""
        source = GitHubSource(type="github", slug="owner/repo")
        assert source.owner == "owner"
        assert source.repo == "repo"
        assert source.ref == "HEAD"

    def test_parse_slug_with_ref(self) -> None:
        """Test parsing slug with branch ref."""
        source = GitHubSource(type="github", slug="owner/repo#main")
        assert source.owner == "owner"
        assert source.repo == "repo"
        assert source.ref == "main"

    def test_parse_slug_with_tag(self) -> None:
        """Test parsing slug with tag ref."""
        source = GitHubSource(type="github", slug="owner/repo#v1.0.0")
        assert source.owner == "owner"
        assert source.repo == "repo"
        assert source.ref == "v1.0.0"
