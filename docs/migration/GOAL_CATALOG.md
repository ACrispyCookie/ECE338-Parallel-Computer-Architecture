# Goal Catalog Draft

This document is the working catalog for the production `gpgpu` goal model. It is intentionally separate from `config/goals.yaml` until the names, boundaries, and parameter model are approved.

The purpose is not to mirror every script or helper function one-to-one. The purpose is to define a small, coherent set of operations that cover the repository's current workflows without preserving script-era duplication or ambiguous naming.

## Design principles

1. Goals are user/domain operations, not script names.
2. Goals have hierarchy and stable ownership: `sw.program.*`, `hw.rtl.*`, `hw.fpga.*`, `board.*`, `kernel.*`, `demo.*`, and `test.*`.
3. Artifacts, checks, actions, and services stay distinct.
4. Hardware state is never represented as a cacheable artifact.
5. Board configuration is named as board configuration, not as “programming” a program.
6. Kernel execution is transport/board-parameterized; board names should not be baked into kernel goal names.
7. Low-level UART commands are diagnostics or internal library operations, not normal user-facing goals.
8. Test fixture generation belongs to `test.*`, not `hw.rtl.*`, because it generates test inputs and expected outputs.
9. Program-specific FPGA adapter knobs are settings selected by the program manifest, not independent goals.
10. Compatibility scripts remain references/wrappers until parity and deletion approval, but their names should not drive the final goal model.

## Goal kinds

- `artifact`: produces declared files under `out/artifacts/<goal>/<identity>/` and may be cache-skipped after validation.
- `check`: runs verification and reports pass/fail. It may produce reports later, but it is not skipped through the artifact cache.
- `action`: changes external state such as board configuration, memory loading, or kernel execution.
- `service`: starts a long-running process with explicit lifecycle behavior.

## Top-level hierarchy

```text
sw.program.*        Software program compilation, conversion, native execution, and visualization.
hw.rtl.*            RTL-source artifacts such as simulation executables.
hw.fpga.*           FPGA/Vivado build artifacts such as projects, bitstreams, and XSA files.
board.*             Physical/logical board state and configuration actions.
kernel.*            GPGPU kernel load/run operations over the selected backend/transport.
demo.*              Interactive demo services.
test.*              RTL, program, hardware-in-loop, and fixture checks.
```

Avoid adding normal public goals under `uart.*` or `memory.*`. Those are implementation details of `board.*`, `kernel.*`, or `test.*`. Diagnostic commands can exist later as CLI subcommands or hidden/internal goals, but they should not define the main goal graph.

## Public goal catalog

These are the normal goals that should eventually appear in `gpgpu list`.

### `sw.program.native`

Kind: `artifact`

Build the selected program as a native host executable.

Covers current behavior:

- `make -C sw/programs PROG=<program> x86`
- `make -C sw/programs PROG=<program> native`
- native portion of `sw/programs/run.sh -p <program> all`

Primary outputs:

- `executable`: `<program>_x86`, type `native-executable`

Core params:

- `program`
- `program.optimization`

### `sw.program.elf`

Kind: `artifact`

Build the selected program as a RISC-V bare-metal ELF and linker map.

Covers current behavior:

- `make -C sw/programs PROG=<program> elf`
- RISC-V compile/link part of `make ... riscv`
- RISC-V compile/link part of `sw/programs/run.sh --fpga`

Primary outputs:

- `elf`: `<program>.elf`, type `riscv-elf`
- `map`: `<program>.map`, type `linker-map`

Core params:

- `program`
- `architecture`
- `program.optimization`
- `program.march`
- `program.mabi`
- selected toolchain setting when it becomes real config

### `sw.program.image`

Kind: `artifact`

Convert the selected RISC-V program into the instruction-memory image consumed by the GPGPU.

Covers current behavior:

- `make -C sw/programs PROG=<program> image`
- `make -C sw/programs PROG=<program> <program>/<program>_instructions.mem`
- image-build portion of `sw/programs/run.sh --fpga`
- image-build portion of `demo/run.sh` in FPGA mode

Primary outputs:

- `imem`: `<program>_instructions.mem`, type `instruction-memory`
- `objdump`: `<program>_dump_real.asm`, type `objdump`

Dependency:

- `elf` -> `sw.program.elf`

Note: the current Makefile also emits a clean assembly listing, `<program>_program.asm`. Do not add a separate public goal for that unless it is consumed by a real workflow or user-facing report.

### `sw.program.run`

Kind: `artifact`

Run the selected program through the selected backend and capture the normalized program output as a typed artifact.

