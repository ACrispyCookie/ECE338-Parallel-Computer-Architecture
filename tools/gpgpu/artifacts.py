from __future__ import annotations

import hashlib
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Mapping

if TYPE_CHECKING:
    from .config import ResolvedConfig
    from .planner import GoalInstance


@dataclass(frozen=True)
class ArtifactStatus:
    state: str
    path: Path | None
    reason: str

    @property
    def is_hit(self) -> bool:
        return self.state == "hit"


def artifacts_root(repo_root: str | Path) -> Path:
    return Path(repo_root) / "out" / "artifacts"


def artifact_dir(repo_root: str | Path, node: GoalInstance) -> Path:
    return artifacts_root(repo_root) / node.goal_id / node.identity


def read_artifact_status(repo_root: str | Path, node: GoalInstance) -> ArtifactStatus:
    if node.kind != "artifact":
        return ArtifactStatus("not-artifact", None, "goal is not an artifact")
    root = Path(repo_root)
    directory = artifact_dir(root, node)
    metadata_path = directory / "artifact.toml"
    if not directory.exists():
        return ArtifactStatus("missing", directory, "artifact directory missing")
    if not directory.is_dir():
        return ArtifactStatus("invalid", directory, "artifact path is not a directory")
    if not metadata_path.exists():
        return ArtifactStatus("missing", directory, "artifact metadata missing")
    try:
        with metadata_path.open("rb") as handle:
            metadata = tomllib.load(handle)
    except tomllib.TOMLDecodeError:
        return ArtifactStatus("invalid", directory, "artifact metadata invalid")
    if metadata.get("goal") != node.goal_id or metadata.get("identity") != node.identity:
        return ArtifactStatus("invalid", directory, "artifact metadata mismatch")
    produced = metadata.get("produced", {})
    produced_files = produced.get("files", ()) if isinstance(produced, dict) else ()
    output_hashes = metadata.get("output_hashes")
    input_hashes = metadata.get("input_hashes")
    if not isinstance(produced_files, list) or not isinstance(output_hashes, dict) or not isinstance(input_hashes, dict):
        return ArtifactStatus("unknown", directory, "metadata lacks validation hashes")

    expected_outputs = {_display_path(path, directory) for path in resolve_artifact_outputs(directory, node)}
    if expected_outputs:
        recorded_outputs = {relative for relative in produced_files if isinstance(relative, str)}
        if recorded_outputs != expected_outputs:
            missing = sorted(expected_outputs - recorded_outputs)
            extra = sorted(recorded_outputs - expected_outputs)
            if missing:
                return ArtifactStatus("incomplete", directory, f"missing output: {missing[0]}")
            return ArtifactStatus("stale", directory, f"output set changed: {extra[0]}")

    expected_inputs = {_display_path(path, root) for path in resolve_artifact_inputs(root, node)}
    if expected_inputs:
        recorded_inputs = {relative for relative in input_hashes if isinstance(relative, str)}
        if recorded_inputs != expected_inputs:
            missing = sorted(expected_inputs - recorded_inputs)
            extra = sorted(recorded_inputs - expected_inputs)
            changed = missing[0] if missing else extra[0]
            return ArtifactStatus("stale", directory, f"input set changed: {changed}")

    for relative in produced_files:
        if not isinstance(relative, str):
            return ArtifactStatus("invalid", directory, "artifact metadata has invalid produced file entry")
        output = directory / relative
        if not output.exists():
            return ArtifactStatus("incomplete", directory, f"missing output: {relative}")
        expected = output_hashes.get(relative)
        if expected is None:
            return ArtifactStatus("unknown", directory, f"metadata lacks output hash: {relative}")
        if _sha256_uri(output) != expected:
            return ArtifactStatus("invalid", directory, f"output hash mismatch: {relative}")
    for relative, expected in sorted(input_hashes.items()):
        if not isinstance(relative, str) or not isinstance(expected, str):
            return ArtifactStatus("invalid", directory, "artifact metadata has invalid input hash entry")
        source = root / relative
        if not source.exists():
            return ArtifactStatus("stale", directory, f"input missing: {relative}")
        if _sha256_uri(source) != expected:
            return ArtifactStatus("stale", directory, f"input changed: {relative}")
    planned_dependencies = _dependency_identities(node)
    metadata_dependencies = metadata.get("dependencies", {})
    if planned_dependencies and not isinstance(metadata_dependencies, dict):
        return ArtifactStatus("stale", directory, "dependency metadata missing")
    for goal_id, identity in planned_dependencies.items():
        if metadata_dependencies.get(goal_id) != identity:
            return ArtifactStatus("stale", directory, f"dependency identity changed: {goal_id}")
    return ArtifactStatus("hit", directory, "artifact metadata and validation hashes match")


