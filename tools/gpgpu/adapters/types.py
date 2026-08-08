from __future__ import annotations

from typing import Callable

from tools.gpgpu.executor import ExecutionContext, RunResult

Adapter = Callable[[ExecutionContext], RunResult]
