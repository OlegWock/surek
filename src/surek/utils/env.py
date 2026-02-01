"""Environment variable expansion utilities."""

import os
import re
from typing import Any


def expand_env_vars(value: str) -> str:
    """Expand ${VAR_NAME} patterns with environment variables.

    Args:
        value: String potentially containing ${VAR_NAME} patterns.

    Returns:
        String with environment variables expanded.

    Raises:
        ValueError: If an environment variable is not set.
    """
    pattern = r"\$\{([^}]+)\}"

    def replacer(match: re.Match[str]) -> str:
        var_name = match.group(1)
        env_value = os.environ.get(var_name)
        if env_value is None:
            raise ValueError(f"Environment variable '{var_name}' is not set")
        return env_value

    return re.sub(pattern, replacer, value)


def expand_env_vars_in_dict(data: dict[str, Any]) -> dict[str, Any]:
    """Recursively expand environment variables in a dictionary.

    Args:
        data: Dictionary potentially containing ${VAR_NAME} patterns in string values.

    Returns:
        Dictionary with environment variables expanded in all string values.

    Raises:
        ValueError: If an environment variable is not set.
    """
    result: dict[str, Any] = {}
    for key, value in data.items():
        if isinstance(value, str):
            result[key] = expand_env_vars(value)
        elif isinstance(value, dict):
            result[key] = expand_env_vars_in_dict(value)
        elif isinstance(value, list):
            result[key] = _expand_env_vars_in_list(value)
        else:
            result[key] = value
    return result


def _expand_env_vars_in_list(data: list[Any]) -> list[Any]:
    """Recursively expand environment variables in a list.

    Args:
        data: List potentially containing ${VAR_NAME} patterns in string values.

    Returns:
        List with environment variables expanded in all string values.
    """
    result: list[Any] = []
    for item in data:
        if isinstance(item, str):
            result.append(expand_env_vars(item))
        elif isinstance(item, dict):
            result.append(expand_env_vars_in_dict(item))
        elif isinstance(item, list):
            result.append(_expand_env_vars_in_list(item))
        else:
            result.append(item)
    return result
