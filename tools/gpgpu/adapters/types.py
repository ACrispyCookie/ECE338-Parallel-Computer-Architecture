from __future__ import annotations

from pathlib import Path
from typing import Callable

from tools.gpgpu.config import ResolvedConfig
from tools.gpgpu.executor import RunResult

Adapter = Callable[[ResolvedConfig, Path], RunResult]
