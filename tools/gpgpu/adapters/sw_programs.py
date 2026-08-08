from __future__ import annotations

import os
import subprocess
from pathlib import Path

from tools.gpgpu.config import ResolvedConfig
from tools.gpgpu.run_result import RunResult


def run_native(config: ResolvedConfig, repo_root: Path) -> RunResult:
    program = str(config.get("program"))
    command = ("make", "-C", "sw/programs", f"PROG={program}", "x86")
    return _run_make_artifacts(
        goal_id="sw.program.native",
        command=command,
        repo_root=repo_root,
        produced=(repo_root / "sw" / "programs" / program / f"{program}_x86",),
        require_executable=True,
    )


def run_elf(config: ResolvedConfig, repo_root: Path) -> RunResult:
    program = str(config.get("program"))
    command = ("make", "-C", "sw/programs", f"PROG={program}", f"{program}/{program}.elf")
    return _run_make_artifacts(
        goal_id="sw.program.elf",
        command=command,
        repo_root=repo_root,
        produced=(repo_root / "sw" / "programs" / program / f"{program}.elf",),
        require_executable=False,
    )


def run_image(config: ResolvedConfig, repo_root: Path) -> RunResult:
    program = str(config.get("program"))
    command = ("make", "-C", "sw/programs", f"PROG={program}", f"{program}/{program}_instructions.mem")
    program_dir = repo_root / "sw" / "programs" / program
    return _run_make_artifacts(
        goal_id="sw.program.image",
        command=command,
        repo_root=repo_root,
        produced=(
            program_dir / f"{program}_instructions.mem",
            program_dir / f"{program}_dump_real.asm",
        ),
        require_executable=False,
    )


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
