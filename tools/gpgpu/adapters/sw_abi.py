from __future__ import annotations

import json
import math
import re
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from tools.gpgpu.executor import ExecutionContext, RunResult


_TEMPLATE_PATTERN = re.compile(r"\$\{([A-Za-z0-9_.]+)\}")
_RUNTIME_HEADER_TEMPLATE = Path("sw/programs/gpgpu_runtime.h.in")
_LINKER_SCRIPT_TEMPLATE = Path("sw/programs/gpgpu.ld.in")


@dataclass(frozen=True)
class AbiModel:
    architecture: str
    word_bytes: int
    thread_count: int
    thread_id_register: str
    imem_origin: int
    imem_words: int
    dmem_origin: int
    dmem_words: int
    args_base_word: int
    args_words: int
    data_base_word: int
    stack_per_lane_bytes: int
    stack_top_word: int

    @property
    def imem_bytes(self) -> int:
        return self.imem_words * self.word_bytes

    @property
    def dmem_bytes(self) -> int:
        return self.dmem_words * self.word_bytes

    @property
    def args_base_byte(self) -> int:
        return self.args_base_word * self.word_bytes

    @property
    def args_end_word(self) -> int:
        return self.args_base_word + self.args_words

    @property
    def args_end_byte(self) -> int:
        return self.args_end_word * self.word_bytes

    @property
    def data_base_byte(self) -> int:
        return self.data_base_word * self.word_bytes

    @property
    def stack_top_byte(self) -> int:
        return self.stack_top_word * self.word_bytes

    @property
    def stack_per_lane_words(self) -> int:
        return self.stack_per_lane_bytes // self.word_bytes

    @property
    def stack_bottom_byte(self) -> int:
        return self.stack_top_byte - self.thread_count * self.stack_per_lane_bytes

    @property
    def stack_bottom_word(self) -> int:
        return self.stack_bottom_byte // self.word_bytes

    @property
    def data_limit_byte(self) -> int:
        return self.stack_bottom_byte

    @property
    def data_limit_word(self) -> int:
        return self.stack_bottom_word

    @property
    def stack_stride_shift(self) -> int:
        return int(math.log2(self.stack_per_lane_bytes))


def run_sw_abi(context: ExecutionContext) -> RunResult:
    model = _model_from_context(context)
    _validate(model)
    variables = _template_variables(model, context.config.values)
    runtime_header = _render_template(context.repo_root / _RUNTIME_HEADER_TEMPLATE, variables)
    linker_script = _render_template(context.repo_root / _LINKER_SCRIPT_TEMPLATE, variables)

    outputs = context.declared_outputs
    outputs["runtime_header"].path.write_text(runtime_header, encoding="utf-8")
    outputs["linker_script"].path.write_text(linker_script, encoding="utf-8")
    outputs["metadata"].path.write_text(json.dumps(_metadata(model), indent=2, sort_keys=True) + "\n", encoding="utf-8")

    return RunResult(
        goal_id=context.goal_id,
        command=("generate-sw-abi", model.architecture),
        returncode=0,
        produced=tuple(outputs.values()),
    )


def _model_from_context(context: ExecutionContext) -> AbiModel:
    get = context.config.get
    return AbiModel(
        architecture=str(get("architecture")),
        word_bytes=int(get("architecture.memory.word_bytes")),
        thread_count=int(get("architecture.rtl.thread.count")),
        thread_id_register=str(get("architecture.rtl.thread.id_register")),
        imem_origin=int(get("architecture.memory.imem.origin")),
        imem_words=int(get("architecture.memory.imem.words")),
        dmem_origin=int(get("architecture.memory.dmem.origin")),
        dmem_words=int(get("architecture.memory.dmem.words")),
        args_base_word=int(get("architecture.abi.args.base_word")),
        args_words=int(get("architecture.abi.args.words")),
        data_base_word=int(get("architecture.abi.data.base_word")),
        stack_per_lane_bytes=int(get("architecture.abi.stack.per_lane_bytes")),
        stack_top_word=int(get("architecture.abi.stack.top_word")),
    )


def _validate(model: AbiModel) -> None:
    if model.word_bytes <= 0:
        raise ValueError("architecture.memory.word_bytes must be positive")
    if model.stack_per_lane_bytes <= 0 or model.stack_per_lane_bytes % model.word_bytes != 0:
        raise ValueError("architecture.abi.stack.per_lane_bytes must be a positive multiple of word_bytes")
    if model.stack_per_lane_bytes & (model.stack_per_lane_bytes - 1):
        raise ValueError("architecture.abi.stack.per_lane_bytes must be a power of two for generated shift-based startup")
    if model.thread_count <= 0:
        raise ValueError("architecture.rtl.thread.count must be positive")
    if model.args_words <= 0:
        raise ValueError("architecture.abi.args.words must be positive")
    if model.args_end_byte > model.data_base_byte:
        raise ValueError("architecture ABI args window overlaps compiler data region")
    if model.data_base_byte >= model.data_limit_byte:
        raise ValueError("architecture ABI data base must be below data limit")
    if model.stack_top_byte > model.dmem_origin + model.dmem_bytes:
        raise ValueError("architecture ABI stack top exceeds DMEM")
    if model.stack_bottom_byte < model.dmem_origin:
        raise ValueError("architecture ABI stack bottom is below DMEM origin")


