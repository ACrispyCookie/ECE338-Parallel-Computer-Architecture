from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

from .artifacts import ArtifactStatus, read_artifact_status
from .config import ResolvedConfig
from .goals import GOALS, GoalDefinition


class PlanError(ValueError):
    """Raised when a goal graph cannot be planned."""


@dataclass(frozen=True)
class PlanNote:
    kind: str
    subject: str
    reason: str


@dataclass(frozen=True)
class GoalInstance:
    goal_id: str
    kind: str
    params: tuple[tuple[str, object], ...]
    identity: str
    cacheable: bool
    public: bool
    description: str
    lifecycle: str | None = None
    dependencies: tuple[str, ...] = ()
    expected_outputs: tuple[str, ...] = ()
    side_effects: tuple[str, ...] = ()
    cache_status: ArtifactStatus | None = None

    @property
    def key(self) -> str:
        return instance_key(self.goal_id, self.params)


@dataclass
class Plan:
    root: GoalInstance
    nodes: list[GoalInstance]
    notes: tuple[PlanNote, ...] = ()

    def require_instance(self, goal_id: str) -> GoalInstance:
        matches = [node for node in self.nodes if node.goal_id == goal_id]
        if not matches:
            raise PlanError(f"Plan does not contain goal instance: {goal_id}")
        if len(matches) > 1:
            raise PlanError(f"Plan contains multiple instances for {goal_id}")
        return matches[0]

    def format_plan(self, *, verbose: bool = False) -> str:
        lines: list[str] = [f"Plan: {self.root.goal_id} ({len(self.nodes)} goals)"]
        for index, node in enumerate(self.nodes, start=1):
            label = {
                "artifact": "BUILD",
                "action": "ACTION",
                "service": "SERVICE",
                "check": "CHECK",
            }[node.kind]
            marker = {
                "artifact": "◇",
                "action": "⚡",
                "service": "◆",
                "check": "✓",
            }[node.kind]
            cache = _format_cache_column(node)
            params = format_params(node.params, verbose=verbose)
            if cache:
                lines.append(f"{label:<8} {cache:<10} {marker} {index:02d}. {node.goal_id:<24} {params}".rstrip())
            else:
                lines.append(f"{label:<8} {marker} {index:02d}. {node.goal_id:<24} {params}".rstrip())
            if verbose:
                lines.extend(_format_node_metadata(node))
        if verbose and self.notes:
            if lines:
                lines.append("")
            lines.append("Notes:")
            for note in self.notes:
                lines.append(f"  {note.kind.upper():<8} {note.subject}")
                lines.append(f"           reason: {note.reason}")
        return "\n".join(lines)

    def format_explain(self, config: ResolvedConfig, *, verbose: bool = False) -> str:
        lines = [self.format_plan(verbose=verbose)]
        if verbose:
            artifact_nodes = [node for node in self.nodes if node.kind == "artifact"]
            if artifact_nodes:
                lines.extend(["", "Artifact identities:"])
                for node in artifact_nodes:
                    lines.append(f"  {node.goal_id:<24} {node.identity}")
        lines.extend(["", "Configuration provenance:"])
        for key, value, source in config.normalized_items():
            lines.append(f"  {key:<28} {str(value):<24} {source}")
        return "\n".join(lines)


def _format_cache_column(node: GoalInstance) -> str:
    if node.kind != "artifact" or node.cache_status is None:
        return ""
    return "CACHE HIT" if node.cache_status.is_hit else "CACHE MISS"


def _format_node_metadata(node: GoalInstance) -> list[str]:
    lines: list[str] = []
    if node.cache_status is not None and node.kind == "artifact":
        status = node.cache_status
        lines.append(f"           ↳ cache       {status.state}")
        lines.append(f"           ↳ cache path  {status.path}")
        lines.append(f"           ↳ cache why   {status.reason}")
    if node.expected_outputs:
        lines.append(f"           ↳ outputs      {', '.join(node.expected_outputs)}")
    if node.side_effects:
        lines.append(f"           ↳ effects      {', '.join(node.side_effects)}")
    if node.lifecycle:
        lines.append(f"           ↳ lifecycle    {node.lifecycle}")
    return lines


def instance_key(goal_id: str, params: tuple[tuple[str, object], ...]) -> str:
    return goal_id + json.dumps(params, sort_keys=True, separators=(",", ":"))


def format_params(params: tuple[tuple[str, object], ...], *, verbose: bool = False) -> str:
    if not params:
        return ""
    shown = params if verbose else params[:3]
    body = ", ".join(f"{key}={value}" for key, value in shown)
    if not verbose and len(params) > len(shown):
        body = f"{body}, +{len(params) - len(shown)} params"
    return f"[{body}]"


