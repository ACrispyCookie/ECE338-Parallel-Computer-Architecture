# Migration Compatibility Record

Compatibility work must preserve existing behavior until parity is proven.

## Rule

Existing scripts are compatibility interfaces, behavioral references, regression oracles, and rollback mechanisms. They must stay in place until explicitly approved for retirement.

## Current compatibility status

No legacy command has been replaced yet.

The planner foundation is mock-only and does not execute current workflows. Therefore no legacy-versus-new parity claim is made for execution behavior.

## Milestone 6 safe characterization evidence

These tests intentionally exercise only help/import/static behavior. They do not open UART devices, call Vivado, build programs, run compilers, or execute hardware flows.

Automated characterization lives in:

```text
tests/legacy/test_legacy_cli_characterization.py
```

Covered entry points:

- `./run.sh --help` exits 0 and exposes build targets, `--fpga`, `--kernel-calls`, and adapter-forwarding guidance.
- `./sw/programs/run.sh --help` exits 0 and has the same key generic workflow surface as the root wrapper.
- `python3 sw/programs/fpga_run.py --help` exits 0 and exposes common UART loop options: `--program`, `--adapter-help`, `--kernel-calls`, `--args-offset`, and `--skip-load-imem`.
- `python3 test/host_uart_tester.py --help` exits 0 and exposes hardware test options: `--port`, `--dmem-words`, `--dmem-offset`, `--check-words`.
- `sw/host/baremetal/gpgpu_uart.py` imports without opening serial and remains the UART protocol reference for `DEPTH`, `PROMPT`, word normalization, memory-file reads, and RET trimming.

Duplicated/shared UART and kernel-run observations before adapter work:

- `sw/host/baremetal/gpgpu_uart.py` owns the protocol implementation: prompt handling, status parsing, ASCII/binary IMEM/DMEM load/dump, `run`, and `done`.
- `sw/programs/fpga_run.py` imports that protocol layer and owns the common program FPGA loop: load IMEM once, adapter-provided DMEM initialization, GPGPU_ARGS normalization/write-if-changed, kernel run, DMEM dump, adapter output processing, and `done` per call.
- `test/host_uart_tester.py` imports `DEPTH`, `GpgpuUartMonitor`, `read_mem_file`, and `trim_program_at_ret` from the protocol layer, but still owns a separate hardware-test loop for load/run/dump/compare/done.
- The current shared ABI/runtime constants include `DEPTH=2048`, UART baud default `115200`, `GPU_ARGS_BASE_WORDS=0x40/4`, `GPU_ARGS_WORDS=4`, and `kernel_calls` handling in the common runner and program adapters.
- Program adapters under `sw/programs/*/fpga.py` each receive `kernel_calls`; `mandelbrot` adds stronger semantic constraints by requiring kernel calls to match frame/height-derived counts.

Conclusion for future wrapper work: keep `sw/host/baremetal/gpgpu_uart.py` as the protocol reference and treat `sw/programs/fpga_run.py` plus `test/host_uart_tester.py` as behavior oracles. Do not extract or consolidate their loops until a wrapper/adaptor milestone compares command behavior against these characterization tests.

## Milestone 7 native compatibility adapter

The first executable goal adapter is intentionally narrow:

```bash
tools/gpgpu/gpgpu run sw.program.native --set program=nbody
```

It delegates to the legacy native Makefile target instead of reimplementing compiler flags:

```bash
make -C sw/programs PROG=nbody x86
```

Compatibility behavior:

- produced artifact stays at the legacy path `sw/programs/<program>/<program>_x86`;
- no `out/` artifact is created;
- the native program is not run, so no `sw/programs/<program>/data.csv` is produced;
- unsupported executable goals fail with `no executor adapter registered for <goal>`;
- legacy scripts and `sw/programs/Makefile` are not modified.

Known limitation: planner identity includes `program.optimization`, but the legacy native Makefile target currently uses `NATIVE_CFLAGS = -O2` and does not consume planner config. This adapter preserves legacy behavior exactly and records the mismatch for a later configuration/toolchain milestone rather than silently changing Makefile semantics.

## Milestone 9 RISC-V ELF compatibility adapter

The next executable artifact adapter is also narrow:

```bash
tools/gpgpu/gpgpu run sw.program.elf --set program=nbody
```

It delegates to the legacy RISC-V ELF Makefile target instead of reimplementing toolchain flags:

```bash
make -C sw/programs PROG=nbody nbody/nbody.elf
```

Compatibility behavior:

- produced artifact stays at the legacy path `sw/programs/<program>/<program>.elf`;
- secondary linker map output may be produced at `sw/programs/<program>/<program>.map` by existing Makefile behavior;
- no `out/` artifact is created;
- the ELF is not run;
- `sw.program.image` and other goals remain unsupported by the executor until their own adapter milestones;
- legacy scripts and `sw/programs/Makefile` are not modified.

Known limitation: planner identity includes `program.optimization`, `program.march`, and `program.mabi`, but the legacy RISC-V Makefile target currently hardcodes `-O2 -march=rv32im -mabi=ilp32`. This adapter preserves legacy behavior exactly and records the mismatch for a later configuration/toolchain milestone rather than silently changing Makefile semantics.

## Milestone 10 program image compatibility adapter

The instruction-memory image artifact adapter remains a direct legacy wrapper:

```bash
tools/gpgpu/gpgpu run sw.program.image --set program=nbody
```

It delegates to the legacy memory-image Makefile target instead of reimplementing objdump or awk extraction:

```bash
make -C sw/programs PROG=nbody nbody/nbody_instructions.mem
```

Compatibility behavior:

