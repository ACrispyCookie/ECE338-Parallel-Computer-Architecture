from __future__ import annotations

from tools.gpgpu.adapters.sw_programs import run_elf, run_image, run_native
from tools.gpgpu.adapters.types import Adapter

ADAPTERS: dict[str, Adapter] = {
    "sw.program.native": run_native,
    "sw.program.elf": run_elf,
    "sw.program.image": run_image,
}

__all__ = ["ADAPTERS", "Adapter"]
