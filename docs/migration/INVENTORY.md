# Migration Inventory

This inventory summarizes the baseline repository workflows inspected during Phase 0.

## Baseline

```text
commit: 7c5c12f20e7151773c2c8d72842d43f064244a9d
author: PANAGIVTHS <panagiotis.tsogka@gmail.com>
subject: Move tb to correct folder
```

## User-facing entry points

### Repository wrapper

- `run.sh`: thin wrapper around `sw/programs/run.sh`.

### Program workflows

- `sw/programs/run.sh`: program selection, build, native run, visualization, FPGA UART run.
- `sw/programs/Makefile`: `all`, `riscv`, `x86`, `clean`.
- `sw/programs/fpga_run.py`: generic program adapter runner over UART.
- `sw/programs/*/fpga.py`: program-specific FPGA ABI adapters.
- `sw/programs/*/visualize.py`: program-specific result visualization.

### Demo workflows

- `demo/run.sh`: interactive nbody/nbody-3d demo wrapper.
- `demo/interactive.py`: browser UI for 2D nbody.
- `demo/interactive_3d.py`: browser UI for nbody-3d.

### RTL/test workflows

- `test/run_tests.sh`: standard, random, host, and generation-only test modes.
- `test/Makefile`: assemble, expected, compile, simulate, host, visualize, clean.
- `test/assembler.py`: assembly to `program.mem`.
- `test/expected_generator.py`: expected DMEM/regfile/trace generation.
- `test/random_tester.py`: random fuzzer.
- `test/host_uart_tester.py`: UART hardware test runner.
- `test/host_uart_helper.py`: manual UART helper.

### Hardware host workflows

- `sw/host/baremetal/main.c`: board-side UART monitor.
- `sw/host/baremetal/gpgpu_host.c/.h`: low-level GPGPU host access.
- `sw/host/baremetal/gpgpu_uart.py`: host-side Python UART client library.
- `sw/host/linux/host.py (deleted in Milestone 8)`: older raw serial host driver, likely legacy/stale.

## Generated artifacts in source directories

### Program outputs

- `sw/programs/<program>/<program>_x86`
- `sw/programs/<program>/<program>.elf`
- `sw/programs/<program>/<program>.map`
- `sw/programs/<program>/<program>_dump_real.asm`
- `sw/programs/<program>/<program>_program.asm`
- `sw/programs/<program>/<program>_instructions.mem`
- `sw/programs/<program>/data.csv`
- visualization outputs such as `.svg`, `.png`, `.gif`, `.mp4`, `.pgm`

### Test outputs

- `test/tests/test*/program.mem`
- `test/tests/test*/data.mem`
- `test/tests/test*/trace.csv`
- `test/tests/test*/regfile_c*.mem`
- `test/main`
- `test/simulation.log`
- `test/dumpfile.vcd`

### Legacy host outputs

- `fpga_dram_dump.mem`
- `fpga_reg_dump.mem`

## Important duplicated constants

- Memory depth: 2048 words across RTL, linker script, UART helpers, assembler, expected generator.
- Core/lane count: 32 across RTL, runtime header, linker script, tests, and adapters.
- GPGPU args window: byte address `0x00000040`, host DMEM words `16..19`.
- Default UART settings: usually `/dev/ttyACM0` or `/dev/ttyUSB1`, baud `115200`.
- Legacy mismatch: `sw/host/linux/host.py (deleted in Milestone 8)` assumes 1024-word memories and 9600 baud.

## Duplicated UART / FPGA-runner logic to characterize

Inspection of the existing scripts shows useful sharing already exists, but there is still duplicated orchestration and naming drift that should be characterized before refactoring:

- `sw/host/baremetal/gpgpu_uart.py` is the current reusable UART monitor client. It centralizes word normalization, memory-file parsing, prompt handling, ASCII/binary IMEM/DMEM load commands, DMEM dump parsing, `run`, and `done`.
- `sw/programs/fpga_run.py` correctly imports `GpgpuUartMonitor` and should remain the common program-kernel runner, but it still carries its own word normalization and GPGPU argument-window constants (`0x00000040 // 4`, four words). Those should eventually come from a shared ABI/config module.
- `test/host_uart_tester.py` also imports `GpgpuUartMonitor`, `DEPTH`, `read_mem_file`, and `trim_program_at_ret`, then duplicates the load-IMEM, clear/load-DMEM, run, dump-DMEM, compare, and done loop for tests. That loop should eventually share a lower-level board-kernel execution helper with `sw/programs/fpga_run.py`.
- `demo/interactive.py` and `demo/interactive_3d.py` contain their own FPGA backend loops with the same UART operations and the same GPGPU args base. These are future refactor candidates after demo characterization.

No refactor is approved yet. Keep these scripts as references until behavior is characterized and compatibility tests exist.

## Future naming cleanup candidates

The current filenames are compatibility surfaces, but the control-plane concepts should eventually have clearer names:

- `sw/host/baremetal/gpgpu_uart.py` -> board UART monitor/client library.
- `sw/programs/fpga_run.py` -> board kernel runner / program adapter runner.
- `test/host_uart_tester.py` -> hardware-in-the-loop RTL/program test runner.
- `test/host_uart_helper.py` -> board UART diagnostic tool.

Do not rename these files until wrappers/import compatibility and documentation migration are approved.

## Documentation mismatches to preserve as migration issues

- `README.md` describes stale `sw/programs/fpga_run.py` adapter hooks.
- `README.md` uses stale options such as direct `--steps`/`--runs` on `sw/programs/run.sh`.
- `programs/Readme.md` describes older output names.
- `demo/README.md` still describes nbody 3D as future work even though baseline contains nbody-3d files.
- `sw/host/linux/host.py (deleted in Milestone 8)` appears stale relative to the newer UART monitor protocol.

## Missing reproducible flows

- Vivado project generation.
- Bitstream generation.
- XSA export.
- Vitis/XSCT baremetal application build.
- Board programming.
- Hardware build-ID/capability detection.

## Initial script classification

### Preserve as reusable library

- `sw/host/baremetal/gpgpu_uart.py`
- `sw/programs/fpga_run.py`
- `programs/gpgpu_runtime.h`
- `programs/gpgpu.ld`
- `test/assembler.py`
- `test/expected_generator.py`
- `test/host_uart_helper.py`
- `test/host_uart_tester.py`
- `sw/programs/*/fpga.py`

### Retain as compatibility wrapper

- `run.sh`
- `sw/programs/run.sh`
- `demo/run.sh`
- `test/run_tests.sh`
- `sw/programs/Makefile`
- `test/Makefile`

### Refactor after characterization

- `demo/interactive.py`
- `demo/interactive_3d.py`
- `sw/programs/*/visualize.py`
- `test/random_tester.py`
- `test/program_checker.py`
- `sw/host/baremetal/main.c`
- `sw/host/baremetal/gpgpu_host.c/.h`

### Replace after parity

- `sw/host/linux/host.py (deleted in Milestone 8)`

### Possible deletion pending evidence

None approved.
