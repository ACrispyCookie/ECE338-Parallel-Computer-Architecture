# Migration Plan

## Objective

Migrate the repository toward a maintainable GPGPU control plane exposed through a typed goal planner and, later, executor.

The eventual public interface is expected to support:

```bash
gpgpu list
gpgpu plan <goal>
gpgpu explain <goal>
gpgpu run <goal>
```

## Ground rules

- Preserve existing behavior throughout migration.
- Do not delete, move, rename, or rewrite legacy scripts until parity is proven and deletion is explicitly approved.
- Implement one small milestone at a time.
- Stop at checkpoints for review.
- Prefer typed configuration and typed artifacts over recursive string forwarding.

## Completed milestones

### Phase 0: read-only inventory

Completed as an inspection report against baseline commit `7c5c12f20e7151773c2c8d72842d43f064244a9d`.

Findings included:

- existing program build, native run, FPGA UART, demo, RTL test, and UART test entry points;
- generated artifacts currently written into source directories;
- duplicated ABI constants;
- stale documentation/API mismatches;
- missing reproducible Vivado/Zynq project flow.

### Milestone 1: mock planner foundation

Implemented in commit `8e1d945` on branch `gpgpu-planner-foundation`.

Added:

- `tools/gpgpu/` mock planner package;
- typed config schema with provenance;
- goal definitions and goal kinds;
- deterministic graph planning;
- fake-vs-FPGA conditional dependencies;
- public/internal visibility;
- `python3 -m tools.gpgpu list|plan|explain`;
- unit tests for planner behavior.

No existing legacy workflow was modified.

### Milestone 1 follow-up: migration records and unified names

Implemented in commit `c9c764d` on branch `gpgpu-planner-foundation`.

Added migration records under `docs/migration/` and renamed initial goal identifiers to accepted hierarchical names such as `hw.board.bitstream`, `hw.rtl.assemble`, and `sw.program.native`.

### Milestone 2: file-backed manifests and local CLI wrapper

Objective: move selected entities, profiles, and machine-local defaults out of `tools/gpgpu/config.py` into repo-owned TOML files while preserving current planner behavior.

Implemented in commit `8d4c0f1` on branch `gpgpu-planner-foundation`.

Files expected to change:

- `config/gpgpu/components.toml`
- `config/gpgpu/profiles.toml`
- `config/gpgpu/local.example.toml`
- `config/gpgpu/architectures/gpgpu32.toml`
- `config/gpgpu/platforms/zynq7000-zedboard.toml`
- `config/gpgpu/programs/nbody.toml`
- `config/gpgpu/programs/nbody-3d.toml`
- `config/gpgpu/demos/nbody.toml`
- `config/gpgpu/demos/nbody-3d.toml`
- `.gitignore`
- `tools/gpgpu/config.py`
- `tools/gpgpu/gpgpu`
- `tests/gpgpu/test_planner.py`

Non-goals:

- no `gpgpu run`;
- no real Vivado, UART, compiler, RTL simulation, or demo execution;
- no legacy-script rename/deletion;
- no `--use-artifact`;
- no `demo.nbody3d` alias.

Expected evidence:

- file-backed profile loads deterministically;
- unknown profile fails;
- unknown manifest setting fails;
- type-invalid manifest setting fails;
- profile overrides selected manifest defaults;
- unused `variant` placeholder is removed from the initial schema;
- provenance reports TOML file and section names;
- CLI output stays equivalent to current planner behavior;
- local board config is optional and gitignored;
- `tools/gpgpu/gpgpu` works as a local wrapper.

Commit policy was satisfied: changes were reviewed, tested, then committed after approval.

### Milestone 4: clarify planner config naming

Implemented in commits `8ba72eb` and `d7637de` on branch `gpgpu-planner-foundation`.

Added/changed:

- `platform` config concept renamed to `board_type`;
- `components.toml` renamed to `defaults.toml`;
- board type manifests moved under `config/gpgpu/board_types/`;
- profiles moved under `config/gpgpu/profiles/<name>.toml`;
- local board instance defaults renamed from `lab-zed` to `zedboard`;
- local-origin settings are marked in `gpgpu explain` provenance;
- `kernel.kernel_calls` retained for future `hw.board.kernel.run` use;
- fake test settings remain rejected until real test behavior exists.