- primary produced artifact stays at the legacy path `sw/programs/<program>/<program>_instructions.mem`;
- supporting dump output may be produced at `sw/programs/<program>/<program>_dump_real.asm`;
- upstream ELF and map outputs may be produced at `sw/programs/<program>/<program>.elf` and `sw/programs/<program>/<program>.map`;
- no `out/` artifact is created;
- the memory-image format and extraction pipeline are unchanged;
- `test.program`, hardware goals, and demo goals remain unsupported by the executor until their own adapter milestones;
- legacy scripts and `sw/programs/Makefile` are not modified.

Known limitation: generated artifacts still live under `sw/programs/<program>/`. The tracked legacy `*_program.asm` snapshots must not be committed accidentally when compiler output changes. The `out/` root is reserved for a future generated-artifact migration milestone.

## Milestone 8 layout split

The branch intentionally breaks old root `src/`, `host/`, and `programs/` paths to establish explicit hardware/software domains before more adapters are added:

```text
hw/rtl/        former src/
sw/host/       former host/ minus stale linux host driver
sw/programs/   former programs/
out/           ignored generated-output root, with tracked out/.gitkeep
```

Compatibility behavior after the move:

- root `./run.sh` routes to `sw/programs/run.sh`;
- `tools/gpgpu/gpgpu run sw.program.native` delegates to `make -C sw/programs ...`;
- characterization tests use `sw/programs/fpga_run.py` and `sw/host/baremetal/gpgpu_uart.py`;
- old `host/linux/host.py` was deleted with explicit user approval because it was stale relative to the current UART monitor.

No compatibility wrappers were kept under root `programs/`, `host/`, or `src/`; this is acceptable on the feature branch before merge.

## Legacy workflows requiring characterization

### Program build and native run

Representative commands:

```bash
./run.sh --help
./run.sh -p nbody x86 --x86 --no-visualize
make -C sw/programs PROG=nbody riscv
make -C sw/programs PROG=nbody nbody/nbody_instructions.mem
```

Evidence to capture:

- exit code;
- generated file list;
- generated artifact hashes;
- stdout/stderr;
- dirty working tree after run.

### RTL tests

Representative commands:

```bash
cd test
./run_tests.sh --help
./run_tests.sh --gen-only --range 1
./run_tests.sh --standard --tb e2e --range 1
```

Evidence to capture:

- generated `program.mem`, `data.mem`, `trace.csv`, `regfile_c*.mem`;
- simulation log;
- pass/fail lines;
- waveform behavior if requested.

### UART helper and hardware tests

Representative commands without hardware:

```bash
python3 test/host_uart_helper.py --help
python3 test/host_uart_tester.py --help
```

Representative commands with hardware:

```bash
python3 test/host_uart_helper.py --port <port> status
cd test && ./run_tests.sh --host --port <port>
```

Evidence to capture:

- UART prompt protocol;
- monitor status output;
- binary load/dump behavior;
- pass/fail comparisons.

### Demo fake backend

Representative commands:

```bash
timeout 10 ./demo/run.sh --program nbody --fake --steps 1 --no-browser --http-port 8770
timeout 10 ./demo/run.sh --program nbody-3d --fake --dataset rings --steps 1 --no-browser --http-port 8771
```

Evidence to capture:

- service startup message;
- absence of FPGA/UART dependencies;
- generated native build outputs;
- expected timeout behavior for long-running service.

### Demo FPGA backend

Representative commands with hardware:

```bash
./demo/run.sh --program nbody --port <port> --steps 1 --no-browser
./demo/run.sh --program nbody-3d --port <port> --steps 1 --no-browser
```

Evidence to capture:

- RISC-V image build;
- IMEM load;
- DMEM argument writes;
- kernel run/dump/done sequence;
- output frame/result data.

### Shared UART/board execution helpers

Representative source files to compare before creating adapters:

```text
sw/host/baremetal/gpgpu_uart.py
sw/programs/fpga_run.py
test/host_uart_tester.py
demo/interactive.py
demo/interactive_3d.py
```

Compatibility evidence to capture:

- exact UART command sequence for load/run/dump/done;
- IMEM trim/load behavior;
- DMEM initialization/argument window behavior;
- binary versus ASCII bulk load/dump behavior;
- timeout/error handling;
- output parsing and comparison behavior.

Refactoring target: keep `sw/host/baremetal/gpgpu_uart.py` as the protocol reference initially, then extract shared board-kernel execution helpers only after `sw/programs/fpga_run.py` and `test/host_uart_tester.py` have characterization tests proving equivalent behavior.

## New planner goals and intended legacy adapters

Current planned mapping:

- `sw.program.native` -> adapter around native `sw/programs/Makefile` flow.
- `sw.program.elf` -> adapter around RISC-V compiler step.
- `sw.program.image` -> adapter around objdump and memory-image extraction.
- `test.rtl` -> adapter around `test/run_tests.sh` or lower-level test Makefile stages, with internal `hw.rtl.assemble` and `hw.rtl.sim_executable` support goals.
- `hw.board.bitstream` -> future Vivado flow, not present in baseline.
- `hw.board.program` -> future board-programming action.
- `hw.board.kernel.load` -> adapter around UART IMEM/DMEM loading.
- `hw.board.kernel.run` -> adapter around UART run/dump/done sequence.
- `demo.run` -> adapter around `demo/run.sh` or direct service runner after characterization.

## Deletion status

No deletion approved.

Potential future retirement candidates remain only candidates until evidence is collected:

- `sw/host/linux/host.py (deleted in Milestone 8)` after replacement and parity.
- tracked generated assembly snapshots only after confirming their role.
