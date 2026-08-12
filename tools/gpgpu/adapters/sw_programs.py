from __future__ import annotations

import os
import subprocess
from pathlib import Path

from tools.gpgpu.executor import ExecuteError, ExecutionContext, ProducedArtifact, RunResult


def run_native(context: ExecutionContext) -> RunResult:
    program = str(context.config.get("program"))
    command = _make_command(program, context.artifact_dir, "native")
    return _run_make_artifacts(
        goal_id=context.goal_id,
        command=command,
        repo_root=context.repo_root,
        produced=tuple(context.declared_outputs.values()),
        require_executable=True,
    )


def run_elf(context: ExecutionContext) -> RunResult:
    program = str(context.config.get("program"))
    abi_dir = _dependency_output(context, "sw.abi", "runtime_header", artifact_type="c-header").parent
    linker_script = _dependency_output(context, "sw.abi", "linker_script", artifact_type="linker-script")
    command = _make_command(
        program,
        context.artifact_dir,
        "elf",
        extra=(f"ABI_INCLUDE_DIR={abi_dir}", f"LINKER_SCRIPT={linker_script}"),
    )
    return _run_make_artifacts(
        goal_id=context.goal_id,
        command=command,
        repo_root=context.repo_root,
        produced=tuple(context.declared_outputs.values()),
        require_executable=False,
    )


def run_image(context: ExecutionContext) -> RunResult:
    program = str(context.config.get("program"))
    elf_path = _dependency_output(context, "sw.program.elf", "elf", artifact_type="riscv-elf")
    command = _make_command(program, context.artifact_dir, "image", extra=(f"ELF_IN={elf_path}",))
    return _run_make_artifacts(
        goal_id=context.goal_id,
        command=command,
        repo_root=context.repo_root,
        produced=tuple(context.declared_outputs.values()),
        require_executable=False,
    )


def _make_command(program: str, out_dir: Path, target: str, *, extra: tuple[str, ...] = ()) -> tuple[str, ...]:
    return ("make", "-C", "sw/programs", f"PROG={program}", f"OUT_DIR={out_dir}", *extra, target)


def _dependency_output(context: ExecutionContext, dependency_goal_id: str, output_role: str, *, artifact_type: str) -> Path:
    artifact = context.dependency_outputs.get(dependency_goal_id, {}).get(output_role)
    if artifact is None:
        raise ExecuteError(f"{context.goal_id} requires dependency {dependency_goal_id}.{output_role}")
    if artifact.artifact_type != artifact_type:
        raise ExecuteError(
            f"{context.goal_id} requires {dependency_goal_id}.{output_role} type {artifact_type}, got {artifact.artifact_type}"
        )
    return artifact.path


def _run_make_artifacts(
    *,
    goal_id: str,
    command: tuple[str, ...],
    repo_root: Path,
    produced: tuple[ProducedArtifact, ...],
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
        artifact for artifact in produced
        if artifact.path.exists() and (not require_executable or os.access(artifact.path, os.X_OK))
    )
    return RunResult(
        goal_id=goal_id,
        command=command,
        returncode=completed.returncode,
        produced=produced_tuple,
        stdout=completed.stdout,
        stderr=completed.stderr,
    )