def _hex(value: int) -> str:
    return f"0x{value:08x}"


def _length(value: int) -> str:
    return f"{value // 1024}K" if value % 1024 == 0 else str(value)


def _template_variables(model: AbiModel, resolved_values: Mapping[str, object] | None = None) -> dict[str, str]:
    variables = {key: str(value) for key, value in (resolved_values or {}).items()}
    variables.update({
        "architecture": model.architecture,
        "architecture.rtl.thread.count": str(model.thread_count),
        "architecture.rtl.thread.id_register": model.thread_id_register,
        "architecture.memory.word_bytes": str(model.word_bytes),
        "architecture.memory.imem.origin": str(model.imem_origin),
        "architecture.memory.imem.origin.hex": _hex(model.imem_origin),
        "architecture.memory.imem.words": str(model.imem_words),
        "architecture.memory.imem.bytes": str(model.imem_bytes),
        "architecture.memory.imem.bytes.length": _length(model.imem_bytes),
        "architecture.memory.dmem.origin": str(model.dmem_origin),
        "architecture.memory.dmem.origin.hex": _hex(model.dmem_origin),
        "architecture.memory.dmem.words": str(model.dmem_words),
        "architecture.memory.dmem.bytes": str(model.dmem_bytes),
        "architecture.memory.dmem.bytes.length": _length(model.dmem_bytes),
        "architecture.abi.args.base_word": str(model.args_base_word),
        "architecture.abi.args.base_byte": str(model.args_base_byte),
        "architecture.abi.args.base_byte.hex": _hex(model.args_base_byte),
        "architecture.abi.args.words": str(model.args_words),
        "architecture.abi.args.end_word": str(model.args_end_word),
        "architecture.abi.args.end_word.last": str(model.args_end_word - 1),
        "architecture.abi.args.end_byte": str(model.args_end_byte),
        "architecture.abi.args.end_byte.hex": _hex(model.args_end_byte),
        "architecture.abi.data.base_word": str(model.data_base_word),
        "architecture.abi.data.base_byte": str(model.data_base_byte),
        "architecture.abi.data.base_byte.hex": _hex(model.data_base_byte),
        "architecture.abi.data.limit_word": str(model.data_limit_word),
        "architecture.abi.data.limit_byte": str(model.data_limit_byte),
        "architecture.abi.data.limit_byte.hex": _hex(model.data_limit_byte),
        "architecture.abi.stack.per_lane_bytes": str(model.stack_per_lane_bytes),
        "architecture.abi.stack.per_lane_words": str(model.stack_per_lane_words),
        "architecture.abi.stack.per_lane_bytes.shift": str(model.stack_stride_shift),
        "architecture.abi.stack.top_word": str(model.stack_top_word),
        "architecture.abi.stack.top_word.last": str(model.stack_top_word - 1),
        "architecture.abi.stack.top_byte": str(model.stack_top_byte),
        "architecture.abi.stack.top_byte.hex": _hex(model.stack_top_byte),
        "architecture.abi.stack.bottom_word": str(model.stack_bottom_word),
        "architecture.abi.stack.bottom_byte": str(model.stack_bottom_byte),
        "architecture.abi.stack.bottom_byte.hex": _hex(model.stack_bottom_byte),
    })
    return variables


def _render_template(path: Path, variables: Mapping[str, str]) -> str:
    template = path.read_text(encoding="utf-8")

    def replace(match: re.Match[str]) -> str:
        name = match.group(1)
        try:
            return variables[name]
        except KeyError as exc:
            raise ValueError(f"unknown ABI template variable {name!r} in {path}") from exc

    rendered = _TEMPLATE_PATTERN.sub(replace, template)
    return rendered if rendered.endswith("\n") else rendered + "\n"


def _metadata(model: AbiModel) -> dict[str, object]:
    return {
        "architecture": model.architecture,
        "word_bytes": model.word_bytes,
        "thread": {
            "count": model.thread_count,
            "id_register": model.thread_id_register,
        },
        "memory": {
            "imem": {"origin": model.imem_origin, "words": model.imem_words, "bytes": model.imem_bytes},
            "dmem": {"origin": model.dmem_origin, "words": model.dmem_words, "bytes": model.dmem_bytes},
        },
        "abi": {
            "args": {
                "base_word": model.args_base_word,
                "base_byte": model.args_base_byte,
                "words": model.args_words,
                "end_word": model.args_end_word,
                "end_byte": model.args_end_byte,
            },
            "data": {
                "base_word": model.data_base_word,
                "base_byte": model.data_base_byte,
                "limit_word": model.data_limit_word,
                "limit_byte": model.data_limit_byte,
            },
            "stack": {
                "per_lane_bytes": model.stack_per_lane_bytes,
                "per_lane_words": model.stack_per_lane_words,
                "top_word": model.stack_top_word,
                "top_byte": model.stack_top_byte,
                "bottom_word": model.stack_bottom_word,
                "bottom_byte": model.stack_bottom_byte,
            },
        },
    }