This keeps the familiar `run` name, but the production goal boundary is not “do arbitrary side effects.” The goal owns the result of a run. For native execution this is the captured stdout/file output such as `data.csv`. For FPGA execution this is the program-adapter output captured from the board run loop.

Backends:

- `native`: run `sw.program.native` and capture native output.
- `fpga-uart`: execute through the selected board transport and capture adapter output from `kernel.run`.

Covers current behavior:

- `sw/programs/run.sh -p <program> --x86`
- output-producing part of `sw/programs/run.sh -p <program> --fpga --port ...`
- output-producing part of `sw/programs/fpga_run.py --program <program> ...`

Primary outputs:

- `result`: normalized program result, type selected by the program manifest, for example `program-output-csv`.

Dependencies:

- backend `native`: `sw.program.native`
- backend `fpga-uart`: `kernel.run`

Core params:

- `program`
- `backend`
- backend-specific runtime settings from the selected program manifest

### `sw.program.visualize`

Kind: `artifact`

Render the selected program's captured run result into visualization artifact(s).

This keeps the familiar `visualize` name while making the goal cacheable and dependency-driven. The operation is the rendering/build of visualization outputs, not opening or showing them interactively.

Covers current behavior:

- file-producing behavior of `sw/programs/<program>/visualize.py`
- visualization portion of `sw/programs/run.sh --visualize`
- visualization/finalization hooks of `sw/programs/<program>/fpga.py` when they produce files

Primary outputs:

- `visualization`: rendered program visualization artifact, with type selected by the program manifest, for example `program-plot`, `program-image`, or `program-animation`.

Dependency:

- `result` -> `sw.program.run`

Core params:

- `program`
- `backend`
- visualization input/result selection
- visualization/render settings from the program manifest

### `sw.program.show`

Kind: `action` or `service`

Show or open the rendered visualization produced by `sw.program.visualize`.

This is the intentionally side-effecting display boundary: open a GUI/browser, serve an interactive viewer, or otherwise present an already-rendered artifact to the user. It is not an artifact build goal.

Covers current behavior:

- interactive/open-display behavior of program visualization scripts, where present
- future compatibility behavior for `sw/programs/run.sh --visualize` when the script opens rendered output directly

Dependency:

- `visualization` -> `sw.program.visualize`

Core params:

- `program`
- `backend`
- display mode / viewer selection

### `hw.rtl.sim_executable`

Kind: `artifact`

Build the Icarus Verilog simulation executable for the selected RTL testbench.

Covers current behavior:

- `make -C test compile TB=<testbench>`
- direct `iverilog` invocation in `test/run_tests.sh --range ...`

Primary outputs:

- `sim_executable`: `main`, type `iverilog-sim-executable`

Core params:

- `architecture`
- `rtl.sp_per_sm`
- `rtl.imem_words`
- `rtl.dmem_words`
- `test.testbench`
- RTL defines/includes once declared in schema

### `hw.fpga.project`

Kind: `artifact`

Create or refresh the Vivado project/build directory for the selected architecture and board type.

Covers current repository intent:

- no reproducible script currently exists, but RTL and `constraints.xdc` are present and the migration mission requires this boundary.

Primary outputs:

- `project`: Vivado project/build directory or project manifest, type `vivado-project`

Core params:

- `architecture`
- `board_type`
- `fpga.part`
- RTL/memory architecture settings

### `hw.fpga.bitstream`

Kind: `artifact`

Build the programmable-logic bitstream for the selected architecture and board type.

This replaces current implemented/mock `hw.board.bitstream` naming. The bitstream is an FPGA build artifact, not board state.

Covers repository intent:

- Vivado synthesis/implementation/bitstream generation once scripted.

Primary outputs:

- `bitstream`: `.bit`, type `fpga-bitstream`

Dependencies:

- `project` -> `hw.fpga.project`

Core params:

- `architecture`
- `board_type`
- `fpga.part`
- `fpga.synth.strategy`
- RTL/memory architecture settings

### `hw.fpga.xsa`

Kind: `artifact`

Export the hardware handoff for bare-metal firmware/Vitis integration.

Covers repository intent:

- XSA export is currently missing but required for a reproducible Zynq workflow.

Dependencies:

- likely `hw.fpga.bitstream` or `hw.fpga.project`, depending on final Vivado flow.

Primary outputs:

- `xsa`: `.xsa`, type `xilinx-xsa`

### `board.configure`

Kind: `action`

Configure the selected physical/logical board's FPGA fabric with a compatible bitstream.

This replaces current implemented/mock `hw.board.program`. The word `program` is reserved for software programs; this operation configures board state.

