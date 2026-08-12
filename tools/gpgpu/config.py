from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


class ConfigError(ValueError):
    """Raised when typed configuration cannot be resolved."""


@dataclass(frozen=True)
class Provenance:
    source: str


@dataclass(frozen=True)
class SettingSpec:
    key: str
    type_name: str
    default: Any
    choices: tuple[str, ...] = ()
    manifest_dir: str | None = None


@dataclass(frozen=True)
class ResolvedConfig:
    values: dict[str, Any]
    provenance: dict[str, Provenance]

    def get(self, key: str) -> Any:
        if key not in self.values:
            raise ConfigError(f"Unknown setting: {key}")
        return self.values[key]

    def provenance_for(self, key: str) -> Provenance:
        if key not in self.provenance:
            raise ConfigError(f"Unknown setting: {key}")
        return self.provenance[key]

    def normalized_items(self) -> tuple[tuple[str, Any, str], ...]:
        return tuple((key, self.values[key], self.provenance[key].source) for key in sorted(self.values))


def _default_repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def load_schema(path: str | Path) -> dict[str, SettingSpec]:
    schema_path = Path(path)
    try:
        with schema_path.open("rb") as handle:
            data = yaml.safe_load(handle)
    except yaml.YAMLError as exc:
        raise ConfigError(f"Invalid YAML in {schema_path}: {exc}") from exc
    if data is None:
        data = {}
    settings = data.get("settings")
    if not isinstance(settings, dict) or not settings:
        raise ConfigError(f"{schema_path}: missing [settings] table")

    allowed_fields = {"type", "choices", "default", "manifest_dir"}
    valid_types = {"str", "int", "enum"}
    loaded: dict[str, SettingSpec] = {}
    for key, entry in settings.items():
        if not isinstance(key, str) or not re.fullmatch(r"[A-Za-z0-9_]+(\.[A-Za-z0-9_]+)*", key):
            raise ConfigError(f"Invalid setting name: {key!r}")
        if not isinstance(entry, dict):
            raise ConfigError(f"Schema setting {key} must be a table")
        unknown = set(entry) - allowed_fields
        if unknown:
            raise ConfigError(f"Unknown schema field for {key}: {sorted(unknown)[0]}")
        for required in ("type", "default"):
            if required not in entry:
                raise ConfigError(f"Schema setting {key} missing {required}")
        type_name = entry["type"]
        if type_name not in valid_types:
            raise ConfigError(f"Invalid schema type for {key}: {type_name!r}")
        choices: tuple[str, ...] = ()
        if type_name == "enum":
            raw_choices = entry.get("choices")
            if not isinstance(raw_choices, list) or not raw_choices or not all(isinstance(choice, str) for choice in raw_choices):
                raise ConfigError(f"enum setting {key} requires string choices")
            choices = tuple(raw_choices)
        elif "choices" in entry:
            raise ConfigError(f"choices are only valid for enum setting {key}")
        manifest_dir = entry.get("manifest_dir")
        if manifest_dir is not None:
            if type_name != "str":
                raise ConfigError(f"manifest_dir is only valid for string setting {key}")
            if not isinstance(manifest_dir, str) or not re.fullmatch(r"[A-Za-z0-9_/-]+", manifest_dir):
                raise ConfigError(f"Invalid manifest_dir for {key}: {manifest_dir!r}")
        spec = SettingSpec(
            key=key,
            type_name=type_name,
            default=entry["default"],
            choices=choices,
            manifest_dir=manifest_dir,
        )
        _coerce_value(spec, spec.default)
        loaded[key] = spec
    return loaded


def _coerce_value(spec: SettingSpec, raw_value: Any) -> Any:
    if spec.type_name == "int":
        if isinstance(raw_value, int) and not isinstance(raw_value, bool):
            return raw_value
        try:
            return int(str(raw_value), 0)
        except ValueError as exc:
            raise ConfigError(f"Setting {spec.key} expected integer, got {raw_value!r}") from exc

    if spec.type_name == "str":
        if raw_value is None:
            raise ConfigError(f"Setting {spec.key} expected string, got None")
        return str(raw_value)

    if spec.type_name == "enum":
        value = str(raw_value)
        if value not in spec.choices:
            raise ConfigError(f"Setting {spec.key} expected one of {', '.join(spec.choices)}, got {value!r}")
        return value

    raise ConfigError(f"Unsupported setting type for {spec.key}: {spec.type_name}")