No existing legacy workflow was modified.

### Milestone 5: richer mock planner output

Objective: enrich `gpgpu plan` and `gpgpu explain` with compact display-only metadata while preserving graph construction and avoiding fake implementation details.

Implemented in commits `1d70211` and `71e0e2a` on branch `gpgpu-planner-foundation`.

Files changed:

- `tools/gpgpu/goals.py`
- `tools/gpgpu/planner.py`
- `tools/gpgpu/cli.py`
- `tests/gpgpu/test_planner.py`
- `docs/migration/PLAN.md`

Evidence:

- default `plan` output stays compact;
- `-v`/`--verbose` prints expected outputs, side effects, lifecycle, and backend include/omit notes;
- `explain -v` prints artifact identities;
- explanatory metadata does not alter graph shape or artifact identities;
- fake backend still omits hardware dependencies;
- FPGA backend still includes hardware-load dependencies;
- full planner test suite passes.

### Milestone 6: legacy workflow characterization

Objective: add safe characterization tests for current legacy entry points before wrapping any real workflow in the new planner.

Implemented in commit `0de03ba` on branch `gpgpu-planner-foundation`.

Evidence:

- root `./run.sh --help` is characterized;
- `sw/programs/run.sh --help` is compared with the root wrapper surface;
- `sw/programs/fpga_run.py --help` is characterized;
- `test/host_uart_tester.py --help` is characterized;
- `sw/host/baremetal/gpgpu_uart.py` imports without opening serial;
- shared UART constants/helpers are recorded before adapter work;
- duplicated UART/kernel-run logic findings are documented.

### Milestone 7: first native compatibility adapter

Objective: add the first narrow `gpgpu run` compatibility adapter for a non-hardware artifact goal while preserving legacy behavior.

Implemented in commit `b444ed0` on branch `gpgpu-planner-foundation`.

Evidence:

- unsupported `run` goal fails clearly;
- native adapter invokes the exact legacy Make command;
- native adapter produces the ignored legacy executable path;
- native adapter does not create `out/` artifacts;
- native adapter does not run the program or create `data.csv`;
- planner, legacy characterization, executor, and full discovery tests pass.

## Completed structural milestone

### Milestone 8: split hardware/software trees and introduce `out/`

Objective: establish the repository domain layout before adding more workflow adapters.

Implemented in commit `1019b8d` on branch `gpgpu-planner-foundation`.

Added/changed:

- moved RTL from `src/` to `hw/rtl/`;
- moved host code from `host/` to `sw/host/`;
- moved program code from `programs/` to `sw/programs/`;
- deleted stale `host/linux/host.py` with explicit user approval;
- kept `test/` in place for now;
- kept `tools/`, `demo/`, `config/`, and `docs/` as top-level roots;
- introduced ignored `out/` with tracked `out/.gitkeep`;
- moved hardware generated-artifact ignore rules to `hw/.gitignore`.

Evidence:

- domain-layout test proves `hw/rtl`, `sw/host/baremetal`, `sw/programs`, and `out/.gitkeep` exist;
- old root `src`, `host`, and `programs` paths are gone;
- stale `sw/host/linux` is gone;
- root `run.sh` routes to `sw/programs/run.sh`;
- native adapter invokes `make -C sw/programs ...`;
- planner, executor, legacy characterization, and full discovery tests pass.

## Completed program-adapter milestone

### Milestone 9: RISC-V ELF compatibility adapter

Objective: add the next narrow `gpgpu run` compatibility adapter for the existing RISC-V ELF build artifact.

Implemented in commit `9de4947` on branch `gpgpu-planner-foundation`.

Added/changed:

- support `tools/gpgpu/gpgpu run sw.program.elf --set program=<program>`;
- delegate to `make -C sw/programs PROG=<program> <program>/<program>.elf`;
- verify the legacy ELF artifact at `sw/programs/<program>/<program>.elf`;
- keep `sw.program.image` and hardware/demo goals unsupported by the executor for that milestone;
- document the current config/Makefile mismatch for `program.optimization`, `program.march`, and `program.mabi`.

