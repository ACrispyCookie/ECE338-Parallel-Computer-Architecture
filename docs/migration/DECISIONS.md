# Migration Decisions

This file records accepted control-plane migration decisions for the GPGPU repo.

## Baseline boundary

- Authoritative baseline commit: `7c5c12f20e7151773c2c8d72842d43f064244a9d`.
- Do not inspect, copy, cherry-pick, merge, or base architecture on later commits.
- Existing scripts remain behavioral references and compatibility surfaces until explicitly retired.

## Legacy-script deletion rule

No legacy script may be deleted until:

1. Callers and workflows are identified.
2. A replacement exists.
3. Supported options have replacements.
4. Legacy and replacement behavior have been compared.
5. Documentation has migrated.
6. Compatibility tests pass.
7. Deletion is explicitly approved.

## Initial planner scope

- Initial planner is mock-only.
- It supports goal definitions, typed configuration, provenance, dependency binding, goal kinds, visibility, deduplication, `list`, `plan`, and `explain`.
- It does not run Vivado, compilers, UART, demos, simulations, or hardware workflows.
- It does not implement artifact injection initially.

## Goal kind semantics

- `artifact`: produces a typed artifact and may be cacheable.
- `action`: changes external or hardware state and is not cacheable as a normal build artifact.
- `service`: starts a long-running process and must expose lifecycle semantics.
- `check`: produces a verification result.

## Public goal naming

Accepted initial names prefer explicit hardware/software namespaces:

- `sw.program.native`: build native reference executable.
- `sw.program.elf`: build RISC-V ELF.
- `sw.program.image`: build GPGPU instruction-memory image.
- `hw.board.bitstream`: build the programmable-logic image for a board/platform selection.
- `hw.board.program`: configure/program the FPGA fabric on the selected board.
- `hw.board.kernel.load`: load a GPGPU kernel/program image into board memory through the selected transport.
- `hw.board.kernel.run`: run a loaded kernel on the board.
- `demo.run`: run the selected demo service.
- `test.rtl`: run RTL checks.
- `test.program`: run program checks.

Internal hardware-support goals should use the same namespace style:

- `hw.rtl.assemble`: assemble RTL test fixtures.
- `hw.rtl.sim_executable`: build the simulator executable.
- `hw.board.project`: prepare a board/platform project artifact.

No `demo.nbody3d` alias is included initially. Users select `demo=nbody-3d` on `demo.run` until aliases are explicitly approved later.

Spelling note: use `bitstream`, not `bistream`.

## Board versus FPGA wording

Use `board` when the operation targets a selected physical or logical board instance and may involve board-local state, transport, firmware, or programming cables.

Use `fpga` or `bitstream` for artifact concepts that describe the programmable-logic image itself.

Therefore:

- `hw.board.bitstream` is an artifact-producing build goal.
- `hw.board.program` is an action goal that programs/configures the selected board with a bitstream.

Avoid adding an extra verb suffix such as `.build` when the noun already describes the public artifact goal. The goal kind and planner output distinguish build/artifact behavior.

## Compatibility filenames versus future domain names

Existing script filenames stay unchanged until characterized. Better conceptual names may be introduced behind the new control plane later, but file renames require wrappers, import compatibility, documentation migration, and explicit approval.

Noted future cleanup candidates:

- `host/baremetal/gpgpu_uart.py`: board UART monitor/client library.
- `programs/fpga_run.py`: board kernel runner / program adapter runner.
- `test/host_uart_tester.py`: hardware-in-the-loop test runner.

## Parameter scopes

- Shared selection: architecture, platform, board, program, demo, backend, toolchain, variant.
- Artifact-affecting: RTL parameters, memory sizes, compiler flags, Vivado strategy, FPGA part, source hashes, tool versions.
- Runtime: demo FPS, dataset, kernel calls, UART timeout, visualization mode.
- Executor: dry-run, verbosity, parallel jobs, log formatting.
- Machine-local: UART port, JTAG serial, board IP, local tool paths.

## Configuration precedence

Accepted initial order excludes artifact injection:

1. Schema defaults.
2. Repo-wide component defaults.
3. Profile selection values, used to choose manifests.
4. Selected architecture/platform/program/demo manifests.
5. Goal defaults for values still unset by higher-specificity files.
6. Named profile overrides.
7. Gitignored machine-local config, or `local.example.toml` fallback for the mock planner.
8. Environment variables for tool discovery only.
9. CLI convenience flags.
10. CLI `--set namespace.key=value`.

Every resolved setting preserves provenance for `explain`.

`variant` is intentionally absent from the initial schema until a concrete build variant use case exists.

## Hardware-state policies

Accepted policy names:

- `if-needed`
- `always`
- `never`

Initial policy settings:

- `board.configure_policy`
- `kernel.load_policy`

Host-side caches must not prove external hardware state. If hardware cannot expose build IDs or capabilities, record that limitation and fail or act according to explicit policy.

## Artifact identity

Artifact identity should consider:

- goal identifier,
- implementation version,
- artifact-affecting normalized parameters,
- input source hashes,
- relevant tool versions,
- relevant generated configuration,
- dependency artifact identities.

Runtime-only, executor-only, and unrelated machine-local settings must not affect artifact identity.

## Artifact injection

Initial decision: do not implement `--use-artifact` yet. Reconsider later after artifact metadata and compatibility validation exist.
