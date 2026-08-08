from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class RunResult:
    goal_id: str
    command: tuple[str, ...]
    returncode: int
    produced: tuple[Path, ...]
    stdout: str = ""
    stderr: str = ""


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
