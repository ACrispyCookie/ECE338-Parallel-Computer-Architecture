# Migration Compatibility Record

Compatibility work must preserve existing behavior until parity is proven.

## Rule

Existing scripts are compatibility interfaces, behavioral references, regression oracles, and rollback mechanisms. They must stay in place until explicitly approved for retirement.

## Current compatibility status

No legacy command has been replaced yet.

The planner foundation is mock-only and does not execute current workflows. Therefore no legacy-versus-new parity claim is made for execution behavior.

## Legacy workflows requiring characterization

### Program build and native run

Representative commands:

```bash
./run.sh --help
./run.sh -p nbody x86 --x86 --no-visualize
make -C programs PROG=nbody riscv
make -C programs PROG=nbody nbody/nbody_instructions.mem
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
host/baremetal/gpgpu_uart.py
programs/fpga_run.py
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

Refactoring target: keep `host/baremetal/gpgpu_uart.py` as the protocol reference initially, then extract shared board-kernel execution helpers only after `programs/fpga_run.py` and `test/host_uart_tester.py` have characterization tests proving equivalent behavior.

## New planner goals and intended legacy adapters

Current planned mapping:

- `sw.program.native` -> adapter around native `programs/Makefile` flow.
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

- `host/linux/host.py` after replacement and parity.
- tracked generated assembly snapshots only after confirming their role.
