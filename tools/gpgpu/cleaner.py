from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from shutil import rmtree

from .artifacts import artifact_dir, artifacts_root
from .planner import GoalInstance, Plan


class CleanError(RuntimeError):
    """Raised when clean would touch an unsafe or unsupported path."""


@dataclass(frozen=True)
class CleanRecord:
    node: GoalInstance
    path: Path
    status: str
    reason: str | None = None


@dataclass(frozen=True)
class CleanSummary:
    root: GoalInstance
    records: tuple[CleanRecord, ...]

    @property
    def would_remove_count(self) -> int:
        return sum(1 for record in self.records if record.status == "would-remove")

    @property
    def removed_count(self) -> int:
        return sum(1 for record in self.records if record.status == "removed")

    @property
    def missing_count(self) -> int:
        return sum(1 for record in self.records if record.status == "missing")

    @property
    def skipped_count(self) -> int:
        return sum(1 for record in self.records if record.status == "skipped")


class Cleaner:
    def __init__(self, *, repo_root: str | Path | None = None):
        self.repo_root = Path(repo_root) if repo_root is not None else Path(__file__).resolve().parents[2]
        self.artifacts_root = artifacts_root(self.repo_root)

    def clean_plan(self, plan: Plan, *, deps: bool = False, dry_run: bool = False) -> CleanSummary:
        records: list[CleanRecord] = []
        for node in self._selected_nodes(plan, deps=deps):
            path = artifact_dir(self.repo_root, node)
            self._assert_safe_artifact_path(path)
            if not path.exists():
                records.append(CleanRecord(node=node, path=path, status="missing"))
                continue
            if dry_run:
                records.append(CleanRecord(node=node, path=path, status="would-remove"))
                continue
            rmtree(path)
            records.append(CleanRecord(node=node, path=path, status="removed"))
        return CleanSummary(root=plan.root, records=tuple(records))

    def _selected_nodes(self, plan: Plan, *, deps: bool) -> tuple[GoalInstance, ...]:
        if not deps:
            if plan.root.kind != "artifact":
                raise CleanError("clean supports artifact goals only unless --deps is used")
            return (plan.root,)
        return tuple(node for node in plan.nodes if node.kind == "artifact")

    def _assert_safe_artifact_path(self, path: Path) -> None:
        if path.is_symlink():
            raise CleanError(f"refusing to clean symlink artifact path: {path}")
        resolved = path.resolve()
        artifacts = self.artifacts_root.resolve()
        if resolved in {self.repo_root.resolve() / "out", artifacts}:
            raise CleanError(f"refusing to clean broad artifact path: {path}")
        try:
            relative = resolved.relative_to(artifacts)
        except ValueError as exc:
            raise CleanError(f"refusing to clean path outside out/artifacts: {path}") from exc
        if len(relative.parts) < 2:
            raise CleanError(f"refusing to clean broad artifact path: {path}")


def format_clean_summary(
    summary: CleanSummary,
    *,
    dry_run: bool,
    deps: bool,
    repo_root: str | Path | None = None,
) -> str:
    root = Path(repo_root) if repo_root is not None else Path(__file__).resolve().parents[2]
    mode = f"{'dry-run' if dry_run else 'delete'} {'with dependencies' if deps else 'root-only'}"
    lines = [f"Clean: {summary.root.goal_id}", f"Mode: {mode}", ""]
    for record in summary.records:
        lines.append(f"{_status_label(record.status):<13} {record.node.goal_id:<18} {_display_path(record.path, root)}")
        if record.reason:
            lines.append(f"  reason: {record.reason}")
    if not summary.records:
        lines.append("<no artifact goals selected>")
    lines.extend([
        "",
        "Summary:",
        f"  would-remove: {summary.would_remove_count}",
        f"  removed:      {summary.removed_count}",
        f"  missing:      {summary.missing_count}",
        f"  skipped:      {summary.skipped_count}",
    ])
    return "\n".join(lines).rstrip()


def _status_label(status: str) -> str:
    return {
        "would-remove": "WOULD REMOVE",
        "removed": "REMOVED",
        "missing": "MISSING",
        "skipped": "SKIPPED",
    }[status]


def _display_path(path: Path, root: Path) -> str:
    try:
        return str(path.relative_to(root))
    except ValueError:
        return str(path)


__all__ = ["CleanError", "CleanRecord", "CleanSummary", "Cleaner", "format_clean_summary"]
