from __future__ import annotations

from pathlib import Path
from typing import Callable

from tools.gpgpu.config import ResolvedConfig
from tools.gpgpu.run_result import RunResult

Adapter = Callable[[ResolvedConfig, Path], RunResult]
