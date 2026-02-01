"""Surek template variable expansion."""

from surek.models.config import SurekConfig


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