Covers current repository intent:

- board programming/configuration workflow once reproducible.

Dependencies:

- `bitstream` -> `hw.fpga.bitstream`

Core params:

- `board`
- `board.configure_policy` = `if-needed | always | never`
- machine-local JTAG/programming settings

### `board.monitor`

Kind: `action` or `check`

Ensure or verify that the board-side UART monitor firmware is available and responsive.

Covers current assumptions:

- `sw/host/baremetal/main.c`
- `sw/host/baremetal/gpgpu_host.c/.h`
- all UART scripts assume this firmware/protocol is already running.

This is not a replacement for every low-level UART helper command. It is the board readiness boundary required before automated kernel/test/demo workflows.

Core params:

- `board`
- `uart.baud`
- machine-local port setting
- monitor protocol/version setting when available

### `kernel.load`

Kind: `action`

Load the selected program image and required initial data into the selected backend/board.

Covers current behavior:

- IMEM load in `sw/programs/fpga_run.py`
- initial DMEM writes from `sw/programs/<program>/fpga.py`
- IMEM load in `demo/interactive.py` and `demo/interactive_3d.py`
- setup portion of `test/host_uart_tester.py`

Dependencies:

- `program_image` -> `sw.program.image`
- `configured_board` -> `board.configure` when backend requires FPGA fabric configuration
- `monitor` -> `board.monitor` when backend is `fpga-uart`

Core params:

- `program`
- `backend`
- `board`
- `kernel.load_policy`
- `kernel.skip_load_imem`
- `kernel.imem_offset`
- `kernel.args_offset`
- `uart.baud`
- program-specific runtime settings selected through the program manifest

### `kernel.run`

Kind: `action`

Run the selected loaded kernel for one or more launches, including argument-window updates and output-window collection.

Covers current behavior:

- kernel-call loop in `sw/programs/fpga_run.py`
- per-step FPGA backend in `demo/interactive.py`
- per-step FPGA backend in `demo/interactive_3d.py`
- run/dump/done loop in `test/host_uart_tester.py`

Dependencies:

- `loaded_kernel` -> `kernel.load`

Core params:

- `program`
- `backend`
- `board`
- `kernel.kernel_calls`
- `kernel.args_offset`
- program-specific runtime settings selected through the program manifest

### `demo.run`

Kind: `service`

Run the selected interactive browser demo.

Covers current behavior:

- `demo/run.sh --fake ...`
- `demo/run.sh --program nbody-3d --fake --dataset rings ...`
- `demo/run.sh --port ...`
- `demo/interactive.py`
- `demo/interactive_3d.py`

Dependencies:

- backend `fake`: `sw.program.native`
- backend `fpga-uart`: `kernel.load`; repeated stepping occurs inside the service using the selected backend

Core params:

- `demo`
- `program`
- `backend`
- `demo.fps`
- `demo.steps_per_frame`
- `demo.dataset`
- `demo.http_host`
- `demo.http_port`
- `demo.no_browser`
- `board`/UART settings when backend is `fpga-uart`

### `test.fixtures`

Kind: `artifact`

Generate RTL test fixture files from assembly tests.

This replaces current implemented/mock `hw.rtl.assemble`. These are test fixtures, not RTL artifacts.

Covers current behavior:

- `make -C test gen`
- `test/run_tests.sh --gen-only`
- `python3 test/assembler.py`
- `python3 test/expected_generator.py`
- range-specific assembly/expected generation in `test/run_tests.sh --range ...`

Primary outputs:

- `program_mem`: `program.mem`, type `test-program-memory`
- `data_mem`: `data.mem`, type `expected-data-memory`
- `trace`: `trace.csv`, type `expected-trace`
- `regfiles`: `regfile_c*.mem`, type `expected-regfile-set`

Core params:

- `architecture`
- `test.range`
- `rtl.sp_per_sm`
- `rtl.imem_words`
- `rtl.dmem_words`

### `test.rtl`

Kind: `check`

Run the RTL simulation test suite for the selected testbench/range.

Covers current behavior:

- `test/run_tests.sh --standard --tb e2e`
- `test/run_tests.sh --standard --tb smx --range N-M`
- `make -C test testsuite`
- `make -C test simulate`

Dependencies:

- `fixtures` -> `test.fixtures`
- `sim_executable` -> `hw.rtl.sim_executable`

Core params:

- `architecture`
- `test.testbench`
- `test.range`
- RTL/memory architecture settings

### `test.rtl.random`

Kind: `check`

Run randomized RTL fuzzing after or alongside the standard RTL suite.

Covers current behavior:

