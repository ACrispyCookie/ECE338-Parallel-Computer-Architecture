from __future__ import annotations

from pathlib import Path
from typing import Any, TextIO


RESET = "\033[0m"
STATUS_COLORS = {
    "running": "\033[36m",
    "done": "\033[32m",
    "failed": "\033[31m",
    "skipped": "\033[90m",
    "stopped": "\033[33m",
}


class RunReporter:
    """Progress event sink for `gpgpu run` graph execution."""

    def plan_started(self, plan: Any, executable_count: int) -> None:
        pass

    def goal_skipped(self, node: Any, reason: str) -> None:
        pass

    def goal_started(self, node: Any, context: Any) -> None:
        pass

    def goal_completed(self, node: Any, result: Any, elapsed: float) -> None:
        pass

    def goal_failed(self, node: Any, result: Any, elapsed: float) -> None:
        pass

    def goal_stopped(self, node: Any, reason: str) -> None:
        pass

    def plan_finished(self, summary: Any) -> None:
        pass


class PlainRunReporter(RunReporter):
    """Deterministic compact progress reporter for CI, pipes, and tests."""

    def __init__(self, stream: TextIO, *, repo_root: str | Path | None = None, color: bool = False):
        self.stream = stream
        self.repo_root = Path(repo_root) if repo_root is not None else Path.cwd()
        self.color = color
        self._executable_total = 0
        self._running_index = 0

    def plan_started(self, plan: Any, executable_count: int) -> None:
        self._executable_total = executable_count
        self.stream.write(f"gpgpu run {plan.root.goal_id}\n")
        self.stream.write(f"Plan: {self._executable_total} executable goals, {len(plan.nodes)} planned goals\n\n")

    def goal_skipped(self, node: Any, reason: str) -> None:
        self.stream.write(f"{_paint('∙', 'skipped', self.color)} {node.goal_id}  skipped\n")
        self.stream.write(f"  reason: {reason}\n")

    def goal_started(self, node: Any, context: Any) -> None:
        self._running_index += 1
        self.stream.write(f"[{self._running_index}/{self._executable_total}] {node.goal_id}\n")
        self.stream.write(f"  id:  {node.identity}\n")
        self.stream.write(f"  out: {_display_path(context.artifact_dir, self.repo_root)}\n")

    def goal_completed(self, node: Any, result: Any, elapsed: float) -> None:
        produced = _produced_summary(result.produced)
        suffix = f"  produced {produced}" if produced else "  produced <none verified>"
        self.stream.write(f"{_paint('✓', 'done', self.color)} {node.goal_id}  {_format_elapsed(elapsed)}{suffix}\n")

    def goal_failed(self, node: Any, result: Any, elapsed: float) -> None:
        self.stream.write(
            f"{_paint('✗', 'failed', self.color)} {node.goal_id}  {_format_elapsed(elapsed)}  failed exit {result.returncode}\n\n"
        )
        self.stream.write("Command:\n")
        self.stream.write(f"  {_format_command(result.command)}\n")
        if result.stdout.strip():
            self.stream.write("\nstdout:\n")
            self.stream.write(_indent(result.stdout.rstrip()) + "\n")
        if result.stderr.strip():
            self.stream.write("\nstderr:\n")
            self.stream.write(_indent(result.stderr.rstrip()) + "\n")

    def goal_stopped(self, node: Any, reason: str) -> None:
        self.stream.write(f"{_paint('!', 'stopped', self.color)} {node.goal_id}  stopped\n")
        self.stream.write(f"  reason: {reason}\n")

    def plan_finished(self, summary: Any) -> None:
        self.stream.write("\n")
        self.stream.write(
            f"Summary: {summary.completed_count} completed, {summary.skipped_count} skipped, {summary.failed_count} failed\n"
        )


class InteractiveRunReporter(PlainRunReporter):
    """TTY-oriented progress reporter focused on the currently running goal."""

    spinner = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"

    def goal_started(self, node: Any, context: Any) -> None:
        self._running_index += 1
        self.stream.write(f"[{self._running_index}/{self._executable_total}] {node.goal_id}\n")
        self.stream.write(f"      id:  {node.identity}\n")
        self.stream.write(f"      out: {_display_path(context.artifact_dir, self.repo_root)}\n")
        self.stream.write(f"\r      {self.spinner[0]} running")
        self.stream.flush()

    def goal_completed(self, node: Any, result: Any, elapsed: float) -> None:
        self.stream.write(f" { _format_command(result.command)}\n")
        super().goal_completed(node, result, elapsed)

    def goal_failed(self, node: Any, result: Any, elapsed: float) -> None:
        self.stream.write(f" { _format_command(result.command)}\n")
        super().goal_failed(node, result, elapsed)


def _paint(text: str, status: str, enabled: bool) -> str:
    if not enabled:
        return text
    return f"{STATUS_COLORS.get(status, '')}{text}{RESET}"


def _display_path(path: Path, root: Path) -> str:
    try:
        return str(path.relative_to(root))
    except ValueError:
        return str(path)


def _format_command(command: tuple[str, ...]) -> str:
    return " ".join(command)


def _format_elapsed(elapsed: float) -> str:
    return f"{elapsed:.2f}s"


def _produced_summary(paths: tuple[Path, ...]) -> str:
    if not paths:
        return ""
    return ", ".join(path.name for path in paths)


def _indent(text: str) -> str:
    return "\n".join(f"  {line}" for line in text.splitlines())


__all__ = ["InteractiveRunReporter", "PlainRunReporter", "RunReporter"]
