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

- `sw/host/baremetal/gpgpu_uart.py`: board UART monitor/client library.
- `sw/programs/fpga_run.py`: board kernel runner / program adapter runner.
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

## Declarative dependency metadata

Accepted Milestone 15 direction:

- Goal dependencies are declared on `GoalDefinition` objects in `tools/gpgpu/goals.py`.
- The planner resolves those declarations with equality-only conditions for now.
- Do not introduce a general workflow DSL until real use cases require it.
- Conditional demo dependencies are represented as backend conditions, not goal-specific planner branches.
- `sw.program.compile_riscv` is removed as a planner goal because it does not currently own a distinct artifact boundary; `sw.program.elf` is the current RISC-V compile/link artifact boundary.
- Artifact specs are intentionally deferred past Milestone 15.

## Generic artifact layout and clean safety policy

Accepted Milestone 16 direction:

- Artifact directories use `out/artifacts/<goal>/<identity>/`.
- Do not include `program` as a universal artifact path component; program and other settings belong in metadata.
- Each successful artifact goal writes `artifact.toml` containing goal, kind, identity, params, produced files, and dependency identities.
- `tools/gpgpu/artifacts.py` owns artifact path and metadata policy shared by run and clean.
- `gpgpu clean` deletes only exact normalized artifact directories under `out/artifacts/<goal>/<identity>/`.
- `gpgpu clean` never deletes source-tree files and never calls `make clean`.
- Root-only clean supports artifact goals only.
- `--deps` cleans artifact nodes in planner order and does not perform action/service/check lifecycle cleanup.
- Missing artifact directories are reported but are not errors.
- Broad paths such as `out/`, `out/artifacts/`, and `out/artifacts/<goal>` are refused.
- Symlink artifact directories are refused initially.
- Full artifact specs, cache validation, artifact injection, and garbage collection remain deferred.

## Planning-only cache status

Accepted Milestone 17 direction:

- `gpgpu plan` may report `CACHE HIT` or `CACHE MISS` for artifact goals only.
- Cache status is presence metadata, not execution policy.
- A hit requires `out/artifacts/<goal>/<identity>/artifact.toml` to exist and contain matching `goal` and `identity` values.
- Missing directories, missing metadata, invalid metadata, and goal/identity mismatches are misses.
- Action, service, and check goals are not cache hits and should not show compact cache status.
- Verbose plan/explain output reports cache state, path, and reason.
- `gpgpu run` must continue executing adapters even when plan reports a cache hit until a later cache-execution milestone defines validation and skip semantics.
- Source hashes, tool versions, generated config hashes, artifact specs, and artifact injection remain deferred.

## Validated artifact cache status

Accepted Milestone 18 direction:

- Compact cache rendering remains binary: `CACHE HIT` only for internal state `hit`; every other internal state renders as `CACHE MISS`.
- Internal non-hit states include `missing`, `unknown`, `incomplete`, `invalid`, and `stale`.
- Old metadata without validation hashes is `unknown` and therefore a miss.
- A validated hit requires matching goal/identity metadata, expected output files, matching output hashes, matching explicit input hashes, and matching direct dependency identities.
- Successful artifact runs record produced output hashes in `artifact.toml`.
- Current software artifact goals record explicit input hashes for `sw/programs/Makefile` and selected files under `sw/programs/<program>/` such as C/header/assembly/linker-script files and `fpga.py`.
- The current input selection is implemented by `Executor._input_paths_for` as a transitional, conservative software-goal selector; it is not intended to be the long-term artifact-spec interface.
- Future milestones should move input declarations into goal/artifact metadata alongside expected outputs, adapter ownership, tool-command fingerprints, and eventually tool-version validation.
- `gpgpu run` still executes adapters even when plan reports a validated hit; cache skipping remains deferred.
- Tool-version validation, command fingerprints, generated config hashes, full artifact specs, artifact injection, and hardware/action/service/check cache semantics remain deferred.

## Current-state reevaluation

Accepted Milestone 19 direction:

