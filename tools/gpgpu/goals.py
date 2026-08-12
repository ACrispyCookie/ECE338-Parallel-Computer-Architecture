from __future__ import annotations

import re
import string
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

import yaml

from .config import SettingSpec

GoalKind = str


class GoalConfigError(ValueError):
    """Raised when declarative goal definitions are invalid."""


@dataclass(frozen=True)
class ArtifactOutputSpec:
    role: str
    description: str
    path_template: str
    artifact_type: str


@dataclass(frozen=True)
class ArtifactSpec:
    input_globs: tuple[str, ...] = ()
    outputs: tuple[ArtifactOutputSpec, ...] = ()


@dataclass(frozen=True)
class GoalDependency:
    goal_id: str
    when: tuple[tuple[str, object], ...] = ()
    note_kind: str | None = None
    note_subject: str | None = None
    note_reason: str | None = None


@dataclass(frozen=True)
class GoalNote:
    kind: str
    subject: str
    reason: str
    when: tuple[tuple[str, object], ...] = ()


@dataclass(frozen=True)
class GoalDefinition:
    goal_id: str
    kind: GoalKind
    public: bool
    description: str
    params: tuple[str, ...] = ()
    implementation_version: str = "mock-v1"
    lifecycle: str | None = None
    expected_outputs: tuple[str, ...] = ()
    side_effects: tuple[str, ...] = ()
    dependencies: tuple[GoalDependency, ...] = ()
    omitted_dependency_notes: tuple[GoalNote, ...] = ()
    artifact: ArtifactSpec | None = None

    @property
    def cacheable(self) -> bool:
        return self.kind == "artifact"


def _default_goals_path() -> Path:
    return Path(__file__).resolve().parents[2] / "config" / "goals.yaml"


def load_goals(path: str | Path, *, schema: Mapping[str, SettingSpec]) -> dict[str, GoalDefinition]:
    goals_path = Path(path)
    try:
        with goals_path.open("rb") as handle:
            data = yaml.safe_load(handle)
    except yaml.YAMLError as exc:
        raise GoalConfigError(f"Invalid YAML in {goals_path}: {exc}") from exc
    if data is None:
        data = {}
    goals_data = data.get("goals")
    if not isinstance(goals_data, dict) or not goals_data:
        raise GoalConfigError(f"{goals_path}: missing [goals] table")

    loaded: dict[str, GoalDefinition] = {}
    for goal_id, entry in _flatten_goal_definitions(goals_data).items():
        loaded[goal_id] = _load_goal(goal_id, entry, schema=schema)
    _validate_goal_references(loaded, schema=schema)
    return loaded


def _flatten_goal_definitions(goals_data: dict[str, object]) -> dict[str, object]:
    flat: dict[str, object] = {}

    def visit(prefix: str, value: object) -> None:
        if not isinstance(value, dict):
            flat[prefix] = value
            return
        if "kind" in value:
            flat[prefix] = value
            return
        for key, item in value.items():
            child = f"{prefix}.{key}" if prefix else str(key)
            visit(child, item)

    for key, value in goals_data.items():
        visit(str(key), value)
    return flat


def _load_goal(goal_id: str, entry: object, *, schema: Mapping[str, SettingSpec]) -> GoalDefinition:
    if not _valid_dotted_name(goal_id):
        raise GoalConfigError(f"Invalid goal id: {goal_id!r}")
    if not isinstance(entry, dict):
        raise GoalConfigError(f"Goal {goal_id} must be a table")
    allowed = {
        "kind",
        "public",
        "description",
        "params",
        "implementation_version",
        "lifecycle",
        "side_effects",
        "dependencies",
        "omitted_dependency_notes",
        "artifact",
    }
    unknown = set(entry) - allowed
    if unknown:
        raise GoalConfigError(f"Unknown goal field for {goal_id}: {sorted(unknown)[0]}")
    for required in ("kind", "public", "description"):
        if required not in entry:
            raise GoalConfigError(f"Goal {goal_id} missing {required}")
    kind = entry["kind"]
    if kind not in {"artifact", "action", "service", "check"}:
        raise GoalConfigError(f"Invalid goal kind for {goal_id}: {kind!r}")
    public = entry["public"]
    if not isinstance(public, bool):
        raise GoalConfigError(f"Goal {goal_id} public must be boolean")
    description = entry["description"]
    if not isinstance(description, str) or not description:
        raise GoalConfigError(f"Goal {goal_id} description must be a non-empty string")
    lifecycle = entry.get("lifecycle")
    if lifecycle is not None and (kind != "service" or not isinstance(lifecycle, str)):
        raise GoalConfigError(f"Goal {goal_id} lifecycle is only valid for service goals")

    params = _string_tuple(entry.get("params", ()), f"Goal {goal_id} params")
    side_effects = _string_tuple(entry.get("side_effects", ()), f"Goal {goal_id} side_effects")
    implementation_version = entry.get("implementation_version", "mock-v1")
    if not isinstance(implementation_version, str):
        raise GoalConfigError(f"Goal {goal_id} implementation_version must be a string")
    artifact = _load_artifact_spec(goal_id, entry.get("artifact"), schema=schema)
    expected_outputs = tuple(output.description for output in artifact.outputs) if artifact is not None else ()

    return GoalDefinition(
        goal_id=goal_id,
        kind=kind,
        public=public,
        description=description,
        params=params,
        implementation_version=implementation_version,
        lifecycle=lifecycle,
        expected_outputs=expected_outputs,
        side_effects=side_effects,
        dependencies=tuple(_load_dependencies(goal_id, entry.get("dependencies", ()), schema=schema)),
        omitted_dependency_notes=tuple(_load_notes(goal_id, entry.get("omitted_dependency_notes", ()), schema=schema)),
        artifact=artifact,
    )


