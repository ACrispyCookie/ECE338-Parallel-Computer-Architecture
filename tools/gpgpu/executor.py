from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from time import perf_counter
from typing import Mapping

from .artifacts import artifact_dir, write_artifact_metadata
from .config import ResolvedConfig
from .planner import GoalInstance, Plan


class ExecuteError(RuntimeError):
    """Raised when a goal has no compatibility adapter or cannot be executed."""


@dataclass(frozen=True)
class RunResult:
    goal_id: str
    command: tuple[str, ...]
    returncode: int
    produced: tuple[Path, ...]
    stdout: str = ""
    stderr: str = ""


@dataclass(frozen=True)
class ExecutionContext:
    config: ResolvedConfig
    repo_root: Path
    node: GoalInstance
    artifact_dir: Path
    dependency_artifacts: Mapping[str, tuple[Path, ...]]

    @property
    def goal_id(self) -> str:
        return self.node.goal_id

    @property
    def artifact_identity(self) -> str:
        return self.node.identity


@dataclass(frozen=True)
class RunRecord:
    node: GoalInstance
    status: str
    result: RunResult | None = None
    reason: str | None = None


@dataclass(frozen=True)
class RunSummary:
    root: GoalInstance
    planned_count: int
    executable_count: int
    records: tuple[RunRecord, ...]

    @property
    def returncode(self) -> int:
        for record in self.records:
            if record.status == "failed" and record.result is not None:
                return record.result.returncode or 1
        return 0

    @property
    def completed_count(self) -> int:
        return sum(1 for record in self.records if record.status == "done")

    @property
    def skipped_count(self) -> int:
        return sum(1 for record in self.records if record.status in {"skipped", "stopped"})

    @property
    def failed_count(self) -> int:
        return sum(1 for record in self.records if record.status == "failed")


