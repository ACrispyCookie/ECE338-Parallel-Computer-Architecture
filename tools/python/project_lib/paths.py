"""Repository path helpers for ECE338 automation scripts."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import subprocess


@dataclass(frozen=True)
class RepoPaths:
    """Common repository paths used by scripts.

    Attribute names intentionally mirror the Bash variable convention documented
    in `docs/plans/2026-07-28-phase-8a-shared-library.md`.
    """

    repo: Path
    config: Path
    config_file: Path
    build: Path
    hardware: Path
    rtl: Path
    vivado: Path
    software: Path
    host_software: Path
    programs: Path
    tests: Path
    rtl_tests: Path
    test_cases: Path
    test_tools: Path
    demo: Path


def find_repo_root(start: str | Path | None = None) -> Path:
    """Return the repository root for *start*.

    This first asks git, which works from both tracked and untracked scripts
    inside the worktree. If git is unavailable, it walks upward until it finds a
    directory containing both `.git` and `config/gpgpu.json`.
    """

    start_path = Path(start or Path.cwd()).resolve()
    search_dir = start_path if start_path.is_dir() else start_path.parent

    try:
        result = subprocess.run(
            ["git", "-C", str(search_dir), "rev-parse", "--show-toplevel"],
            check=True,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
        )
    except (FileNotFoundError, subprocess.CalledProcessError):
        pass
    else:
        return Path(result.stdout.strip()).resolve()

    for candidate in (search_dir, *search_dir.parents):
        if (candidate / ".git").exists() and (candidate / "config" / "gpgpu.json").exists():
            return candidate.resolve()

    raise RuntimeError(f"Could not find repository root from {start_path}")


def repo_paths(repo_root: str | Path | None = None) -> RepoPaths:
    """Return the standard repository path set."""

    repo = find_repo_root(repo_root) if repo_root is not None else find_repo_root()
    config = repo / "config"
    hardware = repo / "hardware"
    software = repo / "software"
    tests = repo / "tests"
    rtl_tests = tests / "hardware" / "rtl"

    return RepoPaths(
        repo=repo,
        config=config,
        config_file=config / "gpgpu.json",
        build=repo / "build",
        hardware=hardware,
        rtl=hardware / "rtl",
        vivado=hardware / "vivado",
        software=software,
        host_software=software / "host",
        programs=repo / "software" / "programs",
        tests=tests,
        rtl_tests=rtl_tests,
        test_cases=rtl_tests / "cases",
        test_tools=tests / "tools",
        demo=repo / "demo",
    )