- `test/run_tests.sh --rand --iters N`
- `python3 test/random_tester.py --iterations N`

Dependencies:

- likely `hw.rtl.sim_executable`
- possibly `test.rtl` when preserving script behavior that standard tests pass before fuzzer starts

Core params:

- `test.random_iterations`
- `test.testbench`
- RTL/memory architecture settings

### `test.board`

Kind: `check`

Run generated RTL/program tests on the board through the UART monitor and compare board DMEM against expected data.

Covers current behavior:

- `test/run_tests.sh --host --port ...`
- `make -C test host UART_PORT=... UART_BAUD=...`
- `python3 test/host_uart_tester.py --port ...`

Dependencies:

- `fixtures` -> `test.fixtures`
- `monitor` -> `board.monitor`

Core params:

- `board`
- `uart.baud`
- machine-local port setting
- `test.start_at`
- `test.dmem_words`
- `test.dmem_offset`
- `test.check_words`

### `test.program`

Kind: `check`

Verify selected software program behavior against the selected backend/output expectation.

Covers current desired migration boundary:

- program build validation
- native-vs-generated-artifact comparison
- later native-vs-FPGA output comparison

Dependencies:

- backend `native`: `sw.program.run`
- backend `fpga-uart`: `sw.program.run`

Core params:

- `program`
- `backend`
- `architecture`
- `program.optimization`
- program-specific runtime settings

## Internal concepts that should not become normal goals

These are real concepts in the implementation, but they should not appear as normal public goals unless a later workflow proves they need direct user access.

### Program conversion internals

- RISC-V objdump generation.
- Clean assembly listing generation.

Keep inside `sw.program.image` unless another public workflow consumes them independently.

### UART primitive commands

Do not add normal public goals for every primitive from `test/host_uart_helper.py`:

- UART help/status/raw.
- IMEM single read/write.
- DMEM single read/write.
- IMEM/DMEM load/dump/clear primitives.
- `run`/`done` as standalone normal goals.

These should be library operations used by `board.monitor`, `kernel.load`, `kernel.run`, and `test.board`, with optional future diagnostic CLI surfaces.

### Program-adapter callback phases

Do not add separate goals for:

- adapter import;
- `initial_dmem()`;
- `kernel_arguments()`;
- `output_window()`;
- `process_output()`;
- `finalize()`.

Those are program-runner interfaces inside `kernel.load`, `kernel.run`, `sw.program.run`, and `sw.program.visualize`.

### Browser/UI actions

Do not add separate goals for opening a browser, step buttons, FPS buttons, or HTTP request handlers. They are lifecycle/runtime behavior of `demo.run`.

## Current implemented goal names that should be renamed

The current `config/goals.yaml` still contains several names from earlier milestones that should not be finalized as-is.

| Current name | Proposed final name | Reason |
| --- | --- | --- |
| `hw.board.project` | `hw.fpga.project` | Project is an FPGA/Vivado build artifact selected by board type, not physical board state. |
| `hw.board.bitstream` | `hw.fpga.bitstream` | Bitstream is an FPGA artifact. Board state begins at `board.configure`. |
| `hw.board.program` | `board.configure` | Avoids ambiguity with software programs; operation configures FPGA fabric. |
| `hw.board.kernel.load` | `kernel.load` | Kernel loading is parameterized by board/backend; board should not be baked into goal name. |
| `hw.board.kernel.run` | `kernel.run` | Same reason; execution is a kernel operation over selected backend. |
| `hw.rtl.assemble` | `test.fixtures` | The output is test fixture data, not RTL assembly. |

`hw.rtl.sim_executable` can stay because it is an RTL simulation artifact, though its inputs include testbench selection.

## Goals intentionally not added

These names should not be introduced unless the architecture changes:

- `sw.program.objdump` as a normal public goal.
- `sw.program.asm_listing` as a normal public goal.
- `memory.imem.load` as a normal public goal.
- `memory.dmem.dump` as a normal public goal.
- `uart.status` as a normal public goal.
- `kernel.run_once` as a normal public goal.
- `kernel.done` as a normal public goal.
- `demo.backend.fake` as a goal.
- `demo.backend.fpga` as a goal.
- Per-program goals such as `program.nbody.run`, `demo.nbody3d`, or `kernel.mandelbrot.run`.

The selected program/demo/backend should be configuration, not a proliferation of duplicated goals.

## Script coverage map

