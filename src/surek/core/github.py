"""GitHub repository operations."""

import json
import shutil
import tempfile
import zipfile
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
from typing import Optional

import httpx

from surek.exceptions import GitHubError
from surek.models.config import SurekConfig
from surek.models.stack import GitHubSource
from surek.utils.logging import console, print_dim
from surek.utils.paths import get_data_dir


def get_cache_file() -> Path:
    """Get the path to the GitHub cache file.

    Returns:
        Path to surek-data/github_cache.json
    """
    return get_data_dir() / "github_cache.json"


def get_cached_commit(stack_name: str) -> Optional[str]:
    """Get the cached commit hash for a stack.

    Args:
        stack_name: Name of the stack.

    Returns:
        Cached commit hash, or None if not cached.
    """
    cache_file = get_cache_file()
    if not cache_file.exists():
        return None

    try:
        cache = json.loads(cache_file.read_text())
        return cache.get(stack_name, {}).get("commit")
    except (json.JSONDecodeError, OSError):
        return None


def save_cached_commit(stack_name: str, commit: str) -> None:
    """Save the commit hash for a stack.

    Args:
        stack_name: Name of the stack.
        commit: The commit hash to cache.
    """
    cache_file = get_cache_file()

    if cache_file.exists():
        try:
            cache = json.loads(cache_file.read_text())
        except (json.JSONDecodeError, OSError):
            cache = {}
    else:
        cache = {}

    cache[stack_name] = {
        "commit": commit,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }

    cache_file.write_text(json.dumps(cache, indent=2))


def get_latest_commit(source: GitHubSource, config: SurekConfig) -> str:
    """Get the latest commit hash from GitHub.

    Args:
        source: The GitHub source configuration.
        config: The main Surek configuration with GitHub PAT.

    Returns:
        The latest commit SHA.

    Raises:
        GitHubError: If the API request fails or PAT is missing.
    """
    if not config.github:
        raise GitHubError("GitHub PAT is required")

    headers = {
        "Authorization": f"token {config.github.pat}",
        "Accept": "application/vnd.github.v3+json",
    }

    url = f"https://api.github.com/repos/{source.owner}/{source.repo}/commits/{source.ref}"

    try:
        response = httpx.get(url, headers=headers, timeout=30.0)
        response.raise_for_status()
        return response.json()["sha"]
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 404:
            raise GitHubError(
                f"Repository or ref not found: {source.owner}/{source.repo}#{source.ref}"
            ) from e
        elif e.response.status_code == 401:
            raise GitHubError("GitHub authentication failed. Check your PAT.") from e
        else:
            raise GitHubError(f"GitHub API error: {e.response.status_code}") from e
    except httpx.RequestError as e:
        raise GitHubError(f"Failed to connect to GitHub: {e}") from e


def pull_github_repo(
    source: GitHubSource,
    target_dir: Path,
    config: SurekConfig,
) -> str:
    """Download and extract a GitHub repository.

    Args:
        source: The GitHub source configuration.
        target_dir: Directory to extract into.
        config: The main Surek configuration with GitHub PAT.

    Returns:
        The commit SHA that was downloaded.

    Raises:
        GitHubError: If download or extraction fails.
    """
    if not config.github:
        raise GitHubError("GitHub PAT is required for this")

    console.print(f"Downloading GitHub repo {source.slug}")

    headers = {
        "Authorization": f"token {config.github.pat}",
        "Accept": "application/vnd.github.v3+json",
    }

    # Download zipball
    url = f"https://api.github.com/repos/{source.owner}/{source.repo}/zipball/{source.ref}"

    try:
        with httpx.stream("GET", url, headers=headers, timeout=120.0, follow_redirects=True) as response:
            response.raise_for_status()
            zip_content = BytesIO(response.read())
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 404:
            raise GitHubError(
                f"Repository or ref not found: {source.owner}/{source.repo}#{source.ref}"
            ) from e
        elif e.response.status_code == 401:
            raise GitHubError("GitHub authentication failed. Check your PAT.") from e
        else:
            raise GitHubError(f"GitHub API error: {e.response.status_code}") from e
    except httpx.RequestError as e:
        raise GitHubError(f"Failed to download from GitHub: {e}") from e

    # Extract to temporary directory first
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)

        try:
            with zipfile.ZipFile(zip_content) as zf:
                zf.extractall(temp_path)
        except zipfile.BadZipFile as e:
            raise GitHubError(f"Invalid zip file from GitHub: {e}") from e

        # GitHub zipballs have a single root folder (e.g., "owner-repo-commitsha/")
        items = list(temp_path.iterdir())
        if len(items) != 1:
            raise GitHubError("Expected a single root folder in the zip file")

        root_folder = items[0]
        if not root_folder.is_dir():
            raise GitHubError("The single item in the zip is not a folder")

        # Extract commit SHA from folder name (last part after final hyphen)
        # Format: owner-repo-shortsha
        commit_sha = root_folder.name.rsplit("-", 1)[-1]

        # Move contents to target directory
        target_dir.mkdir(parents=True, exist_ok=True)
        for item in root_folder.iterdir():
            dest = target_dir / item.name
            if dest.exists():
                if dest.is_dir():
                    shutil.rmtree(dest)
                else:
                    dest.unlink()
            shutil.move(str(item), str(dest))

    print_dim("Downloaded and unpacked repo content.")
    return commit_sha