Evidence:

- ELF adapter reports the exact legacy Make command;
- ELF adapter produces `sw/programs/nbody/nbody.elf`;
- unsupported `sw.program.image` still fails clearly before Milestone 10;
- native adapter behavior is unchanged;
- planner, executor, legacy characterization, and full discovery tests pass.

## Completed program-adapter milestone

### Milestone 10: program instruction-memory image compatibility adapter

Objective: add the next narrow `gpgpu run` compatibility adapter for the existing RISC-V instruction-memory image artifact.

Implemented in commit `09eb04e` on branch `gpgpu-planner-foundation`.

Added/changed:

- support `tools/gpgpu/gpgpu run sw.program.image --set program=<program>`;
- delegate to `make -C sw/programs PROG=<program> <program>/<program>_instructions.mem`;
- verify the legacy memory artifact at `sw/programs/<program>/<program>_instructions.mem`;
- report the supporting dump artifact at `sw/programs/<program>/<program>_dump_real.asm` when produced;
- keep composition/check/hardware/demo goals unsupported by the executor until their own milestones;
- document that generated program artifacts still live under `sw/programs/<program>/`.

Evidence:

- image adapter reports the exact legacy Make command;
- image adapter produces `sw/programs/nbody/nbody_instructions.mem`;
- image adapter reports `sw/programs/nbody/nbody_dump_real.asm` when produced;
- unsupported `test.program` still fails clearly;
- native and ELF adapter behavior is unchanged;
- planner, executor, legacy characterization, and full discovery tests pass;
- generated program artifacts are cleaned before commit.

## Completed executor-structure milestone

### Milestone 11: executor adapter registry and artifact-policy documentation

Objective: clean up the executor structure now that three program adapters exist, and record the Makefile/backend, `out`, and cleaning policies before changing artifact locations.

Implemented in commits `b0fc64a` and `19e6e1e` on branch `gpgpu-planner-foundation`.

Added/changed:

- introduced `tools/gpgpu/adapters/` with a small goal-id adapter registry;
- moved software program adapter functions into `tools/gpgpu/adapters/sw_programs.py`;
- kept `tools/gpgpu/executor.py` as a thin coordinator that dispatches by goal id;
- moved run-result formatting/types back into `tools/gpgpu/executor.py` rather than keeping a premature one-purpose module;
- kept all command behavior and output paths unchanged;
- documented that Makefile remains the backend for now, while a later Python-native backend remains possible;
- documented the future `gpgpu clean` subcommand model.

Evidence:

- adapter registry exposes `sw.program.native`, `sw.program.elf`, and `sw.program.image`;
- executor no longer owns domain-specific `_run_sw_program_*` methods;
- native, ELF, and image adapters still execute the exact same Make commands;
- unsupported goals still fail clearly;
- planner, executor, legacy characterization, and full discovery tests pass.

## Completed artifact-layout milestone

### Milestone 12: route software artifacts to `out/`

Objective: move software artifact outputs for the current program adapters out of `sw/programs/<program>/` and into identity-scoped directories under `out/`.

Implemented in commits `c2c01cf` and `ade33ee` on branch `gpgpu-planner-foundation`.

Added/changed:

- use planner root artifact identity for `gpgpu run` output directories;
- have `tools/gpgpu/executor.py` compute the artifact directory and pass it to adapters through `ExecutionContext`;
- route `sw.program.native`, `sw.program.elf`, and `sw.program.image` outputs to `out/artifacts/<goal-id>/<program>/<identity>/`;
- keep Makefile as the compatibility backend, but add `OUT_DIR` support and named `native`, `elf`, and `image` targets;
- preserve current compiler/linker/objdump/awk behavior and generated filenames;
- leave `gpgpu clean` for a later milestone.

Evidence:

- native, ELF, and image artifacts appear under `out/artifacts/<goal-id>/<program>/<identity>/`;
- no source-tree software generated artifacts are left behind by `gpgpu run`;
- artifact-affecting settings change output directories;
- runtime-only settings do not change output directories;
- tracked generated snapshots such as `sw/programs/nbody/nbody_program.asm` stay clean;
- planner, executor, legacy characterization, and full discovery tests pass.