def _load_dependencies(goal_id: str, entries: object, *, schema: Mapping[str, SettingSpec]) -> list[GoalDependency]:
    if entries in (None, ()):
        return []
    if not isinstance(entries, list):
        raise GoalConfigError(f"Goal {goal_id} dependencies must be a list")
    dependencies: list[GoalDependency] = []
    dependency_goals: set[str] = set()
    for item in entries:
        if not isinstance(item, dict):
            raise GoalConfigError(f"Goal {goal_id} dependency must be a table")
        dep_goal = item.get("goal")
        if not isinstance(dep_goal, str) or not dep_goal:
            raise GoalConfigError(f"Goal {goal_id} dependency missing goal")
        if dep_goal in dependency_goals:
            raise GoalConfigError(f"Goal {goal_id} duplicate dependency goal: {dep_goal}")
        dependency_goals.add(dep_goal)
        unknown = set(item) - {"goal", "when", "note_kind", "note_subject", "note_reason"}
        if unknown:
            raise GoalConfigError(f"Unknown dependency field for {goal_id}: {sorted(unknown)[0]}")
        dependencies.append(
            GoalDependency(
                goal_id=dep_goal,
                when=_condition_tuple(item.get("when", {}), schema=schema),
                note_kind=_optional_str(item.get("note_kind"), f"Goal {goal_id} dependency note_kind"),
                note_subject=_optional_str(item.get("note_subject"), f"Goal {goal_id} dependency note_subject"),
                note_reason=_optional_str(item.get("note_reason"), f"Goal {goal_id} dependency note_reason"),
            )
        )
    return dependencies


def _load_notes(goal_id: str, entries: object, *, schema: Mapping[str, SettingSpec]) -> list[GoalNote]:
    if entries in (None, ()):
        return []
    if not isinstance(entries, list):
        raise GoalConfigError(f"Goal {goal_id} omitted_dependency_notes must be a list")
    notes: list[GoalNote] = []
    for item in entries:
        if not isinstance(item, dict):
            raise GoalConfigError(f"Goal {goal_id} note must be a table")
        try:
            kind = item["kind"]
            subject = item["subject"]
            reason = item["reason"]
        except KeyError as exc:
            raise GoalConfigError(f"Goal {goal_id} note missing {exc.args[0]}") from exc
        if not all(isinstance(value, str) and value for value in (kind, subject, reason)):
            raise GoalConfigError(f"Goal {goal_id} note fields must be non-empty strings")
        notes.append(GoalNote(kind=kind, subject=subject, reason=reason, when=_condition_tuple(item.get("when", {}), schema=schema)))
    return notes


def _load_artifact_spec(goal_id: str, entry: object, *, schema: Mapping[str, SettingSpec]) -> ArtifactSpec | None:
    if entry is None:
        return None
    if not isinstance(entry, dict):
        raise GoalConfigError(f"Goal {goal_id} artifact spec must be a table")
    unknown = set(entry) - {"input_globs", "outputs"}
    if unknown:
        raise GoalConfigError(f"Unknown artifact field for {goal_id}: {sorted(unknown)[0]}")
    spec = ArtifactSpec(
        input_globs=_string_tuple(entry.get("input_globs", ()), f"Goal {goal_id} artifact.input_globs"),
        outputs=tuple(_load_artifact_outputs(goal_id, entry.get("outputs", {}), schema=schema)),
    )
    for value in spec.input_globs:
        _validate_artifact_path_template(value, schema=schema)
    for output in spec.outputs:
        _validate_artifact_path_template(output.path_template, schema=schema)
    return spec


