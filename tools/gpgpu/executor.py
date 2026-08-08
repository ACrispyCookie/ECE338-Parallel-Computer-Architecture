from __future__ import annotations

from pathlib import Path

from .adapters import ADAPTERS
from .config import ResolvedConfig
from .run_result import RunResult, format_run_result


class ExecuteError(RuntimeError):
    """Raised when a goal has no compatibility adapter or cannot be executed."""


class Executor:
    """Minimal legacy compatibility executor.

    The executor is now a thin coordinator: it resolves a goal id to a
    registered domain adapter, passes the resolved configuration and repository
    root, and leaves workflow-specific command construction to adapter modules.
    Goals without explicit characterization and adapters remain planner-only.
    """

    def __init__(self, config: ResolvedConfig, *, repo_root: str | Path | None = None):
        self.config = config
        self.repo_root = Path(repo_root) if repo_root is not None else Path(__file__).resolve().parents[2]

    def run(self, goal_id: str) -> RunResult:
        adapter = ADAPTERS.get(goal_id)
        if adapter is None:
            raise ExecuteError(f"no executor adapter registered for {goal_id}")
        return adapter(self.config, self.repo_root)


__all__ = ["ExecuteError", "Executor", "RunResult", "format_run_result"]
