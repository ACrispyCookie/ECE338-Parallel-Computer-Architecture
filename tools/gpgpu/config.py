from __future__ import annotations

from dataclasses import dataclass
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
    """Resolve the approved initial typed configuration model.

    Initial milestone intentionally supports schema defaults, built-in component
    defaults, manifests, goal defaults, named profiles, machine-local placeholder
    values, environment/tool placeholder defaults, and CLI --set overrides. It
    deliberately does not implement artifact injection.
    """

    SCHEMA: dict[str, SettingSpec] = {
        "architecture": SettingSpec("architecture", "str", "gpgpu32", "shared"),
        "platform": SettingSpec("platform", "str", "zynq7000-zedboard", "shared"),
        "board": SettingSpec("board", "str", "lab-zed", "machine-local"),
        "program": SettingSpec("program", "str", "nbody", "shared"),
        "demo": SettingSpec("demo", "str", "nbody", "shared"),
        "backend": SettingSpec("backend", "enum:fake,fpga-uart", "fake", "runtime"),
        "toolchain": SettingSpec("toolchain", "str", "riscv-gcc-rv32im-ilp32", "shared"),
        "variant": SettingSpec("variant", "str", "default", "shared"),
        "program.optimization": SettingSpec("program.optimization", "enum:O0,O1,O2,O3", "O2", "artifact"),
        "program.march": SettingSpec("program.march", "str", "rv32im", "artifact"),
        "program.mabi": SettingSpec("program.mabi", "str", "ilp32", "artifact"),
        "rtl.sp_per_sm": SettingSpec("rtl.sp_per_sm", "int", 32, "artifact"),
        "rtl.imem_words": SettingSpec("rtl.imem_words", "int", 2048, "artifact"),
        "rtl.dmem_words": SettingSpec("rtl.dmem_words", "int", 2048, "artifact"),
        "fpga.synth.strategy": SettingSpec("fpga.synth.strategy", "str", "default", "artifact"),
        "fpga.part": SettingSpec("fpga.part", "str", "xc7z020", "artifact"),
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

    COMPONENT_DEFAULTS: dict[str, Any] = {
        "architecture": "gpgpu32",
        "program.optimization": "O2",
        "fpga.synth.strategy": "default",
    }

    MANIFEST_DEFAULTS: dict[str, Any] = {
        "program": "nbody",
        "demo": "nbody",
        "platform": "zynq7000-zedboard",
    }

    GOAL_DEFAULTS: dict[str, Any] = {
        "backend": "fake",
        "kernel.kernel_calls": 1,
    }

    PROFILES: dict[str, dict[str, Any]] = {
        "zed-demo": {
            "architecture": "gpgpu32",
            "platform": "zynq7000-zedboard",
            "board": "lab-zed",
            "program": "nbody-3d",
            "demo": "nbody-3d",
            "backend": "fpga-uart",
            "fpga.synth.strategy": "Performance_Explore",
            "program.optimization": "O2",
            "board.configure_policy": "if-needed",
            "demo.fps": 12,
            "demo.dataset": "rings",
        }
    }

    MACHINE_LOCAL_DEFAULTS: dict[str, Any] = {
        "board.port": "/dev/ttyACM0",
        "uart.baud": 115200,
    }

    TOOL_ENV_DEFAULTS: dict[str, Any] = {
        "toolchain": "riscv-gcc-rv32im-ilp32",
    }

    def resolve(
        self,
        *,
        profile: str | None = None,
        set_values: list[str] | None = None,
    ) -> ResolvedConfig:
        values: dict[str, Any] = {}
        provenance: dict[str, Provenance] = {}

        for key, spec in self.SCHEMA.items():
            self._assign(values, provenance, key, spec.default, "schema default")

        layers: list[tuple[str, dict[str, Any]]] = [
            ("component default", self.COMPONENT_DEFAULTS),
            ("manifest default", self.MANIFEST_DEFAULTS),
            ("goal default", self.GOAL_DEFAULTS),
        ]

        if profile is not None:
            if profile not in self.PROFILES:
                raise ConfigError(f"Unknown profile: {profile}")
            layers.append((f"profile: {profile}", self.PROFILES[profile]))

        layers.extend(
            [
                ("machine-local default", self.MACHINE_LOCAL_DEFAULTS),
                ("tool discovery default", self.TOOL_ENV_DEFAULTS),
            ]
        )

        for source, mapping in layers:
            for key, value in mapping.items():
                self._assign(values, provenance, key, value, source)

        for item in set_values or []:
            key, raw_value = self._parse_set(item)
            self._assign(values, provenance, key, raw_value, "CLI --set")

        return ResolvedConfig(values=values, provenance=provenance)

    def _parse_set(self, item: str) -> tuple[str, str]:
        if "=" not in item:
            raise ConfigError(f"Invalid --set value {item!r}; expected namespace.key=value")
        key, value = item.split("=", 1)
        key = key.strip()
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