class Planner:
    def __init__(self, config: ResolvedConfig, *, repo_root: str | Path | None = None):
        self.config = config
        self.repo_root = Path(repo_root) if repo_root is not None else Path.cwd()
        self._instances: dict[str, GoalInstance] = {}
        self._notes: list[PlanNote] = []

    def list_goals(self, *, include_internal: bool = False) -> list[GoalDefinition]:
        goals = [goal for goal in GOALS.values() if include_internal or goal.public]
        return sorted(goals, key=lambda goal: goal.goal_id)

    def plan(self, goal_id: str) -> Plan:
        if goal_id not in GOALS:
            raise PlanError(f"Unknown goal: {goal_id}")
        self._instances = {}
        self._notes = []
        root = self._require(goal_id)
        ordered = self._topological(root)
        return Plan(root=root, nodes=ordered, notes=tuple(self._notes))

    def _require(self, goal_id: str) -> GoalInstance:
        definition = GOALS[goal_id]
        params = self._params_for(definition)
        key = instance_key(goal_id, params)
        if key in self._instances:
            return self._instances[key]

        dependency_instances = tuple(self._require(dep_id) for dep_id in self._dependency_goal_ids(goal_id))
        dependency_keys = tuple(instance.key for instance in dependency_instances)
        identity = self._identity_for(
            definition,
            params,
            tuple(instance.identity for instance in dependency_instances),
        )
        instance = GoalInstance(
            goal_id=definition.goal_id,
            kind=definition.kind,
            params=params,
            identity=identity,
            cacheable=definition.cacheable,
            public=definition.public,
            description=definition.description,
            lifecycle=definition.lifecycle,
            dependencies=dependency_keys,
            expected_outputs=definition.expected_outputs,
            side_effects=definition.side_effects,
        )
        if definition.kind == "artifact":
            instance = GoalInstance(
                goal_id=instance.goal_id,
                kind=instance.kind,
                params=instance.params,
                identity=instance.identity,
                cacheable=instance.cacheable,
                public=instance.public,
                description=instance.description,
                lifecycle=instance.lifecycle,
                dependencies=instance.dependencies,
                expected_outputs=instance.expected_outputs,
                side_effects=instance.side_effects,
                cache_status=read_artifact_status(self.repo_root, instance),
            )
        self._instances[key] = instance
        return instance

    def _params_for(self, definition: GoalDefinition) -> tuple[tuple[str, object], ...]:
        names = definition.artifact_params if definition.kind == "artifact" else definition.runtime_params
        return tuple((name, self.config.get(name)) for name in names)

    def _dependency_goal_ids(self, goal_id: str) -> tuple[str, ...]:
        definition = GOALS[goal_id]
        included: list[str] = []
        for dependency in definition.dependencies:
            if not self._condition_matches(dependency.when):
                continue
            included.append(dependency.goal_id)
            if dependency.note_kind is not None:
                self._notes.append(
                    PlanNote(
                        kind=dependency.note_kind,
                        subject=dependency.note_subject or dependency.goal_id,
                        reason=dependency.note_reason or "dependency condition matched",
                    )
                )
        for note in definition.omitted_dependency_notes:
            if self._condition_matches(note.when):
                self._notes.append(PlanNote(kind=note.kind, subject=note.subject, reason=note.reason))
        return tuple(included)

    def _condition_matches(self, conditions: tuple[tuple[str, object], ...]) -> bool:
        return all(self.config.get(key) == value for key, value in conditions)

    def _identity_for(
        self,
        definition: GoalDefinition,
        params: tuple[tuple[str, object], ...],
        dependency_keys: tuple[str, ...],
    ) -> str:
        if definition.kind != "artifact":
            return "uncached-action" if definition.kind == "action" else definition.kind
        payload = {
            "goal": definition.goal_id,
            "implementation_version": definition.implementation_version,
            "params": params,
            "dependencies": sorted(dependency_keys),
        }
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()[:16]

    def _topological(self, root: GoalInstance) -> list[GoalInstance]:
        by_key = {instance.key: instance for instance in self._instances.values()}
        seen: set[str] = set()
        ordered: list[GoalInstance] = []

        def visit(instance: GoalInstance) -> None:
            if instance.key in seen:
                return
            for dep_key in instance.dependencies:
                visit(by_key[dep_key])
            seen.add(instance.key)
            ordered.append(instance)

        visit(root)
        return ordered
