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

## Milestone 11 executor adapter registry

Milestone 11 is a structure-only cleanup of the new control-plane executor:

```text
tools/gpgpu/executor.py
tools/gpgpu/adapters/
  __init__.py
  sw_programs.py
```

Compatibility behavior:

- `sw.program.native`, `sw.program.elf`, and `sw.program.image` still call the same Makefile commands as before;
- output paths remain in legacy `sw/programs/<program>/` locations;
- no `out/` artifact migration occurs;
- no Makefile targets or flags change;
- unsupported goals continue to fail with `no executor adapter registered for <goal>`.

Backend policy: keep Makefile as the compatibility backend for now. A later milestone may either make Makefile a thinner typed backend that receives variables from `gpgpu`, or switch specific workflows to Python-native command execution after parity tests exist.

Clean policy: do not add broad or implicit cleaning to `gpgpu run`. A future `gpgpu clean <goal>` should remove only artifacts owned by a normalized goal instance, and `--force` should rebuild scoped artifacts rather than calling broad `make clean`.

## Milestone 12 software artifact `out/` routing

Milestone 12 changes the output location for the three current software artifact adapters while preserving the Makefile backend:

```text
out/artifacts/<goal-id>/<program>/<artifact-identity>/
```

Representative outputs:

```text
out/artifacts/sw.program.native/nbody/<identity>/nbody_x86
out/artifacts/sw.program.elf/nbody/<identity>/nbody.elf
out/artifacts/sw.program.elf/nbody/<identity>/nbody.map
out/artifacts/sw.program.image/nbody/<identity>/nbody_instructions.mem
out/artifacts/sw.program.image/nbody/<identity>/nbody_dump_real.asm
```

Compatibility behavior:

- `sw.program.native`, `sw.program.elf`, and `sw.program.image` still use `make -C sw/programs`;
- artifact layout is owned by control-plane helpers, not by domain adapters;
- Makefile accepts `OUT_DIR=<artifact-dir>` and exposes named `native`, `elf`, and `image` targets;
- source inputs remain under `sw/programs/<program>/`;
- generated software artifacts are no longer written to `sw/programs/<program>/` by `gpgpu run`;
- no broad `make clean` is introduced.

Milestone 13 dependency-aware `gpgpu run` resolves that limitation for registered adapters:

- `gpgpu run` now executes registered goal adapters in planner topological order;
- internal planner-only artifacts such as `sw.program.compile_riscv` are shown as skipped when they have no adapter;
- public/check/action/service goals without adapters fail during preflight before side effects;
- failures stop dependent goals and show the failed goal stdout/stderr;
- `sw.program.image` consumes the `sw.program.elf` output via `ELF_IN=<elf artifact>` instead of rebuilding ELF in the image artifact directory.

## Milestone 14 Docker-like run progress reporter

Milestone 14 changes the presentation of `gpgpu run` without changing graph semantics or adapter behavior.

```bash
tools/gpgpu/gpgpu run sw.program.image --set program=nbody
```

Compatibility behavior:

- dependency order, stop-on-failure behavior, and adapter commands are unchanged from Milestone 13;
- compact progress output is now the default for non-TTY runs and captured test output;
- `--progress plain` forces deterministic compact output;
- `--progress tty` forces the current-goal-focused interactive renderer with a single mutable goal area;
- the interactive renderer clears and replaces the spinner/status line on completion or failure, rather than leaving a stale loading line followed by a separate completion line;
- interactive color mode styles the goal header, status, and secondary details for readability;
- completed goals collapse to one line with status, elapsed time, and produced artifact basenames;
- skipped internal planner-only goals are retained as compact records with a reason;
- failed goals expand the command, stdout, stderr, and stop reasons for dependents;
- successful compact output intentionally does not print the full Make command unless using the older `format_run_summary()` helper in tests/debugging.

No live subprocess stdout streaming is implemented yet. Adapters still capture stdout/stderr and expose it after command completion, with stderr/stdout printed on failure.

## Milestone 15 declarative dependency metadata

Milestone 15 changes where dependency metadata lives without changing adapter commands or legacy workflow behavior.

Compatibility behavior:

- dependencies are declared on goal definitions in `tools/gpgpu/goals.py`, not as a goal-specific `if` chain in `Planner._dependency_goal_ids()`;
- conditional dependencies are equality-only declarations, currently used for `demo.run` backend selection;
- included/omitted dependency notes remain visible in verbose plans;
- `sw.program.compile_riscv` is removed as an internal planner placeholder because it does not currently own a distinct artifact boundary;
- `sw.program.elf` is the current RISC-V compile/link artifact boundary;
- `gpgpu run sw.program.elf` no longer displays a skipped `sw.program.compile_riscv` node;
- `gpgpu run sw.program.image` still runs `sw.program.elf` before `sw.program.image` and passes `ELF_IN=<elf artifact>`;
- artifact specs are intentionally not implemented in this milestone.

The removal may change software artifact identity hashes because dependency identities participate in artifact identity. This is acceptable before persistent cache semantics exist and removes a misleading placeholder boundary.

## Milestone 16 generic artifact layout and clean command

Milestone 16 changes artifact directory layout and adds a conservative clean command.

Compatibility behavior:

- generated artifact directories now use `out/artifacts/<goal>/<identity>/`, not `out/artifacts/<goal>/<program>/<identity>/`;
- `program` and other human-readable settings are recorded in `artifact.toml` instead of being universal path components;
- `artifact.toml` is written after successful artifact goal execution and records goal, kind, identity, params, produced files, and dependency identities;
- `gpgpu clean` deletes only normalized artifact directories under `out/artifacts/<goal>/<identity>/`;
- `gpgpu clean` never deletes source-tree files and never calls `make clean`;
- root-only clean supports artifact goals only;
- `--deps` cleans artifact nodes in planner order and does not perform action/service/check lifecycle cleanup;
- missing artifact directories are reported but are not errors;
- broad paths, outside paths, and symlink artifact directories are refused.

This layout change is expected to move existing generated software outputs if a user has stale artifacts from prior feature-branch milestones. Those stale directories can be removed manually because they are ignored output under `out/artifacts`.

## Milestone 17 planning-only cache status

Milestone 17 adds cache presence reporting to `gpgpu plan` and `gpgpu explain` without changing execution behavior.

Compatibility behavior:

- artifact goals report `CACHE HIT` only when their exact normalized `out/artifacts/<goal>/<identity>/artifact.toml` exists and records matching goal and identity metadata;
- artifact goals report `CACHE MISS` for missing directories, missing metadata, invalid metadata, or goal/identity mismatches;
- action, service, and check goals do not show compact cache status and are not considered cache hits;
- verbose plan/explain output reports the status path and reason;
- `gpgpu run` still executes adapters even when a plan reports `CACHE HIT`;
- no source hashes, tool versions, artifact specs, artifact injection, or cache-skipping behavior is implemented yet.

This milestone is intentionally a reporting milestone. It gives users visibility into current artifact presence while preserving the existing compatibility-adapter execution path.

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