class Executor:
    """Minimal legacy compatibility executor.

    The executor is a thin coordinator: it resolves planned goal instances to
    registered domain adapters, computes normalized artifact directories, and
    leaves workflow-specific command construction to adapter modules.
    """

    def __init__(
        self,
        config: ResolvedConfig,
        *,
        repo_root: str | Path | None = None,
        adapters: Mapping[str, object] | None = None,
    ):
        self.config = config
        self.repo_root = Path(repo_root) if repo_root is not None else Path(__file__).resolve().parents[2]
        self._adapters = adapters

    def run_plan(self, plan: Plan, *, reporter: object | None = None) -> RunSummary:
        adapters = self._adapter_mapping()
        self._preflight(plan, adapters)
        executable_count = sum(1 for node in plan.nodes if node.goal_id in adapters)
        records: list[RunRecord] = []
        dependency_artifacts: dict[str, tuple[Path, ...]] = {}
        dependency_identities: dict[str, str] = {}
        nodes_by_key = {node.key: node for node in plan.nodes}
        if reporter is not None:
            reporter.plan_started(plan, executable_count)  # type: ignore[attr-defined]

        for index, node in enumerate(plan.nodes):
            adapter = adapters.get(node.goal_id)
            if adapter is None:
                if self._can_skip_missing_adapter(node):
                    reason = "internal planner-only artifact has no registered adapter"
                    records.append(RunRecord(node=node, status="skipped", reason=reason))
                    if reporter is not None:
                        reporter.goal_skipped(node, reason)  # type: ignore[attr-defined]
                    continue
                raise ExecuteError(f"no executor adapter registered for required goal {node.goal_id}")

            context = self._context_for(node, dependency_artifacts)
            records.append(RunRecord(node=node, status="running"))
            if reporter is not None:
                reporter.goal_started(node, context)  # type: ignore[attr-defined]
            started_at = perf_counter()
            result = adapter(context)  # type: ignore[misc]
            elapsed = perf_counter() - started_at
            if result.returncode != 0:
                records.append(RunRecord(node=node, status="failed", result=result))
                if reporter is not None:
                    reporter.goal_failed(node, result, elapsed)  # type: ignore[attr-defined]
                for remaining in plan.nodes[index + 1:]:
                    if remaining.goal_id in adapters:
                        reason = f"dependency {node.goal_id} failed"
                        records.append(RunRecord(node=remaining, status="stopped", reason=reason))
                        if reporter is not None:
                            reporter.goal_stopped(remaining, reason)  # type: ignore[attr-defined]
                summary = RunSummary(
                    root=plan.root,
                    planned_count=len(plan.nodes),
                    executable_count=executable_count,
                    records=tuple(records),
                )
                if reporter is not None:
                    reporter.plan_finished(summary)  # type: ignore[attr-defined]
                return summary
            records.append(RunRecord(node=node, status="done", result=result))
            if node.kind == "artifact":
                write_artifact_metadata(
                    context.artifact_dir,
                    node=node,
                    produced=result.produced,
                    dependency_identities=self._direct_dependency_identities(
                        node,
                        nodes_by_key=nodes_by_key,
                        completed=dependency_identities,
                    ),
                )
            dependency_artifacts[node.goal_id] = result.produced
            dependency_identities[node.goal_id] = node.identity
            if reporter is not None:
                reporter.goal_completed(node, result, elapsed)  # type: ignore[attr-defined]

        summary = RunSummary(
            root=plan.root,
            planned_count=len(plan.nodes),
            executable_count=executable_count,
            records=tuple(records),
        )
        if reporter is not None:
            reporter.plan_finished(summary)  # type: ignore[attr-defined]
        return summary

    def run(self, goal_id: str, *, artifact_identity: str) -> RunResult:
        adapters = self._adapter_mapping()
        adapter = adapters.get(goal_id)
        if adapter is None:
            raise ExecuteError(f"no executor adapter registered for {goal_id}")
        node = GoalInstance(
            goal_id=goal_id,
            kind="artifact",
            params=(),
            identity=artifact_identity,
            cacheable=True,
            public=True,
            description="direct compatibility run",
        )
        return adapter(self._context_for(node, {}))  # type: ignore[misc]

    def _direct_dependency_identities(
        self,
        node: GoalInstance,
        *,
        nodes_by_key: Mapping[str, GoalInstance],
        completed: Mapping[str, str],
    ) -> dict[str, str]:
        identities: dict[str, str] = {}
        for dependency_key in node.dependencies:
            dependency = nodes_by_key[dependency_key]
            if dependency.goal_id in completed:
                identities[dependency.goal_id] = completed[dependency.goal_id]
        return identities

    def _adapter_mapping(self):
        if self._adapters is not None:
            return self._adapters
        from .adapters import ADAPTERS

        return ADAPTERS

    def _preflight(self, plan: Plan, adapters: Mapping[str, object]) -> None:
        for node in plan.nodes:
            if node.goal_id in adapters or self._can_skip_missing_adapter(node):
                continue
            raise ExecuteError(f"no executor adapter registered for required goal {node.goal_id}")

    def _can_skip_missing_adapter(self, node: GoalInstance) -> bool:
        return not node.public and node.kind == "artifact"

    def _context_for(
        self,
        node: GoalInstance,
        dependency_artifacts: Mapping[str, tuple[Path, ...]],
    ) -> ExecutionContext:
        return ExecutionContext(
            config=self.config,
            repo_root=self.repo_root,
            node=node,
            artifact_dir=artifact_dir(self.repo_root, node),
            dependency_artifacts=dependency_artifacts,
        )


