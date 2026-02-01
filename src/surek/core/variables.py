"""Surek template variable expansion."""

from typing import Any

from surek.models.config import SurekConfig
from surek.utils.env import expand_env_vars


def expand_variables(value: str, config: SurekConfig) -> str:
    """Expand Surek template variables in a string.

    Supported variables:
        <root>              - root_domain from config
        <default_auth>      - default_auth (user:password)
        <default_user>      - username from default_auth
        <default_password>  - password from default_auth
        <backup_password>   - backup encryption password
        <backup_s3_endpoint> - S3 endpoint URL
        <backup_s3_bucket>  - S3 bucket name
        <backup_s3_access_key> - S3 access key
        <backup_s3_secret_key> - S3 secret key

    Args:
        value: String potentially containing <variable> patterns.
        config: The main Surek configuration.

    Returns:
        String with variables replaced by their values.
    """
    result = value

    # Core variables
    replacements = {
        "<root>": config.root_domain,
        "<default_auth>": config.default_auth,
        "<default_user>": config.default_user,
        "<default_password>": config.default_password,
    }

    # Backup variables (only if backup is configured)
    if config.backup:
        replacements.update(
            {
                "<backup_password>": config.backup.password,
                "<backup_s3_endpoint>": config.backup.s3_endpoint,
                "<backup_s3_bucket>": config.backup.s3_bucket,
                "<backup_s3_access_key>": config.backup.s3_access_key,
                "<backup_s3_secret_key>": config.backup.s3_secret_key,
            }
        )

    for var, val in replacements.items():
        result = result.replace(var, val)

    return result


def expand_variables_in_list(values: list[str], config: SurekConfig) -> list[str]:
    """Expand Surek template variables in a list of strings.

    Args:
        values: List of strings potentially containing <variable> patterns.
        config: The main Surek configuration.

    Returns:
        List of strings with variables replaced.
    """
    return [expand_variables(v, config) for v in values]


def expand_all_variables(value: str, config: SurekConfig) -> str:
    """Expand both Surek variables and environment variables in a string.

    First expands Surek variables (<root>, etc.), then environment variables (${VAR}).

    Args:
        value: String potentially containing variables.
        config: The main Surek configuration.

    Returns:
        String with all variables expanded.
    """
    # First expand surek variables, then env variables
    result = expand_variables(value, config)
    return expand_env_vars(result)


def expand_all_variables_in_dict(data: dict[str, Any], config: SurekConfig) -> dict[str, Any]:
    """Recursively expand all variables in a dictionary.

    Expands both Surek variables (<root>, etc.) and environment variables (${VAR})
    in all string values throughout the dictionary.

    Args:
        data: Dictionary potentially containing variables in string values.
        config: The main Surek configuration.

    Returns:
        Dictionary with all variables expanded.
    """
    result: dict[str, Any] = {}
    for key, value in data.items():
        if isinstance(value, str):
            result[key] = expand_all_variables(value, config)
        elif isinstance(value, dict):
            result[key] = expand_all_variables_in_dict(value, config)
        elif isinstance(value, list):
            result[key] = _expand_all_variables_in_list(value, config)
        else:
            result[key] = value
    return result


def _expand_all_variables_in_list(data: list[Any], config: SurekConfig) -> list[Any]:
    """Recursively expand all variables in a list.

    Args:
        data: List potentially containing variables in string values.
        config: The main Surek configuration.

    Returns:
        List with all variables expanded.
    """
    result: list[Any] = []
    for item in data:
        if isinstance(item, str):
            result.append(expand_all_variables(item, config))
        elif isinstance(item, dict):
            result.append(expand_all_variables_in_dict(item, config))
        elif isinstance(item, list):
            result.append(_expand_all_variables_in_list(item, config))
        else:
            result.append(item)
    return result
