from __future__ import annotations

import json
import math
from dataclasses import dataclass

from tools.gpgpu.executor import ExecutionContext, RunResult


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

    outputs = context.declared_outputs
    outputs["runtime_header"].path.write_text(_render_runtime_header(model), encoding="utf-8")
    outputs["linker_script"].path.write_text(_render_linker_script(model), encoding="utf-8")
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


def _render_runtime_header(model: AbiModel) -> str:
    return f"""#ifndef GPGPU_RUNTIME_H
#define GPGPU_RUNTIME_H

#include <stdint.h>

/* Generated from config/architectures/{model.architecture}.yaml. */
/* Linker-provided DMEM symbols from gpgpu.ld.  These are byte addresses from
 * the RISC-V core's point of view; host UART DMEM word offset = address / 4. */
extern volatile int __gpu_args_base[];
extern char __gpu_stack_bottom[];
extern char __stack_top[];

#define GPGPU_ARGS   ((volatile int *)__gpu_args_base)

#define GPGPU_NUM_CORES    {model.thread_count}u
#define GPGPU_STACK_STRIDE {model.stack_per_lane_bytes}u

static inline __attribute__((always_inline)) unsigned int gpgpu_thread_id(void)
{{
    unsigned int tid;
    __asm__ volatile("mv %0, {model.thread_id_register}" : "=r"(tid));
    return tid;
}}

/* Use this for normal C kernels that may spill registers.
 *
 * Example:
 *
 *   static void kernel_main(void) {{
 *       unsigned int tid = gpgpu_thread_id();
 *       ... ordinary C that may use the stack ...
 *   }}
 *   GPGPU_START(kernel_main)
 *
 * The wrapper runs at PC 0, gives every lane a private {model.stack_per_lane_bytes}-byte stack slice at
 * the top of DMEM, calls kernel_main(), then returns to the host-controller
 * completion convention by looping forever.
 */
#define GPGPU_START(kernel_fn)                                                 \\
    __attribute__((naked, noreturn, section(".text.start"))) void _start(void) \\
    {{                                                                          \\
        __asm__ volatile(                                                      \\
            "mv x5, {model.thread_id_register}\\n"                                                     \\
            "slli x6, x5, {model.stack_stride_shift}\\n"                                                 \\
            "lui sp, %hi(__stack_top)\\n"                                       \\
            "addi sp, sp, %lo(__stack_top)\\n"                                  \\
            "sub sp, sp, x6\\n"                                                 \\
            "jal x1, " #kernel_fn "\\n"                                         \\
            "1:\\n"                                                             \\
            "jal x0, 1b\\n"                                                     \\
        );                                                                     \\
        __builtin_unreachable();                                               \\
    }}

#endif /* GPGPU_RUNTIME_H */
"""


def _render_linker_script(model: AbiModel) -> str:
    return f"""/*
 * Linker script for the GPGPU.
 *
 * Generated from config/architectures/{model.architecture}.yaml.
 * The RTL has separate instruction and data memories, but the RISC-V cores still
 * use ordinary byte addresses for loads/stores. Host-side DMEM commands use
 * word offsets, so byte address A corresponds to host DMEM word A / {model.word_bytes}.
 */
OUTPUT_ARCH(riscv)
ENTRY(_start)

MEMORY
{{
    /* {model.imem_words} instructions / {model.dmem_words} data words. */
    IMEM (rx)  : ORIGIN = {_hex(model.imem_origin)}, LENGTH = {_length(model.imem_bytes)}
    DMEM (rw)  : ORIGIN = {_hex(model.dmem_origin)}, LENGTH = {_length(model.dmem_bytes)}
}}

/* Host/kernel ABI windows, expressed as RISC-V byte addresses. */
__gpu_args_base      = {_hex(model.args_base_byte)}; /* host DMEM word {model.args_base_word} */
__gpu_args_end       = {_hex(model.args_end_byte)}; /* words {model.args_base_word}..{model.args_end_word - 1} */

/* Per-lane spill stacks: {model.thread_count} lanes * {model.stack_per_lane_bytes} bytes = DMEM[{model.stack_bottom_word}..{model.stack_top_word - 1}]. */
__gpu_num_cores      = {model.thread_count};
__gpu_stack_stride   = {model.stack_per_lane_bytes};
__gpu_stack_bottom   = {_hex(model.stack_bottom_byte)};
__stack_top          = {_hex(model.stack_top_byte)};

/*
 * Compiler-owned data.
 *
 * Starts at {_hex(model.data_base_byte)}, available for .rodata/.sdata/.data/.bss.
 */
__gpu_data_base      = {_hex(model.data_base_byte)};
__gpu_data_limit     = __gpu_stack_bottom;

SECTIONS
{{
    . = ORIGIN(IMEM);

    .text :
    {{
        /* Put reset/entry code at PC 0 when built with -ffunction-sections. */
        KEEP(*(.text.start .text.start.*))
        KEEP(*(.text._start))
        *(.text .text.*)
    }} > IMEM

    /*
     * Move the DMEM location counter to the compiler-owned data region.
     * This keeps compiler-generated data away from the host argument window.
     */
    . = __gpu_data_base;
    . = ALIGN(4);
    PROVIDE(__data_start = .);

    .rodata ALIGN(4) :
    {{
        *(.srodata .srodata.*)
        *(.rodata .rodata.*)
    }} > DMEM

    .sdata ALIGN(4) :
    {{
        *(.sdata .sdata.*)
    }} > DMEM

    .data ALIGN(4) :
    {{
        *(.data .data.*)
    }} > DMEM

    .bss ALIGN(4) (NOLOAD) :
    {{
        PROVIDE(__bss_start = .);
        *(.sbss .sbss.*)
        *(.bss .bss.*)
        *(COMMON)
        . = ALIGN(4);
        PROVIDE(__bss_end = .);
    }} > DMEM

    PROVIDE(__data_end = .);

    /DISCARD/ :
    {{
        *(.comment)
        *(.riscv.attributes)
        *(.note .note.*)
        *(__patchable_function_entries)
    }}
}}

ASSERT(SIZEOF(.text) <= LENGTH(IMEM), "GPGPU IMEM overflow: program has more than {model.imem_words} instructions/{model.imem_bytes} bytes");
ASSERT(__data_end <= __gpu_data_limit, "GPGPU DMEM overflow: compiler data/bss collides with per-lane stack window");
ASSERT(__gpu_args_end <= __gpu_data_base, "GPGPU ABI error: data region collides with argument window");
"""


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