def _load_artifact_outputs(
    goal_id: str,
    value: object,
    *,
    schema: Mapping[str, SettingSpec],
) -> list[ArtifactOutputSpec]:
    if value in (None, {}):
        return []
    if not isinstance(value, dict):
        raise GoalConfigError(f"Goal {goal_id} artifact.outputs must be a table")
    outputs: list[ArtifactOutputSpec] = []
    for role, entry in value.items():
        if not isinstance(role, str) or not re.fullmatch(r"[A-Za-z0-9_]+", role):
            raise GoalConfigError(f"Invalid artifact output role for {goal_id}: {role!r}")
        if not isinstance(entry, dict):
            raise GoalConfigError(f"Goal {goal_id} artifact output {role} must be a table")
        unknown = set(entry) - {"description", "path", "type"}
        if unknown:
            raise GoalConfigError(f"Unknown artifact output field for {goal_id}.{role}: {sorted(unknown)[0]}")
        description = entry.get("description")
        path_template = entry.get("path")
        artifact_type = entry.get("type")
        if not isinstance(description, str) or not description:
            raise GoalConfigError(f"Goal {goal_id} artifact output {role} missing description")
        if not isinstance(path_template, str) or not path_template:
            raise GoalConfigError(f"Goal {goal_id} artifact output {role} missing path")
        if not isinstance(artifact_type, str) or not artifact_type:
            raise GoalConfigError(f"Goal {goal_id} artifact output {role} missing type")
        _validate_artifact_path_template(path_template, schema=schema)
        outputs.append(ArtifactOutputSpec(role=role, description=description, path_template=path_template, artifact_type=artifact_type))
    return outputs


def _validate_goal_references(goals: Mapping[str, GoalDefinition], *, schema: Mapping[str, SettingSpec]) -> None:
    for goal in goals.values():
        for param in goal.params:
            if param not in schema:
                raise GoalConfigError(f"Unknown setting referenced by {goal.goal_id}: {param}")
        for dependency in goal.dependencies:
            if dependency.goal_id not in goals:
                raise GoalConfigError(f"Unknown dependency goal for {goal.goal_id}: {dependency.goal_id}")


def _condition_tuple(mapping: object, *, schema: Mapping[str, SettingSpec]) -> tuple[tuple[str, object], ...]:
    if mapping in (None, {}):
        return ()
    if not isinstance(mapping, dict):
        raise GoalConfigError("Dependency conditions must be a table")
    pairs: list[tuple[str, object]] = []
    for key, value in mapping.items():
        if key not in schema:
            raise GoalConfigError(f"Unknown setting referenced in condition: {key}")
        pairs.append((key, value))
    return tuple(sorted(pairs))


def _validate_artifact_path_template(template: str, *, schema: Mapping[str, SettingSpec]) -> None:
    if template.startswith("/"):
        raise GoalConfigError("artifact paths must be repository-relative")
    parts = Path(template).parts
    if ".." in parts:
        raise GoalConfigError("artifact paths must not escape the repository")
    for _, field_name, _, _ in string.Formatter().parse(template):
        if field_name is not None and field_name not in schema:
            raise GoalConfigError(f"Unknown artifact placeholder: {field_name}")


def _string_tuple(value: object, label: str) -> tuple[str, ...]:
    if value in (None, ()):
        return ()
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise GoalConfigError(f"{label} must be a list of strings")
    return tuple(value)


def _optional_str(value: object, label: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise GoalConfigError(f"{label} must be a string")
    return value


def _valid_dotted_name(value: str) -> bool:
    return bool(re.fullmatch(r"[A-Za-z0-9_]+(\.[A-Za-z0-9_]+)*", value))


from .config import ConfigResolver  # noqa: E402  # imported after definitions to keep loader types available

GOALS = load_goals(_default_goals_path(), schema=ConfigResolver.SCHEMA)

__all__ = [
    "ArtifactOutputSpec",
    "ArtifactSpec",
    "GoalConfigError",
    "GoalDefinition",
    "GoalDependency",
    "GoalKind",
    "GoalNote",
    "GOALS",
    "load_goals",
]
