"""Docker Compose file transformation."""

import copy
import json
import os
from pathlib import Path
from typing import Any

import bcrypt
import yaml

from surek.core.docker import DEFAULT_LABELS, SUREK_NETWORK
from surek.core.variables import expand_all_variables_in_dict, expand_variables
from surek.exceptions import SurekError
from surek.models.config import SurekConfig
from surek.models.stack import StackConfig
from surek.utils.logging import print_warning
from surek.utils.paths import get_stack_volumes_dir


def read_compose_file(path: Path) -> dict[str, Any]:
    """Read and parse a Docker Compose file.

    Args:
        path: Path to the compose file.

    Returns:
        Parsed compose file as a dictionary.

    Raises:
        SurekError: If the file cannot be read or parsed.
    """
    try:
        with open(path) as f:
            data = yaml.safe_load(f)
        if data is None:
            raise SurekError(f"Compose file is empty: {path}")
        return data
    except yaml.YAMLError as e:
        raise SurekError(f"Invalid YAML in compose file: {e}") from e
    except OSError as e:
        raise SurekError(f"Could not read compose file: {e}") from e


def write_compose_file(path: Path, spec: dict[str, Any]) -> None:
    """Write a Docker Compose file.

    Args:
        path: Path to write the file.
        spec: The compose specification to write.
    """
    with open(path, "w") as f:
        yaml.dump(spec, f, default_flow_style=False, sort_keys=False)


def transform_compose_file(
    spec: dict[str, Any],
    config: StackConfig,
    surek_config: SurekConfig,
) -> dict[str, Any]:
    """Transform a Docker Compose specification for Surek.

    This function applies the following transformations:
    1. Add the Surek network as external
    2. Convert volumes to bind mounts for backup
    3. Add Caddy labels for public endpoints
    4. Inject environment variables
    5. Connect all services to the Surek network

    Args:
        spec: The original compose specification.
        config: The stack configuration.
        surek_config: The main Surek configuration.

    Returns:
        The transformed compose specification.

    Raises:
        SurekError: If a referenced service is not found.
    """
    spec = copy.deepcopy(spec)

    # Expand surek variables (<root>, etc.) and env variables (${VAR}) in compose spec
    spec = expand_all_variables_in_dict(spec, surek_config)

    volumes_dir = get_stack_volumes_dir(config.name)
    folders_to_create: list[Path] = []

    # 1. Network injection - add Surek network as external
    if "networks" not in spec:
        spec["networks"] = {}

    spec["networks"][SUREK_NETWORK] = {
        "name": SUREK_NETWORK,
        "external": True,
    }

    # 2. Volume transformation - convert to bind mounts
    if "volumes" in spec and spec["volumes"]:
        exclude_volumes = config.backup.exclude_volumes if config.backup else []

        for volume_name, volume_config in list(spec["volumes"].items()):
            if volume_name in exclude_volumes:
                continue

            # Skip pre-configured volumes (those with existing configuration)
            if volume_config and len(volume_config) > 0:
                print_warning(
                    f"Volume {volume_name} is pre-configured. "
                    f"This volume will be skipped on backup."
                )
                continue

            folder_path = volumes_dir / volume_name
            folders_to_create.append(folder_path)

            spec["volumes"][volume_name] = {
                "driver": "local",
                "driver_opts": {
                    "type": "none",
                    "o": "bind",
                    "device": str(folder_path),
                },
                "labels": DEFAULT_LABELS.copy(),
            }

    # 3. Public service labels - add Caddy configuration
    for endpoint in config.public:
        service_name = endpoint.service_name
        port = endpoint.port

        if "services" not in spec or service_name not in spec["services"]:
            raise SurekError(f"Service '{service_name}' not defined in docker-compose config")

        service = spec["services"][service_name]
        if "labels" not in service:
            service["labels"] = {}

        domain = expand_variables(endpoint.domain, surek_config)

        labels: dict[str, str] = {
            **DEFAULT_LABELS,
            "caddy": domain,
            "caddy.reverse_proxy": f"{{{{upstreams {port}}}}}",
        }

        # Development mode - use internal TLS
        if os.environ.get("SUREK_ENV") == "development":
            labels["caddy.tls"] = "internal"

        # Basic auth
        if endpoint.auth:
            auth_str = expand_variables(endpoint.auth, surek_config)
            user, password = auth_str.split(":", 1)
            hashed = bcrypt.hashpw(password.encode(), bcrypt.gensalt(rounds=14))
            # Escape $ for Docker Compose ($ -> $$)
            escaped_hash = hashed.decode().replace("$", "$$")
            labels["caddy.basic_auth"] = ""
            labels[f"caddy.basic_auth.{user}"] = escaped_hash

        # Merge labels into service
        _merge_labels(service, labels)

    # 4. Environment variable injection
    if config.env and "services" in spec:
        for service_name, service in spec["services"].items():
            container_env = config.env.by_container.get(service_name, [])
            shared_env = config.env.shared

            expanded_env = [
                expand_variables(e, surek_config) for e in shared_env + container_env
            ]

            if expanded_env:
                if "environment" not in service:
                    service["environment"] = []

                service["environment"] = _merge_envs(service["environment"], expanded_env)

    # 5. Create volume directories
    for folder in folders_to_create:
        folder.mkdir(parents=True, exist_ok=True)

    # 6. Service network injection - connect all services to Surek network
    if "services" in spec:
        for _service_name, service in spec["services"].items():
            # Skip if network_mode is set (can't add networks with network_mode)
            if "network_mode" in service:
                continue

            if "networks" not in service:
                service["networks"] = []

            if isinstance(service["networks"], list):
                if SUREK_NETWORK not in service["networks"]:
                    service["networks"].append(SUREK_NETWORK)
            else:
                # networks is a dict
                if SUREK_NETWORK not in service["networks"]:
                    service["networks"][SUREK_NETWORK] = None

    return spec