## Completed run-execution milestone

### Milestone 13: dependency-aware `gpgpu run`

Objective: make `gpgpu run <goal>` execute the planned graph in topological order instead of invoking only the root adapter.

Implemented in commit `5b484e4` on branch `gpgpu-planner-foundation`.

Added/changed:

- added `Executor.run_plan(plan)`;
- preflighted the plan before running so missing public/action/service/check adapters fail before side effects;
- visibly skipped internal planner-only artifact nodes that have no adapter;
- executed registered adapters in `plan.nodes` order;
- stopped on the first nonzero adapter return code;
- showed readable run progress, completed goals, skipped goals, failed goal stdout/stderr, and summary counts;
- passed produced dependency artifacts into dependent adapter contexts;
- made `sw.program.image` consume the `sw.program.elf` artifact through `ELF_IN` instead of rebuilding ELF in the image artifact directory.

Evidence:

- `gpgpu run sw.program.image` runs `sw.program.elf` before `sw.program.image`;
- `sw.program.compile_riscv` is visibly skipped as an internal planner-only artifact;
- `sw.program.image` command includes `ELF_IN=<sw.program.elf artifact>`;
- image artifact directory contains memory/dump outputs, not duplicate ELF/map outputs;
- failing dependency stops dependent execution and prints stdout/stderr;
- missing required root/check/action/service adapter fails before dependencies run;
- planner, executor, legacy characterization, and full discovery tests pass.

## Current implementation scope

### Milestone 14: Docker-like `gpgpu run` progress reporter

Objective: make `gpgpu run` output more focused and readable while preserving deterministic non-interactive behavior.

Scope:

- add a run reporter/event-sink layer separate from adapter execution;
- support deterministic compact progress output for non-TTY, `--progress plain`, and tests;
- support a TTY-oriented reporter with a current-goal spinner/progress line;
- add `--progress auto|plain|tty`;
- keep completed goals compact, showing status, elapsed time, and produced artifact basenames;
- keep skipped internal goals compact with an explicit reason;
- expand failed goal output with command, stdout, stderr, exit code, and stopped dependents;
- leave graph semantics, artifact layout, adapter commands, cache behavior, and dependency selection unchanged.

Non-goals:

- no live subprocess stdout streaming;
- no third-party terminal UI dependency;
- no cache hit/miss skipping;
- no `gpgpu clean`;
- no parallel execution;
- no hardware, UART, Vivado, demo, or RTL execution.

Expected evidence:

- reporter tests cover compact completed goals, skipped goals, failure expansion, and spinner/current-goal rendering;
- CLI tests cover `--progress plain` deterministic output;
- existing adapter artifact tests pass with the new compact run output;
- planner, executor, legacy characterization, and full discovery tests pass.

## Dependency execution policy

Dependencies are declared in `tools/gpgpu/planner.py`, especially in `Planner._dependency_goal_ids()`. The planner builds and displays dependency graphs for `list`, `plan`, `explain`, and now `run`.

`gpgpu run <goal>` executes registered adapters in the plan's topological order. Internal artifact nodes without adapters may be skipped only when they are planner-only implementation detail placeholders. Public goals, check goals, action goals, and service goals without adapters fail during preflight before any dependency adapter runs.

## Makefile backend and future Python backend direction

For now, the control plane keeps the existing Makefile as the implementation backend for software artifacts. The goal graph describes semantic operations such as `sw.program.elf` and `sw.program.image`; the adapter invokes the corresponding existing Make target as the compatibility implementation.

Current policy:

- use Makefile targets for compatibility milestones;
- do not reimplement compiler, objdump, linker, or awk behavior in Python while parity is still being established;
- record mismatches between typed planner settings and Makefile hardcoded values instead of silently changing behavior;
- keep generated artifacts in legacy locations until an explicit `out/` migration milestone.

Possible future policy:

- either keep Makefile as a thin backend that accepts typed variables from `gpgpu`, such as `OUT_DIR`, `OPT`, `MARCH`, and `MABI`;
- or switch specific adapters to Python-native commands once legacy behavior is characterized and parity tests exist.

The decision should be per workflow. Program builds may move to Python earlier than Vivado/RTL workflows if that reduces duplication safely, but no backend switch should happen without characterization and parity evidence.

