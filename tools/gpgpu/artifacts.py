from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Mapping

if TYPE_CHECKING:
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
    directory = artifact_dir(repo_root, node)
    metadata_path = directory / "artifact.toml"
    if not directory.exists():
        return ArtifactStatus("miss", directory, "artifact directory missing")
    if not directory.is_dir():
        return ArtifactStatus("miss", directory, "artifact path is not a directory")
    if not metadata_path.exists():
        return ArtifactStatus("miss", directory, "artifact metadata missing")
    try:
        with metadata_path.open("rb") as handle:
            metadata = tomllib.load(handle)
    except tomllib.TOMLDecodeError:
        return ArtifactStatus("miss", directory, "artifact metadata invalid")
    if metadata.get("goal") != node.goal_id or metadata.get("identity") != node.identity:
        return ArtifactStatus("miss", directory, "artifact metadata mismatch")
    return ArtifactStatus("hit", directory, "artifact metadata matches")


def write_artifact_metadata(
    directory: Path,
    *,
    node: GoalInstance,
    produced: tuple[Path, ...],
    dependency_identities: Mapping[str, str],
) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    metadata_path = directory / "artifact.toml"
    metadata_path.write_text(
        _render_artifact_metadata(
            directory,
            node=node,
            produced=produced,
            dependency_identities=dependency_identities,
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
    if dependency_identities:
        lines.extend(["", "[dependencies]"])
        for goal_id in sorted(dependency_identities):
            lines.append(f"{_toml_key(goal_id)} = {_toml_value(dependency_identities[goal_id])}")
    lines.append("")
    return "\n".join(lines)


def _display_path(path: Path, root: Path) -> str:
    try:
        return str(path.relative_to(root))
    except ValueError:
        return str(path)


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
    "write_artifact_metadata",
]
