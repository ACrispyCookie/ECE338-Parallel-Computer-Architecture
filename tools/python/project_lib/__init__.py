"""Shared helpers for ECE338 repository automation.

This package is intentionally small. Runnable scripts should import path and
configuration helpers from here instead of duplicating repo-root discovery and
JSON configuration loading.
"""

from .config import get_config_int, get_config_str, get_config_value, load_config
from .paths import RepoPaths, find_repo_root, repo_paths

__all__ = [
    "RepoPaths",
    "find_repo_root",
    "repo_paths",
    "load_config",
    "get_config_value",
    "get_config_int",
    "get_config_str",
]
