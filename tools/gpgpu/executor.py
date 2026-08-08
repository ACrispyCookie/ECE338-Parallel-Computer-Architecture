from __future__ import annotations

import os
import subprocess
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

    Milestone 7 intentionally supports only the native program build adapter.
    Other goals stay planner-only until they have explicit characterization and
    parity evidence.
    """

    def __init__(self, config: ResolvedConfig, *, repo_root: str | Path | None = None):
        self.config = config
        self.repo_root = Path(repo_root) if repo_root is not None else Path(__file__).resolve().parents[2]

    def run(self, goal_id: str) -> RunResult:
        if goal_id != "sw.program.native":
            raise ExecuteError(f"no executor adapter registered for {goal_id}")
        return self._run_sw_program_native()

    def _run_sw_program_native(self) -> RunResult:
        program = str(self.config.get("program"))
        command = ("make", "-C", "programs", f"PROG={program}", "x86")
        completed = subprocess.run(
            command,
            cwd=self.repo_root,
            text=True,
            capture_output=True,
            check=False,
        )
        produced = self.repo_root / "programs" / program / f"{program}_x86"
        produced_tuple: tuple[Path, ...] = (produced,) if produced.exists() and os.access(produced, os.X_OK) else ()
        return RunResult(
            goal_id="sw.program.native",
            command=command,
            returncode=completed.returncode,
            produced=produced_tuple,
            stdout=completed.stdout,
            stderr=completed.stderr,
        )


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