| Current entry point | Final goal coverage |
| --- | --- |
| `run.sh` | compatibility wrapper around `gpgpu ...`; no unique goal. |
| `sw/programs/run.sh -p <program> x86` | `sw.program.native`, then `sw.program.run --set backend=native`. |
| `sw/programs/run.sh -p <program> riscv` | `sw.program.elf` and `sw.program.image`. |
| `sw/programs/run.sh -p <program> all` | `sw.program.native` plus `sw.program.image`; maybe an alias, not a new core goal. |
| `sw/programs/run.sh -p <program> --x86 --visualize` | `sw.program.run --set backend=native`, then `sw.program.visualize`, optionally `sw.program.show`. |
| `sw/programs/run.sh -p <program> --fpga ...` | `sw.program.image`, `kernel.load`, `kernel.run`, `sw.program.run --set backend=fpga-uart`, optional `sw.program.visualize`/`sw.program.show`. |
| `sw/programs/Makefile native/x86` | `sw.program.native`. |
| `sw/programs/Makefile elf` | `sw.program.elf`. |
| `sw/programs/Makefile image` | `sw.program.image`. |
| `sw/programs/fpga_run.py` | `kernel.load` and `kernel.run`, with program adapter settings from manifests. |
| `sw/programs/<program>/fpga.py` | Program manifest/runtime adapter consumed by `kernel.load`, `kernel.run`, and `sw.program.run`. |
| `sw/programs/<program>/visualize.py` | `sw.program.visualize` for rendered artifacts; `sw.program.show` for display/open behavior. |
| `demo/run.sh --fake` | `demo.run --set backend=fake`. |
| `demo/run.sh --port ...` | `demo.run --set backend=fpga-uart`, depending on `kernel.load`. |
| `demo/interactive.py` | implementation of `demo.run` for `demo=nbody`. |
| `demo/interactive_3d.py` | implementation of `demo.run` for `demo=nbody-3d`. |
| `test/run_tests.sh --gen-only` | `test.fixtures`. |
| `test/run_tests.sh --standard` | `test.rtl`. |
| `test/run_tests.sh --rand` | `test.rtl.random`. |
| `test/run_tests.sh --host` | `test.board`. |
| `test/Makefile compile` | `hw.rtl.sim_executable`. |
| `test/Makefile testsuite/simulate` | `test.rtl`. |
| `test/Makefile gen` | `test.fixtures`. |
| `test/Makefile host` | `test.board`. |
| `test/host_uart_helper.py` | future diagnostics, not normal production goals. |
| `sw/host/baremetal/main.c` and `gpgpu_host.c/.h` | `board.monitor` readiness; later firmware build goal only after a reproducible build flow exists. |

## Program coverage

Known program directories:

- `nbody`: native build, RISC-V image, FPGA adapter, visualization.
- `nbody-3d`: native build, RISC-V image, FPGA adapter, demo, dataset selection.
- `mandelbrot`: native/RISC-V image, FPGA adapter, visualization.
- `differences`: native/RISC-V image, FPGA adapter, visualization.
- `simple`: native/RISC-V build only unless an adapter is added.
- `sobel`: native/RISC-V build only unless an adapter is added.
- `stacktest`: native/RISC-V build only unless an adapter is added.

Program-specific runtime settings belong in selected program manifests and are consumed by `sw.program.run`, `kernel.load`, `kernel.run`, and `demo.run` as appropriate.

## Recommended implementation order

1. Rename/restructure the existing planner goal names to the final hierarchy:
   - `hw.board.project` -> `hw.fpga.project`
   - `hw.board.bitstream` -> `hw.fpga.bitstream`
   - `hw.board.program` -> `board.configure`
   - `hw.board.kernel.load` -> `kernel.load`
   - `hw.board.kernel.run` -> `kernel.run`
   - `hw.rtl.assemble` -> `test.fixtures`
2. Update `test.rtl`, `demo.run`, and dependency notes to use the renamed goals.
3. Add tests that reject the old ambiguous names.
4. Add only the goal declarations needed by the next real adapter slice; avoid adding inert placeholders.
5. Implement the first real artifact/check/action slice after naming is stable, preferably `sw.program.run`, `sw.program.visualize`, `test.program`, or `test.fixtures` depending on which workflow is selected next.

## Open decisions

1. What exact output roles/types should each program manifest declare for `sw.program.run` and `sw.program.visualize`?
2. Should clean assembly listing `<program>_program.asm` remain an internal side output of `sw.program.image`, or become a declared output role?
3. Should `board.monitor` be a `check` goal or an `action` goal? It mostly verifies state, but it may reset/flush UART buffers depending on implementation.
4. Should `sw.program.show` be an `action` or `service` for each current visualizer?
5. Should `hw.fpga.xsa` wait until a real Vivado flow exists, or be declared early as a planned artifact boundary?