def resolve_artifact_inputs(
    repo_root: str | Path,
    node: GoalInstance,
    config: ResolvedConfig | None = None,
) -> tuple[Path, ...]:
    from .goals import GOALS

    goal = GOALS.get(node.goal_id)
    if goal is None or goal.artifact is None:
        return ()
    params = _template_values(node, config)
    root = Path(repo_root)
    paths: set[Path] = set()
    for pattern in goal.artifact.input_globs:
        relative_pattern = pattern.format_map(params)
        paths.update(path for path in root.glob(relative_pattern) if path.is_file())
    return tuple(sorted(paths))


def resolve_artifact_outputs(
    directory: str | Path,
    node: GoalInstance,
    config: ResolvedConfig | None = None,
) -> tuple[Path, ...]:
    from .goals import GOALS

    goal = GOALS.get(node.goal_id)
    if goal is None or goal.artifact is None:
        return ()
    params = _template_values(node, config)
    root = Path(directory)
    return tuple(root / template.format_map(params) for template in goal.artifact.outputs)


def write_artifact_metadata(
    directory: Path,
    *,
    node: GoalInstance,
    produced: tuple[Path, ...],
    dependency_identities: Mapping[str, str],
    input_paths: tuple[Path, ...] = (),
    repo_root: str | Path | None = None,
) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    metadata_path = directory / "artifact.toml"
    metadata_path.write_text(
        _render_artifact_metadata(
            directory,
            node=node,
            produced=produced,
            dependency_identities=dependency_identities,
            input_paths=input_paths,
            repo_root=Path(repo_root) if repo_root is not None else directory.parents[3],
        ),
        encoding="utf-8",
    )
    return metadata_path


def _render_artifact_metadata(
    directory: Path,
    *,
    node: GoalInstance,
    produced: tuple[Path, ...],
    dependency_identities: Mapping[str, str],
    input_paths: tuple[Path, ...],
    repo_root: Path,
) -> str:
    lines = [
        f"goal = {_toml_value(node.goal_id)}",
        f"kind = {_toml_value(node.kind)}",
        f"identity = {_toml_value(node.identity)}",
        f"cacheable = {_toml_value(node.cacheable)}",
        f"public = {_toml_value(node.public)}",
        f"description = {_toml_value(node.description)}",
        "",
        "[params]",
    ]
    for key, value in node.params:
        lines.append(f"{_toml_key(key)} = {_toml_value(value)}")
    lines.extend(["", "[produced]"])
    relative_files = [_display_path(path, directory) for path in produced]
    lines.append(f"files = [{', '.join(_toml_value(path) for path in relative_files)}]")
    lines.extend(["", "[output_hashes]"])
    for path in produced:
        if path.exists():
            lines.append(f"{_toml_key(_display_path(path, directory))} = {_toml_value(_sha256_uri(path))}")
    lines.extend(["", "[input_hashes]"])
    for path in sorted(input_paths):
        if path.exists():
            lines.append(f"{_toml_key(_display_path(path, repo_root))} = {_toml_value(_sha256_uri(path))}")
    if dependency_identities:
        lines.extend(["", "[dependencies]"])
        for goal_id in sorted(dependency_identities):
            lines.append(f"{_toml_key(goal_id)} = {_toml_value(dependency_identities[goal_id])}")
    lines.append("")
    return "\n".join(lines)


def _template_values(node: GoalInstance, config: ResolvedConfig | None) -> dict[str, object]:
    values = dict(node.params)
    if config is not None:
        for key in getattr(config, "values", {}):
            values.setdefault(key, config.get(key))
    return values


def _display_path(path: Path, root: Path) -> str:
    try:
        return str(path.relative_to(root))
    except ValueError:
        return str(path)


def _dependency_identities(node: GoalInstance) -> dict[str, str]:
    return dict(getattr(node, "dependency_identities", ()))


def _sha256_uri(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _toml_key(key: str) -> str:
    return '"' + key.replace('\\', '\\\\').replace('"', '\\"') + '"'


def _toml_value(value: object) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    return '"' + str(value).replace('\\', '\\\\').replace('"', '\\"') + '"'


__all__ = [
    "ArtifactStatus",
    "artifact_dir",
    "artifacts_root",
    "read_artifact_status",
    "resolve_artifact_inputs",
    "resolve_artifact_outputs",
    "write_artifact_metadata",
]