class ConfigResolver:
    """Resolve typed GPGPU planner configuration from YAML manifests."""

    SCHEMA = load_schema(_default_repo_root() / "config" / "schema.yaml")

    def __init__(self, config_root: str | Path | None = None):
        repo_root = _default_repo_root()
        self.repo_root = repo_root
        self.config_root = Path(config_root) if config_root is not None else repo_root / "config"
        schema_path = self.config_root / "schema.yaml"
        self.schema = load_schema(schema_path) if schema_path.exists() else self.SCHEMA

    def resolve(
        self,
        *,
        profile: str | None = None,
        set_values: list[str] | None = None,
    ) -> ResolvedConfig:
        values: dict[str, Any] = {}
        provenance: dict[str, Provenance] = {}

        cli_overrides = tuple(self._parse_set(item) for item in (set_values or []))

        for key, spec in self.schema.items():
            self._assign(values, provenance, key, spec.default, "schema default")

        self._apply_defaults_file(values, provenance, self.config_root / "defaults.yaml", "defaults")

        profile_mapping: dict[str, Any] | None = None
        profile_source: str | None = None
        if profile is not None:
            profile_mapping, profile_source = self._load_profile(profile)
            self._apply_mapping(values, provenance, profile_mapping, profile_source)

        self._apply_manifest_selection_overrides(values, provenance, cli_overrides)
        self._apply_selected_manifests(values, provenance)

        if profile_mapping is not None and profile_source is not None:
            self._apply_mapping(values, provenance, profile_mapping, profile_source)

        self._apply_local(values, provenance)

        for key, raw_value in cli_overrides:
            self._assign(values, provenance, key, raw_value, "CLI --set")

        return ResolvedConfig(values=values, provenance=provenance)

    def _load_profile(self, profile: str) -> tuple[dict[str, Any], str]:
        path = self.config_root / "profiles" / f"{profile}.yaml"
        if not path.exists():
            raise ConfigError(f"Unknown profile: {profile}")
        data = self._read_yaml(path)
        mapping = data.get("profile", {})
        if not isinstance(mapping, dict) or not mapping:
            raise ConfigError(f"Profile {profile} must define a [profile] table")
        source = f"{self._source_path(path)}:profile"
        return self._flatten(mapping), source

    def _apply_manifest_selection_overrides(
        self,
        values: dict[str, Any],
        provenance: dict[str, Provenance],
        cli_overrides: tuple[tuple[str, str], ...],
    ) -> None:
        for key, raw_value in cli_overrides:
            normalized = self._normalize_key(key)
            spec = self.schema.get(normalized)
            if spec is not None and spec.manifest_dir is not None:
                self._assign(values, provenance, normalized, raw_value, "CLI --set selection")

    def _apply_selected_manifests(self, values: dict[str, Any], provenance: dict[str, Provenance]) -> None:
        for key, spec in self.schema.items():
            if spec.manifest_dir is not None:
                self._apply_selected_manifest(values, provenance, key, spec.manifest_dir)

    def _apply_selected_manifest(
        self,
        values: dict[str, Any],
        provenance: dict[str, Provenance],
        selection_key: str,
        directory: str,
    ) -> None:
        selected = values[selection_key]
        path = self.config_root / directory / f"{selected}.yaml"
        self._apply_defaults_file(values, provenance, path, "defaults", required=False)

    def _apply_local(self, values: dict[str, Any], provenance: dict[str, Provenance]) -> None:
        local = self.config_root / "local.yaml"
        if local.exists():
            self._apply_defaults_file(values, provenance, local, "defaults", source_prefix="local: ")
            return
        self._apply_defaults_file(values, provenance, self.config_root / "local.example.yaml", "defaults", required=False, source_prefix="local: ")

    def _apply_defaults_file(
        self,
        values: dict[str, Any],
        provenance: dict[str, Provenance],
        path: Path,
        section: str,
        *,
        required: bool = False,
        source_prefix: str = "",
    ) -> None:
        if not path.exists():
            if required:
                raise ConfigError(f"Missing config file: {self._source_path(path)}")
            return
        data = self._read_yaml(path)
        mapping = data.get(section, {})
        if not isinstance(mapping, dict):
            raise ConfigError(f"{self._source_path(path)}:{section} must be a table")
        self._apply_mapping(values, provenance, self._flatten(mapping), f"{source_prefix}{self._source_path(path)}:{section}")

    def _apply_mapping(
        self,
        values: dict[str, Any],
        provenance: dict[str, Provenance],
        mapping: dict[str, Any],
        source: str,
    ) -> None:
        for key, value in mapping.items():
            self._assign(values, provenance, self._normalize_key(key), value, source)

    def _normalize_key(self, key: str) -> str:
        aliases = {
            "architecture.name": "architecture",
            "board_type.name": "board_type",
            "board.name": "board",
            "program.name": "program",
            "demo.name": "demo",
        }
        return aliases.get(key, key)

    def _flatten(self, mapping: dict[str, Any], prefix: str = "") -> dict[str, Any]:
        flat: dict[str, Any] = {}
        for key, value in mapping.items():
            full_key = f"{prefix}.{key}" if prefix else str(key)
            if isinstance(value, dict):
                flat.update(self._flatten(value, full_key))
            else:
                flat[full_key] = value
        return flat

    def _read_yaml(self, path: Path) -> dict[str, Any]:
        try:
            with path.open("rb") as f:
                data = yaml.safe_load(f)
        except yaml.YAMLError as exc:
            raise ConfigError(f"Invalid YAML in {self._source_path(path)}: {exc}") from exc
        return data or {}

    def _source_path(self, path: Path) -> str:
        try:
            return path.resolve().relative_to(self.repo_root.resolve()).as_posix()
        except ValueError:
            return path.as_posix()

    def _parse_set(self, item: str) -> tuple[str, str]:
        if "=" not in item:
            raise ConfigError(f"Invalid --set value {item!r}; expected namespace.key=value")
        key, value = item.split("=", 1)
        key = self._normalize_key(key.strip())
        if not key:
            raise ConfigError("Invalid --set value with empty setting name")
        return key, value.strip()

    def _assign(
        self,
        values: dict[str, Any],
        provenance: dict[str, Provenance],
        key: str,
        raw_value: Any,
        source: str,
    ) -> None:
        if key not in self.schema:
            raise ConfigError(f"Unknown setting: {key}")
        values[key] = self._coerce(self.schema[key], raw_value)
        provenance[key] = Provenance(source=source)

    def _coerce(self, spec: SettingSpec, raw_value: Any) -> Any:
        return _coerce_value(spec, raw_value)
