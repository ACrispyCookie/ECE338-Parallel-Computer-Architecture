from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any


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
    scope: str
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
        return tuple(
            (key, self.values[key], self.provenance[key].source)
            for key in sorted(self.values)
        )


class ConfigResolver:
    """Resolve typed GPGPU planner configuration from TOML manifests."""

    SCHEMA: dict[str, SettingSpec] = {
        "architecture": SettingSpec("architecture", "str", "gpgpu32", "shared", manifest_dir="architectures"),
        "board_type": SettingSpec("board_type", "str", "zynq7000-zedboard", "shared", manifest_dir="board_types"),
        "board": SettingSpec("board", "str", "zedboard", "machine-local"),
        "program": SettingSpec("program", "str", "nbody", "shared", manifest_dir="programs"),
        "demo": SettingSpec("demo", "str", "nbody", "shared", manifest_dir="demos"),
        "backend": SettingSpec("backend", "enum:fake,fpga-uart", "fake", "runtime"),
        "toolchain": SettingSpec("toolchain", "str", "riscv-gcc-rv32im-ilp32", "shared"),
        "program.optimization": SettingSpec("program.optimization", "enum:O0,O1,O2,O3", "O2", "artifact"),
        "program.march": SettingSpec("program.march", "str", "rv32im", "artifact"),
        "program.mabi": SettingSpec("program.mabi", "str", "ilp32", "artifact"),
        "rtl.sp_per_sm": SettingSpec("rtl.sp_per_sm", "int", 32, "artifact"),
        "rtl.imem_words": SettingSpec("rtl.imem_words", "int", 2048, "artifact"),
        "rtl.dmem_words": SettingSpec("rtl.dmem_words", "int", 2048, "artifact"),
        "fpga.synth.strategy": SettingSpec("fpga.synth.strategy", "str", "default", "artifact"),
        "fpga.part": SettingSpec("fpga.part", "str", "xc7z020clg484-1", "artifact"),
        "board.configure_policy": SettingSpec("board.configure_policy", "enum:if-needed,always,never", "if-needed", "runtime"),
        "kernel.load_policy": SettingSpec("kernel.load_policy", "enum:if-needed,always,never", "if-needed", "runtime"),
        "kernel.kernel_calls": SettingSpec("kernel.kernel_calls", "int", 1, "runtime"),
        "demo.fps": SettingSpec("demo.fps", "int", 12, "runtime"),
        "demo.dataset": SettingSpec("demo.dataset", "str", "default", "runtime"),
        "demo.steps_per_frame": SettingSpec("demo.steps_per_frame", "int", 1, "runtime"),
        "demo.http_host": SettingSpec("demo.http_host", "str", "0.0.0.0", "runtime"),
        "demo.http_port": SettingSpec("demo.http_port", "int", 8765, "runtime"),
        "board.port": SettingSpec("board.port", "str", "/dev/ttyACM0", "machine-local"),
        "uart.baud": SettingSpec("uart.baud", "int", 115200, "machine-local"),
        "executor.verbosity": SettingSpec("executor.verbosity", "int", 0, "executor"),
    }

    GOAL_DEFAULTS: dict[str, Any] = {
        "backend": "fake",
        "kernel.kernel_calls": 1,
    }

    TOOL_ENV_DEFAULTS: dict[str, Any] = {
        "toolchain": "riscv-gcc-rv32im-ilp32",
    }

    def __init__(self, config_root: str | Path | None = None):
        repo_root = Path(__file__).resolve().parents[2]
        self.repo_root = repo_root
        self.config_root = Path(config_root) if config_root is not None else repo_root / "config" / "gpgpu"

    def resolve(
        self,
        *,
        profile: str | None = None,
        set_values: list[str] | None = None,
    ) -> ResolvedConfig:
        values: dict[str, Any] = {}
        provenance: dict[str, Provenance] = {}

        cli_overrides = tuple(self._parse_set(item) for item in (set_values or []))

        for key, spec in self.SCHEMA.items():
            self._assign(values, provenance, key, spec.default, "schema default")

        self._apply_defaults_file(values, provenance, self.config_root / "defaults.toml", "defaults")

        profile_mapping: dict[str, Any] | None = None
        profile_source: str | None = None
        if profile is not None:
            profile_mapping, profile_source = self._load_profile(profile)
            self._apply_mapping(values, provenance, profile_mapping, profile_source)

        self._apply_manifest_selection_overrides(values, provenance, cli_overrides)
        self._apply_selected_manifests(values, provenance)

        if profile_mapping is not None and profile_source is not None:
            self._apply_mapping(values, provenance, profile_mapping, profile_source)

        for key, value in self.GOAL_DEFAULTS.items():
            if key not in provenance or provenance[key].source == "schema default":
                self._assign(values, provenance, key, value, "goal default")

        self._apply_local(values, provenance)

        for key, value in self.TOOL_ENV_DEFAULTS.items():
            if key not in provenance or provenance[key].source == "schema default":
                self._assign(values, provenance, key, value, "tool discovery default")

        for key, raw_value in cli_overrides:
            self._assign(values, provenance, key, raw_value, "CLI --set")

        return ResolvedConfig(values=values, provenance=provenance)

    def _load_profile(self, profile: str) -> tuple[dict[str, Any], str]:
        path = self.config_root / "profiles" / f"{profile}.toml"
        if not path.exists():
            raise ConfigError(f"Unknown profile: {profile}")
        data = self._read_toml(path)
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
            spec = self.SCHEMA.get(normalized)
            if spec is not None and spec.manifest_dir is not None:
                self._assign(values, provenance, normalized, raw_value, "CLI --set selection")

    def _apply_selected_manifests(self, values: dict[str, Any], provenance: dict[str, Provenance]) -> None:
        for key, spec in self.SCHEMA.items():
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
        path = self.config_root / directory / f"{selected}.toml"
        self._apply_defaults_file(values, provenance, path, "defaults", required=False)

    def _apply_local(self, values: dict[str, Any], provenance: dict[str, Provenance]) -> None:
        local = self.config_root / "local.toml"
        if local.exists():
            self._apply_defaults_file(values, provenance, local, "defaults", source_prefix="local: ")
            return
        self._apply_defaults_file(values, provenance, self.config_root / "local.example.toml", "defaults", required=False, source_prefix="local: ")

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
        data = self._read_toml(path)
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

    def _read_toml(self, path: Path) -> dict[str, Any]:
        try:
            with path.open("rb") as f:
                return tomllib.load(f)
        except tomllib.TOMLDecodeError as exc:
            raise ConfigError(f"Invalid TOML in {self._source_path(path)}: {exc}") from exc

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
        if key not in self.SCHEMA:
            raise ConfigError(f"Unknown setting: {key}")
        values[key] = self._coerce(self.SCHEMA[key], raw_value)
        provenance[key] = Provenance(source=source)

    def _coerce(self, spec: SettingSpec, raw_value: Any) -> Any:
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

        if spec.type_name.startswith("enum:"):
            choices = spec.type_name.split(":", 1)[1].split(",")
            value = str(raw_value)
            if value not in choices:
                raise ConfigError(
                    f"Setting {spec.key} expected one of {', '.join(choices)}, got {value!r}"
                )
            return value

        raise ConfigError(f"Unsupported setting type for {spec.key}: {spec.type_name}")
