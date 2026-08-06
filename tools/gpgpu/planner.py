from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field

from .config import ResolvedConfig
from .goals import GOALS, GoalDefinition


class PlanError(ValueError):
    """Raised when a goal graph cannot be planned."""


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

    @property
    def key(self) -> str:
        return instance_key(self.goal_id, self.params)


@dataclass
class Plan:
    root: GoalInstance
    nodes: list[GoalInstance]

    def require_instance(self, goal_id: str) -> GoalInstance:
        matches = [node for node in self.nodes if node.goal_id == goal_id]
        if not matches:
            raise PlanError(f"Plan does not contain goal instance: {goal_id}")
        if len(matches) > 1:
            raise PlanError(f"Plan contains multiple instances for {goal_id}")
        return matches[0]

    def format_plan(self) -> str:
        lines: list[str] = []
        for node in self.nodes:
            label = {
                "artifact": "BUILD",
                "action": "ACTION",
                "service": "SERVICE",
                "check": "CHECK",
            }[node.kind]
            cache = " cacheable" if node.cacheable else ""
            lines.append(f"{label:<8} {node.goal_id}{format_params(node.params)}{cache}")
        return "\n".join(lines)

    def format_explain(self, config: ResolvedConfig) -> str:
        lines = [self.format_plan(), "", "Configuration provenance:"]
        for key, value, source in config.normalized_items():
            lines.append(f"  {key:<28} {str(value):<24} {source}")
        return "\n".join(lines)


def instance_key(goal_id: str, params: tuple[tuple[str, object], ...]) -> str:
    return goal_id + json.dumps(params, sort_keys=True, separators=(",", ":"))


def format_params(params: tuple[tuple[str, object], ...]) -> str:
    if not params:
        return ""
    body = ", ".join(f"{key}={value}" for key, value in params)
    return f"[{body}]"


class Planner:
    def __init__(self, config: ResolvedConfig):
        self.config = config
        self._instances: dict[str, GoalInstance] = {}

    def list_goals(self, *, include_internal: bool = False) -> list[GoalDefinition]:
        goals = [goal for goal in GOALS.values() if include_internal or goal.public]
        return sorted(goals, key=lambda goal: goal.goal_id)

    def plan(self, goal_id: str) -> Plan:
        if goal_id not in GOALS:
            raise PlanError(f"Unknown goal: {goal_id}")
        self._instances = {}
        root = self._require(goal_id)
        ordered = self._topological(root)
        return Plan(root=root, nodes=ordered)

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
        )
        self._instances[key] = instance
        return instance

    def _params_for(self, definition: GoalDefinition) -> tuple[tuple[str, object], ...]:
        names = definition.artifact_params if definition.kind == "artifact" else definition.runtime_params
        return tuple((name, self.config.get(name)) for name in names)

    def _dependency_goal_ids(self, goal_id: str) -> tuple[str, ...]:
        if goal_id == "sw.program.elf":
            return ("sw.program.compile_riscv",)
        if goal_id == "sw.program.image":
            return ("sw.program.elf",)
        if goal_id == "hw.board.bitstream":
            return ("hw.board.project",)
        if goal_id == "hw.board.program":
            return ("hw.board.bitstream",)
        if goal_id == "hw.board.kernel.load":
            return ("hw.board.program", "sw.program.image")
        if goal_id == "hw.board.kernel.run":
            return ("hw.board.kernel.load",)
        if goal_id == "demo.run":
            backend = self.config.get("backend")
            if backend == "fake":
                return ("sw.program.native",)
            if backend == "fpga-uart":
                # Requiring hw.board.kernel.load pulls in hw.board.program, hw.board.bitstream,
                # and sw.program.image exactly once through normal deduplication.
                return ("hw.board.kernel.load",)
            raise PlanError(f"Unsupported backend: {backend}")
        if goal_id == "test.rtl":
            return ("hw.rtl.assemble", "hw.rtl.sim_executable")
        if goal_id == "test.program":
            return ("sw.program.native", "sw.program.image")
        return ()

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
