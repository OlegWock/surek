"""Configuration loading for Surek."""

from pathlib import Path

import yaml
from pydantic import ValidationError

from surek.exceptions import StackConfigError, SurekConfigError
from surek.models.config import SurekConfig
from surek.models.stack import StackConfig
from surek.utils.env import expand_env_vars_in_dict


def load_config(config_path: Path | None = None) -> SurekConfig:
    """Load and validate the main Surek configuration.

    Args:
        config_path: Optional path to config file. If not provided,
                     searches for surek.yml or surek.yaml in cwd.

    Returns:
        Validated SurekConfig instance.

    Raises:
        SurekConfigError: If config file is not found or invalid.
    """
    if config_path is None:
        config_path = _find_config_file()

    if config_path is None:
        raise SurekConfigError(
            "Config file not found. Make sure you have surek.yml in current working directory"
        )

    try:
        with open(config_path) as f:
            raw_data = yaml.safe_load(f)
    except yaml.YAMLError as e:
        raise SurekConfigError(f"Invalid YAML in config file: {e}") from e
    except OSError as e:
        raise SurekConfigError(f"Could not read config file: {e}") from e

    if raw_data is None:
        raise SurekConfigError("Config file is empty")

    # Expand environment variables before validation
    try:
        expanded_data = expand_env_vars_in_dict(raw_data)
    except ValueError as e:
        raise SurekConfigError(str(e)) from e

    # Validate and create model
    try:
        return SurekConfig(**expanded_data)
    except ValidationError as e:
        raise SurekConfigError(f"Invalid configuration:\n{_format_validation_error(e)}") from e


def load_stack_config(path: Path) -> StackConfig:
    """Load and validate a stack configuration file.

    Args:
        path: Path to the surek.stack.yml file.

    Returns:
        Validated StackConfig instance.

    Raises:
        StackConfigError: If config file is not found or invalid.
    """
    if not path.exists():
        raise StackConfigError(f"Stack config file not found: {path}")

    try:
        with open(path) as f:
            raw_data = yaml.safe_load(f)
    except yaml.YAMLError as e:
        raise StackConfigError(f"Invalid YAML in stack config: {e}") from e
    except OSError as e:
        raise StackConfigError(f"Could not read stack config: {e}") from e

    if raw_data is None:
        raise StackConfigError(f"Stack config file is empty: {path}")

    # Expand environment variables before validation
    try:
        expanded_data = expand_env_vars_in_dict(raw_data)
    except ValueError as e:
        raise StackConfigError(str(e)) from e

    # Validate and create model
    try:
        return StackConfig(**expanded_data)
    except ValidationError as e:
        raise StackConfigError(
            f"Invalid stack config at {path}:\n{_format_validation_error(e)}"
        ) from e


def _find_config_file() -> Path | None:
    """Find the Surek config file in the current directory.

    Returns:
        Path to config file if found, None otherwise.
    """
    cwd = Path.cwd()
    for filename in ["surek.yml", "surek.yaml"]:
        config_path = cwd / filename
        if config_path.exists():
            return config_path
    return None


def _format_validation_error(error: ValidationError) -> str:
    """Format a Pydantic validation error for display.

    Args:
        error: The validation error to format.

    Returns:
        Human-readable error message.
    """
    messages = []
    for err in error.errors():
        loc = ".".join(str(x) for x in err["loc"])
        msg = err["msg"]
        if loc:
            messages.append(f"  - {loc}: {msg}")
        else:
            messages.append(f"  - {msg}")
    return "\n".join(messages)