def transform_system_compose(
    spec: dict[str, Any],
    config: SurekConfig,
) -> dict[str, Any]:
    """Apply system-specific transformations to the compose spec.

    Args:
        spec: The original compose specification.
        config: The main Surek configuration.

    Returns:
        The transformed compose specification.
    """
    spec = copy.deepcopy(spec)

    # Remove backup service if not configured
    if not config.backup and "services" in spec:
        spec["services"].pop("backup", None)

    # Remove portainer if disabled
    if not config.system_services.portainer and "services" in spec:
        spec["services"].pop("portainer", None)

    # Remove netdata if disabled
    if not config.system_services.netdata and "services" in spec:
        spec["services"].pop("netdata", None)

    return spec


def _merge_labels(service: dict[str, Any], labels: dict[str, str]) -> None:
    """Merge labels into a service definition.

    Handles both array and object label formats.

    Args:
        service: The service definition to modify.
        labels: The labels to add.
    """
    service_labels = service.get("labels", {})

    if isinstance(service_labels, list):
        # Array format: ["key=value", ...]
        for key, value in labels.items():
            # JSON stringify the value for consistency
            if isinstance(value, str):
                service_labels.append(f"{key}={value}")
            else:
                service_labels.append(f"{key}={json.dumps(value)}")
        service["labels"] = service_labels
    else:
        # Object format: {key: value, ...}
        service_labels.update(labels)
        service["labels"] = service_labels


def _merge_envs(
    original: list[str] | dict[str, str],
    extensions: list[str],
) -> list[str] | dict[str, str]:
    """Merge environment variables.

    Args:
        original: Original environment (list or dict).
        extensions: Environment strings to add ("KEY=value" format).

    Returns:
        Merged environment in the same format as original.
    """
    if isinstance(original, list):
        return list(original) + extensions
    else:
        # Convert extensions to dict and merge
        result = dict(original)
        for ext in extensions:
            if "=" in ext:
                key, value = ext.split("=", 1)
                result[key] = value
        return result