## Future `gpgpu clean` direction

Cleaning must be explicit and goal-instance scoped. `gpgpu run` should not silently call broad `make clean`, because broad clean can delete unrelated generated artifacts and can dirty tracked legacy generated snapshots.

Future command shape:

```bash
gpgpu clean <goal> --set program=nbody
gpgpu clean sw.program.image --profile zed-demo
gpgpu run sw.program.image --force --set program=nbody
```

Policy:

- `gpgpu clean <goal>` removes only artifacts owned by the normalized goal instance;
- `--force` rebuilds only the requested artifact instance and its necessary dependencies, not the whole source tree;
- action goals such as board configuration and kernel load are not cleaned through artifact deletion;
- service goals require lifecycle cleanup, not file deletion;
- source-tree legacy artifacts require extra caution until they move under `out/`;
- once artifacts live under `out/artifacts/<goal>/<program>/<identity>/`, clean can safely remove that directory.

Near-term implementation should keep using targeted test cleanup only. Do not add the `clean` command until artifact ownership and `out/` layout are defined.

## Future `executor.py` direction

The executor should stay small while adapters are few, and must not grow into a long unstructured `if goal_id == ...` chain.

Current/near-term direction:

- keep `executor.py` as a thin coordinator;
- use a tiny adapter registry keyed by goal id;
- keep one adapter per explicitly characterized workflow;
- keep unsupported goals failing clearly until they have adapters.

Medium-term direction:

```text
tools/gpgpu/executor.py
tools/gpgpu/adapters/
  __init__.py
  sw_programs.py
  hw_rtl.py
  hw_board.py
  demo.py
```

`executor.py` owns generic execution concerns: adapter lookup, repository root, run-result type/formatting, error handling, and later dry-run/force/verbosity/service lifecycle behavior.

Domain adapter modules own command construction and artifact verification for their area. Shared subprocess helpers may move to a common module when more than one adapter family needs them.

Long-term direction: executor should walk a validated planned graph in dependency order, cache-skip only compatible artifact goals, never cache-skip action goals, and manage service lifecycles explicitly.

## Future `config.py` direction

`config.py` currently combines schema definition, TOML loading, precedence resolution, type coercion, provenance tracking, and selected-manifest loading. That is acceptable for the foundation but should be split once the model stabilizes.

Near-term rule:

- do not add placeholder settings without real planner or adapter behavior;
- document legacy mismatches instead of silently changing Makefile semantics;
- keep unknown and type-invalid settings as immediate errors.

Medium-term direction:

```text
tools/gpgpu/config/
  __init__.py
  schema.py
  resolver.py
  provenance.py
  toml_loader.py
  types.py
```

Responsibilities:

- `schema.py`: known settings, types, scopes, defaults;
- `resolver.py`: precedence order and selected-manifest application;
- `provenance.py`: source labels and explain-format helpers;
- `toml_loader.py`: TOML reading, flattening, validation;
- `types.py`: enums, coercion helpers, typed values.

Future decision: decide whether typed planner settings are passed into legacy Make, for example `OPT`, `MARCH`, and `MABI`, or whether new toolchain behavior moves to a new adapter-controlled build path. Defer this until after `sw.program.image` exposes the objdump and memory-format boundary.

## Intended next milestones

1. Complete Milestone 13 dependency-aware `gpgpu run`.
2. Add an explicit `gpgpu clean` design/implementation milestone after graph execution and artifact ownership are defined.
3. Revisit planner-only internal goals such as `sw.program.compile_riscv` and decide whether to remove, merge, or implement them.
4. Consider `test.program` as a check goal for native-vs-image comparison.
5. Connect RTL test goals behind adapters only after characterization.
6. Connect UART/board action goals behind explicit hardware-state policies.
7. Connect Vivado/Zynq bitstream goals after a reproducible flow is specified.

## Rollback

For uncommitted changes:

```bash
git restore .
git clean -fd docs/migration
```

For committed planner milestone:

```bash
git switch <target-branch>
git branch -D gpgpu-planner-foundation
```

Only use rollback commands after confirming no wanted local changes would be lost.
