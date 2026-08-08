from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .config import ResolvedConfig


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


class Executor:
    """Minimal legacy compatibility executor.

    The executor is a thin coordinator: it resolves a goal id to a registered
    domain adapter, passes the resolved configuration and repository root, and
    leaves workflow-specific command construction to adapter modules. Goals
    without explicit characterization and adapters remain planner-only.
    """

    def __init__(self, config: ResolvedConfig, *, repo_root: str | Path | None = None):
        self.config = config
        self.repo_root = Path(repo_root) if repo_root is not None else Path(__file__).resolve().parents[2]

    def run(self, goal_id: str, *, artifact_identity: str) -> RunResult:
        from .adapters import ADAPTERS

        adapter = ADAPTERS.get(goal_id)
        if adapter is None:
            raise ExecuteError(f"no executor adapter registered for {goal_id}")
        return adapter(self.config, self.repo_root, artifact_identity)


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
            try:
                display = path.relative_to(root)
            except ValueError:
                display = path
            lines.append(f"  {display}")
    else:
        lines.extend(["", "Produced:", "  <none verified>"])
    lines.append("")
    lines.append(f"Exit code: {result.returncode}")
    return "\n".join(lines)


def _format_command(command: tuple[str, ...]) -> str:
    return " ".join(command)


def _indent(text: str) -> str:
    return "\n".join(f"  {line}" for line in text.splitlines())


__all__ = ["ExecuteError", "Executor", "RunResult", "format_run_result"]
