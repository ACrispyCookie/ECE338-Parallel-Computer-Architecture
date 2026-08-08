from __future__ import annotations

import os
import subprocess
from pathlib import Path

from tools.gpgpu.executor import ExecutionContext, RunResult


def run_native(context: ExecutionContext) -> RunResult:
    program = str(context.config.get("program"))
    command = _make_command(program, context.artifact_dir, "native")
    return _run_make_artifacts(
        goal_id=context.goal_id,
        command=command,
        repo_root=context.repo_root,
        produced=(context.artifact_dir / f"{program}_x86",),
        require_executable=True,
    )


def run_elf(context: ExecutionContext) -> RunResult:
    program = str(context.config.get("program"))
    command = _make_command(program, context.artifact_dir, "elf")
    return _run_make_artifacts(
        goal_id=context.goal_id,
        command=command,
        repo_root=context.repo_root,
        produced=(
            context.artifact_dir / f"{program}.elf",
            context.artifact_dir / f"{program}.map",
        ),
        require_executable=False,
    )


def run_image(context: ExecutionContext) -> RunResult:
    program = str(context.config.get("program"))
    command = _make_command(program, context.artifact_dir, "image")
    return _run_make_artifacts(
        goal_id=context.goal_id,
        command=command,
        repo_root=context.repo_root,
        produced=(
            context.artifact_dir / f"{program}_instructions.mem",
            context.artifact_dir / f"{program}_dump_real.asm",
            context.artifact_dir / f"{program}.elf",
            context.artifact_dir / f"{program}.map",
        ),
        require_executable=False,
    )


def _make_command(program: str, out_dir: Path, target: str) -> tuple[str, ...]:
    return ("make", "-C", "sw/programs", f"PROG={program}", f"OUT_DIR={out_dir}", target)


def _run_make_artifacts(
    *,
    goal_id: str,
    command: tuple[str, ...],
    repo_root: Path,
    produced: tuple[Path, ...],
    require_executable: bool,
) -> RunResult:
    completed = subprocess.run(
        command,
        cwd=repo_root,
        text=True,
        capture_output=True,
        check=False,
    )
    produced_tuple = tuple(
        path for path in produced
        if path.exists() and (not require_executable or os.access(path, os.X_OK))
    )
    return RunResult(
        goal_id=goal_id,
        command=command,
        returncode=completed.returncode,
        produced=produced_tuple,
        stdout=completed.stdout,
        stderr=completed.stderr,
    )
