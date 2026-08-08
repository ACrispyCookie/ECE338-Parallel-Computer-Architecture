from __future__ import annotations

import os
import subprocess
from pathlib import Path

from tools.gpgpu.config import ResolvedConfig
from tools.gpgpu.executor import RunResult


def run_native(config: ResolvedConfig, repo_root: Path, artifact_identity: str) -> RunResult:
    program = str(config.get("program"))
    out_dir = _artifact_dir(repo_root, "sw.program.native", program, artifact_identity)
    command = _make_command(program, out_dir, "native")
    return _run_make_artifacts(
        goal_id="sw.program.native",
        command=command,
        repo_root=repo_root,
        produced=(out_dir / f"{program}_x86",),
        require_executable=True,
    )


def run_elf(config: ResolvedConfig, repo_root: Path, artifact_identity: str) -> RunResult:
    program = str(config.get("program"))
    out_dir = _artifact_dir(repo_root, "sw.program.elf", program, artifact_identity)
    command = _make_command(program, out_dir, "elf")
    return _run_make_artifacts(
        goal_id="sw.program.elf",
        command=command,
        repo_root=repo_root,
        produced=(
            out_dir / f"{program}.elf",
            out_dir / f"{program}.map",
        ),
        require_executable=False,
    )


def run_image(config: ResolvedConfig, repo_root: Path, artifact_identity: str) -> RunResult:
    program = str(config.get("program"))
    out_dir = _artifact_dir(repo_root, "sw.program.image", program, artifact_identity)
    command = _make_command(program, out_dir, "image")
    return _run_make_artifacts(
        goal_id="sw.program.image",
        command=command,
        repo_root=repo_root,
        produced=(
            out_dir / f"{program}_instructions.mem",
            out_dir / f"{program}_dump_real.asm",
            out_dir / f"{program}.elf",
            out_dir / f"{program}.map",
        ),
        require_executable=False,
    )


def _artifact_dir(repo_root: Path, goal_id: str, program: str, artifact_identity: str) -> Path:
    return repo_root / "out" / "artifacts" / goal_id / program / artifact_identity


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