def format_run_summary(summary: RunSummary, *, repo_root: str | Path | None = None, color: bool = False) -> str:
    root = Path(repo_root) if repo_root is not None else Path(__file__).resolve().parents[2]
    lines = [
        f"Run: {summary.root.goal_id}",
        f"Plan: {summary.executable_count} executable goals, {summary.planned_count} planned goals",
        "",
    ]
    running_index = 0
    executable_total = summary.executable_count
    for record in summary.records:
        marker = _kind_marker(record.node.kind)
        if record.status in {"running", "done", "failed"}:
            if record.status == "running":
                running_index += 1
            ordinal = f"{running_index:02d}/{executable_total:02d}"
        else:
            ordinal = "--/--"
        label = {
            "running": "RUNNING",
            "done": "DONE",
            "failed": "FAILED",
            "skipped": "SKIPPED",
            "stopped": "STOPPED",
        }[record.status]
        display_label = _paint_status(f"{label:<9}", record.status, color)
        lines.append(f"{marker} {ordinal} {display_label} {record.node.goal_id}")
        if record.status == "running":
            lines.append(f"   id:       {record.node.identity}")
            lines.append(f"   output:   {_artifact_display(root, record.node)}")
        if record.reason:
            lines.append(f"   reason:   {record.reason}")
        if record.result is not None:
            lines.append(f"   command:  {_format_command(record.result.command)}")
            if record.result.produced:
                lines.append("   produced:")
                for path in record.result.produced:
                    lines.append(f"     {_display_path(path, root)}")
            if record.status == "failed":
                lines.append(f"   exit:     {record.result.returncode}")
                if record.result.stdout.strip():
                    lines.extend(["", "stdout:", _indent(record.result.stdout.rstrip())])
                if record.result.stderr.strip():
                    lines.extend(["", "stderr:", _indent(record.result.stderr.rstrip())])
        lines.append("")
    lines.extend(
        [
            "Summary:",
            f"  completed: {summary.completed_count}",
            f"  skipped:   {summary.skipped_count}",
            f"  failed:    {summary.failed_count}",
        ]
    )
    return "\n".join(lines).rstrip()


def format_run_result(result: RunResult, *, repo_root: str | Path | None = None) -> str:
    root = Path(repo_root) if repo_root is not None else Path(__file__).resolve().parents[2]
    lines = [f"Run: {result.goal_id}", "", "Executing legacy adapter:", f"  {_format_command(result.command)}"]
    if result.stdout.strip():
        lines.extend(["", "Legacy stdout:", _indent(result.stdout.rstrip())])
    if result.stderr.strip():
        lines.extend(["", "Legacy stderr:", _indent(result.stderr.rstrip())])
    if result.produced:
        lines.extend(["", "Produced:"])
        for path in result.produced:
            lines.append(f"  {_display_path(path, root)}")
    else:
        lines.extend(["", "Produced:", "  <none verified>"])
    lines.append("")
    lines.append(f"Exit code: {result.returncode}")
    return "\n".join(lines)


def _kind_marker(kind: str) -> str:
    return {
        "artifact": "◇",
        "action": "⚡",
        "service": "◆",
        "check": "✓",
    }.get(kind, "•")


def _paint_status(text: str, status: str, enabled: bool) -> str:
    if not enabled:
        return text
    colors = {
        "running": "\033[36m",
        "done": "\033[32m",
        "failed": "\033[31m",
        "skipped": "\033[90m",
        "stopped": "\033[33m",
    }
    return f"{colors.get(status, '')}{text}\033[0m"


def _artifact_display(root: Path, node: GoalInstance) -> str:
    # Display policy only; actual layout is computed in _context_for.
    return f"out/artifacts/{node.goal_id}/.../{node.identity}"


def _display_path(path: Path, root: Path) -> str:
    try:
        return str(path.relative_to(root))
    except ValueError:
        return str(path)


def _format_command(command: tuple[str, ...]) -> str:
    return " ".join(command)


def _indent(text: str) -> str:
    return "\n".join(f"  {line}" for line in text.splitlines())


__all__ = [
    "ExecuteError",
    "ExecutionContext",
    "Executor",
    "RunRecord",
    "RunResult",
    "RunSummary",
    "format_run_result",
    "format_run_summary",
]