- The current branch has a real planner/executor/artifact foundation plus three software compatibility adapters, but most original hardware, RTL, check, demo, UART, Vivado, and visualization goals remain planned-only.
- `docs/migration/CURRENT_STATE.md` is the current implementation map for non-test source files, goal coverage, data structures, build-system flow, and transitional-code inventory.
- Cleanup should precede deeper adapter expansion where the foundation has known ambiguity: repo-root resolution, check-goal params, declarative artifact specs, strict adapter output contracts, and command/tool fingerprints.
- Transitional implementation pieces should either be documented as temporary or moved into declarative metadata before becoming precedent for hardware/demo/check workflows.

## Schema-driven selection and root consistency

Accepted Milestone 20 direction:

- Avoid adding new files for small conveniences; repo-root consistency is handled by explicit CLI root passing through existing planner/executor/cleaner constructors.
- Manifest-selection behavior is declared by `SettingSpec.manifest_dir`, not by a hardcoded resolver key set.
- CLI selection overrides for manifest-selecting settings are applied before selected manifests so `--set program=nbody` loads `config/gpgpu/programs/nbody.toml`; all CLI overrides are then applied again at final precedence.
- Explicit setting overrides still win at final precedence, e.g. `--set program=nbody --set program.optimization=O3` yields `O3` from `CLI --set`.
- Direct single-goal `Executor.run()` is removed; graph execution through `Executor.run_plan()` is the supported execution path.

## Declarative schema, goals, and artifact specs

Accepted Milestone 21 direction:

- Substantial control-plane definitions belong in declarative project data rather than embedded Python tables.
- `config/gpgpu/schema.toml` owns setting definitions, including enum choices and manifest-selection metadata.
- `config/gpgpu/goals.toml` owns goal definitions, dependencies, conditional notes, and artifact input/output specs.
- Python owns typed dataclasses, TOML loading, validation, planning, execution, and artifact/cache algorithms.
- Artifact validation compares recorded metadata against the current declarative input/output spec before trusting hashes.
- `Executor._input_paths_for()` is removed; software input selection is no longer hardcoded in the executor.
- `sw.program.image` expected outputs describe current adapter reality: instruction-memory image and objdump artifact.

## Strict typed artifact output contracts

Accepted Milestone 22 direction:

- Keep the artifact output model minimal: `role`, `path`, and `type`.
- Output roles are stable interface names used by consumers and metadata.
- Output paths describe the current storage location relative to the artifact directory.
- Output types are semantic compatibility strings such as `riscv-elf`, `linker-map`, `instruction-memory`, `objdump`, and `native-executable`; there is no type registry yet.
- Successful artifact metadata records produced outputs under `[produced.<role>]` with `path` and `type`, not as a loose `produced.files` list.
- Cache validation treats output role, path, or type drift as a miss/stale condition before trusting hashes.
- An artifact adapter returning success is not sufficient: the executor requires every declared output to exist before recording the run as successful.
- Dependency artifact consumption uses dependency role plus output role, for example `dependency_outputs["elf"]["elf"]`, rather than filename suffix guessing.
- `sw.program.image` consumes the `sw.program.elf` dependency through its declared `elf` output of type `riscv-elf`.
- Cache skipping remains deferred; `gpgpu run` still executes adapters even when planning reports `CACHE HIT`.

## Goal instance parameter model

Accepted Milestone 23 direction:

- Goal definitions use one production-shaped `params` field for normalized goal-instance parameters across all goal kinds.
- The old `artifact_params` and `runtime_params` goal fields are removed rather than kept as transitional aliases.
- Artifact goals use `params` as the artifact-affecting parameter set for artifact identity.
- Check, action, and service goals also use `params` so plan/explain output describes the normalized operation deterministically.
- Cache status remains limited to artifact goals; check/action/service goals must not show compact `CACHE HIT`/`CACHE MISS` output.
- Runtime-vs-artifact-vs-machine-local semantics remain defined by the central setting schema scopes, not by separate per-goal field names.
