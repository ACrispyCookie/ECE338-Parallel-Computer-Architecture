"""Configuration helpers for ECE338 automation scripts."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .paths import find_repo_root


Config = dict[str, Any]


def load_config(
    config_path: str | Path | None = None,
    *,
    repo_root: str | Path | None = None,
) -> Config:
    """Load `config/gpgpu.json`.

    Args:
        config_path: Optional explicit path to a JSON config file.
        repo_root: Optional repository root used when `config_path` is omitted.

    Returns:
        Parsed JSON object.
    """

    if config_path is None:
        root = Path(repo_root).resolve() if repo_root is not None else find_repo_root()
        path = root / "config" / "gpgpu.json"
    else:
        path = Path(config_path).resolve()

    with path.open("r", encoding="utf-8") as f:
        loaded = json.load(f)

    if not isinstance(loaded, dict):
        raise ValueError(f"Config root must be an object: {path}")

    return loaded


def get_config_value(config: Config, dotted_key: str, default: Any = None) -> Any:
    """Read a dotted config key such as `architecture.num_cores`."""

    current: Any = config
    for part in dotted_key.split("."):
        if not isinstance(current, dict) or part not in current:
            return default
        current = current[part]
    return current


def get_config_int(config: Config, dotted_key: str, default: int) -> int:
    """Read a dotted config key as an int."""

    value = get_config_value(config, dotted_key, default)
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Config key {dotted_key!r} must be an integer, got {value!r}") from exc


def get_config_str(config: Config, dotted_key: str, default: str) -> str:
    """Read a dotted config key as a string."""

    value = get_config_value(config, dotted_key, default)
    if value is None:
        return default
    return str(value)
