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

## Completed run-output milestone

### Milestone 14: Docker-like `gpgpu run` progress reporter

Objective: make `gpgpu run` output more focused and readable while preserving deterministic non-interactive behavior.

Implemented in commits `c2d3ce3` and `a8b2859` on branch `gpgpu-planner-foundation`.

Added/changed:

- added a run reporter/event-sink layer separate from adapter execution;
- supported deterministic compact progress output for non-TTY, `--progress plain`, and tests;
- supported a TTY-oriented reporter with a single mutable current-goal area that clears and replaces the spinner/status line on completion or failure;
- added `--progress auto|plain|tty`;
- kept completed goals compact, showing status, elapsed time, and produced artifact basenames;
- kept skipped internal goals compact with an explicit reason;
- expanded failed goal output with command, stdout, stderr, exit code, and stopped dependents;
- left graph semantics, artifact layout, adapter commands, cache behavior, and dependency selection unchanged.

Evidence:

- reporter tests cover compact completed goals, skipped goals, failure expansion, and current-goal rendering;
- CLI tests cover `--progress plain` deterministic output;
- existing adapter artifact tests pass with the compact run output;
- planner, executor, legacy characterization, and full discovery tests pass.

## Completed artifact-layout milestone

### Milestone 16: generic artifact layout and `gpgpu clean`

Objective: make artifact directories goal-generic, record per-artifact metadata, and add a safe goal-instance-scoped clean command.

Scope:

- add `tools/gpgpu/artifacts.py` as the shared owner of artifact layout policy;
- change generated artifact directories from `out/artifacts/<goal>/<program>/<identity>/` to `out/artifacts/<goal>/<identity>/`;
- write `artifact.toml` in each successful artifact directory with goal, kind, identity, params, produced files, and dependency identities;
- add `tools/gpgpu/cleaner.py`;
- add `gpgpu clean <goal> [--dry-run] [--deps]`;
- clean only exact normalized artifact directories under `out/artifacts/<goal>/<identity>/`;
- root-only clean supports artifact goals only;
- `--deps` selects artifact nodes in planner order;
- refuse broad, outside, and symlink paths.

Non-goals:

- no full artifact specs;
- no cache hit/miss skipping;
- no artifact injection;
- no broad `out/` garbage collection;
- no source-tree legacy cleanup;
- no `make clean`;
- no hardware state, service lifecycle, Vivado, UART, RTL, or demo cleanup.

Expected evidence:

- executor uses the shared artifact layout helper;
- software run output and produced files use `out/artifacts/<goal>/<identity>/` with no program path component;
- `artifact.toml` exists and records params, produced files, and dependency identities;
- dry-run clean reports exact paths without deletion;
- actual clean deletes only owned artifact directories;
- `--deps` includes artifact dependencies in plan order;
- non-artifact root-only clean fails clearly;
- safety tests reject broad, outside, and symlink paths;
- planner, executor, cleaner, legacy characterization, and full discovery tests pass.

## Completed cache-status milestone

### Milestone 17: planning-only cache status

Objective: report cache presence in `gpgpu plan` and `gpgpu explain` using the generic artifact layout and `artifact.toml` metadata without changing execution behavior.

Scope:

- artifact goals show compact `CACHE HIT` or `CACHE MISS` status in plan output;
- status is computed from `out/artifacts/<goal>/<identity>/artifact.toml`;
- matching goal and identity metadata is treated as a hit;
- missing artifact directory, missing metadata, invalid metadata, or mismatched goal/identity is treated as a miss;
- verbose plan/explain output reports cache state, path, and reason;
- action, service, and check goals do not show compact cache status;
- `gpgpu run` still executes adapters even when plan reports a hit.

Non-goals:

- no cache skipping;
- no source-hash or tool-version validation;
- no full artifact specs;
- no artifact injection;
- no hardware/service/action cleanup behavior;
- no broad artifact garbage collection.

Expected evidence:

- clean artifacts then `gpgpu plan sw.program.image --set program=nbody` reports misses;
- after `gpgpu run sw.program.image --set program=nbody`, plan reports hits for the built artifacts;
- after `gpgpu clean sw.program.image --deps --set program=nbody`, plan reports misses again;
- tests cover missing metadata, matching metadata, metadata mismatch, non-artifact compact output, and run-not-skipped behavior;
- planner, executor, cleaner, legacy characterization, and full discovery tests pass.

## Completed cache-validation milestone

### Milestone 18: validated artifact cache status

Objective: strengthen cache status so compact `CACHE HIT` means the artifact validates against recorded outputs, inputs, and direct dependency identities. Every internal status other than `hit` is rendered compactly as `CACHE MISS`.

Scope:

- old goal/identity-only metadata is now `unknown` and compact `CACHE MISS`;
- successful artifact runs record output file hashes in `artifact.toml`;
- successful software artifact runs record explicit source/input hashes for `sw/programs/Makefile` and selected program files;
- cache validation checks produced file existence, output hashes, input hashes, and direct dependency identities;
- verbose plan/explain output reports internal states such as `missing`, `unknown`, `incomplete`, `invalid`, and `stale`;
- `gpgpu run` still executes adapters even when cache status is `hit`.

Non-goals:

- no cache skipping;
- no tool-version validation;
- no full artifact specs;
- no artifact injection;
- no hardware/action/service/check cache semantics.

Expected evidence:

- old metadata without validation hashes becomes `unknown`/miss;
- matching output and input hashes produce a validated hit;
- missing output files become `incomplete`/miss;
- changed output hashes become `invalid`/miss;
- changed input hashes become `stale`/miss;
- dependency identity mismatches become `stale`/miss;
- adapter-written metadata includes `output_hashes` and `input_hashes`;
- planner, artifact, executor, cleaner, legacy characterization, and full discovery tests pass.

## Completed reevaluation milestone

### Milestone 19: current build-system/control-plane reevaluation

Objective: pause feature work and document the current state of the control-plane implementation, remaining original mission goals, source-file responsibilities, data structures, execution flow, and transitional/not-clean code.

Deliverable:

```text
docs/migration/CURRENT_STATE.md
```

Scope:

- count current registered goals, public/internal split, goal kinds, and adapter coverage;
- map original mission capabilities to current implementation status;
- explain every current non-test control-plane source file and the software Makefile backend;
- document current `list`, `plan`, `explain`, `run`, and `clean` flows;
- inventory transitional and unclean code paths;
- recommend cleanup/refactor milestones before deeper hardware/check/demo work.

Non-goals:

- no new adapters;
- no cache skipping;
- no Vivado/UART/demo/check implementation;
- no legacy script deletion;
- no behavioral refactor.

Expected evidence:

- report is based on current source files and goal registry, not tests;
- `gpgpu list --internal` and representative `plan` commands still work;
- full test discovery passes because documentation-only changes should not alter behavior.

## Completed source-of-truth cleanup milestone

### Milestone 20: schema-driven selection and CLI root consistency

Objective: clean up source-of-truth behavior without adding convenience-only files or patchy selector hardcoding.

Scope:

- `SettingSpec` declares optional `manifest_dir` metadata for settings that select component manifests;
- config resolution applies CLI overrides for manifest-selecting settings before selected manifests, then reapplies all CLI overrides at final precedence;
- CLI computes repo root once through the existing resolver and passes it into planner, executor, and cleaner;
- obsolete direct `Executor.run()` is removed so graph execution through `run_plan()` is the only executor run path.

Non-goals:

- no new goals;
- no new adapters;
- no cache skipping;
- no new repo-root helper file;
- no artifact-spec refactor;
- no command/tool fingerprinting.

Expected evidence:

- tests prove selector behavior is declared in schema, not a hardcoded key set;
- `--set program=nbody` loads `programs/nbody.toml` defaults;
- `--set program=nbody --set program.optimization=O3` keeps final CLI precedence;
- CLI `plan` from outside the repo still reports cache paths under the repo root;
- executor structure tests prove `run_plan()` is the only public run API;
- full test discovery passes.

### Milestone 21: declarative schema, goals, and artifact specs

Objective: move substantial control-plane definitions out of Python source and into declarative project data.

Scope:

- `config/gpgpu/schema.toml` declares settings, types, defaults, scopes, enum choices, and manifest selectors;
- `config/gpgpu/goals.toml` declares goals, params, visibility, dependencies, notes, and artifact input/output specs;
- `tools/gpgpu/config.py` loads and validates schema TOML instead of owning a hardcoded schema table;
- `tools/gpgpu/goals.py` loads and validates goal TOML instead of owning a hardcoded goal table;
- `tools/gpgpu/artifacts.py` resolves declarative input/output specs and compares current expected input/output sets against metadata;
- `Executor._input_paths_for()` is removed;
- `sw.program.image` expected outputs now match current adapter reality: instruction-memory image plus objdump artifact.

Non-goals:

- no new executable goals or adapters;
- no cache skipping;
- no artifact injection;
- no tool-version/command fingerprints;
- no Makefile flag plumbing;
- no legacy script deletion.

Expected evidence:

- RED tests first for missing declarative files/loaders/specs and stale source-embedded tables;
- invalid schema/goal fixture tests reject enum-without-choices, unknown schema fields, unknown dependency goals, unknown params, absolute artifact paths, and unknown placeholders;
- adding a new matching source file changes the expected input set and makes old metadata stale;
- full test discovery passes;
- smoke run/plan/explain/clean cycle still works.

### Milestone 22: strict typed artifact output contracts

Objective: tighten the artifact interface before cache skipping by making declared outputs role-addressable and enforcing that successful adapters actually produce them.

Scope:

- keep the output data model intentionally small: role, path, and type;
- declare software artifact outputs in `config/gpgpu/goals.toml` as typed output tables;
- record produced outputs in `artifact.toml` under `[produced.<role>]` with path and type;
- validate output role/path/type declarations during cache-status checks;
- require declared outputs to exist after adapter success before a run is recorded as successful;
- pass dependency outputs to adapters by dependency role and output role;
- update `sw.program.image` to consume the declared ELF dependency output rather than scanning paths by suffix.

Non-goals:

- no cache skipping;
- no artifact injection;
- no artifact type registry;
- no extra compatibility metadata beyond role/path/type;
- no Makefile flag plumbing;
- no new executable goals or adapters;
- no legacy script deletion.

Expected evidence:

- tests cover typed output declaration loading and invalid output specs;
- tests cover `artifact.toml` output metadata shape;
- tests cover cache miss/stale behavior for output declaration drift;
- tests cover adapter-success-with-missing-output failure;
- tests cover dependency output lookup by dependency role/output role;
- structure tests prevent suffix-based dependency artifact lookup in software adapters;
- full test discovery passes;
- smoke run/plan/clean cycle still works.

### Milestone 23: production goal-instance parameter model

Objective: replace artifact-only goal parameter terminology with one production-shaped `params` field used by every goal kind.

Scope:

- rename declarative goal fields from `artifact_params`/`runtime_params` to `params`;
- remove the old fields rather than keeping compatibility aliases;
- simplify `GoalDefinition` to one `params` tuple;
- make the planner instantiate every goal kind from `definition.params`;
- keep artifact identity behavior unchanged for artifact goals;
- make check/action/service plan output include declared normalized params;
- keep cache status limited to artifact goals.

Non-goals:

- no cache skipping;
- no new adapters;
- no check-result artifact store;
- no hardware-state probing;
- no new setting scopes;
- no legacy script deletion.

Expected evidence:

- tests prove `config/gpgpu/goals.toml` no longer contains `artifact_params` or `runtime_params`;
- tests prove `test.program` includes `program`, `architecture`, and `program.optimization` in its planned instance;
- tests prove action/service params still appear in planned instances;
- tests prove non-artifact goals still do not show compact cache status;
- full test discovery passes;
- smoke plan commands show the new parameter model.

## Dependency execution policy

Dependencies are declared in `config/gpgpu/goals.toml` and loaded into typed `GoalDefinition.dependencies` records by `tools/gpgpu/goals.py`. The planner resolves those declarations using equality-only conditions and then builds dependency graphs for `list`, `plan`, `explain`, and `run`.

`gpgpu run <goal>` executes registered adapters in the plan's topological order. Public goals, check goals, action goals, and service goals without adapters fail during preflight before any dependency adapter runs. Internal placeholder goals should not be added unless they represent a real artifact boundary; `sw.program.compile_riscv` was removed because `sw.program.elf` is the current compile/link artifact boundary.

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
- once artifacts live under `out/artifacts/<goal>/<identity>/`, clean can safely remove that directory.

Near-term implementation should keep using targeted test cleanup only. Do not expand `clean` beyond owned artifact directories until lifecycle cleanup and artifact specs are explicit.

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

Long-term direction: executor should walk a validated planned graph in dependency order, cache-skip only compatible artifact goals after a dedicated cache-execution milestone, never cache-skip action goals, and manage service lifecycles explicitly.

## Future `config.py` direction

`config.py` currently owns schema loading/validation, TOML loading, precedence resolution, type coercion, provenance tracking, and selected-manifest loading. The setting definitions themselves live in `config/gpgpu/schema.toml`.

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

After Milestone 23, remaining cleanup should continue toward final cache-safe goals:

1. Command/tool fingerprints: record Make command shape and compiler/objdump identities, still reporting-only unless cache skipping is explicitly approved.
2. Cache execution policy: define and test when artifact goals may be skipped, while action/check/service goals remain explicit.
3. Then resume new adapters: `test.program`, `test.rtl`, UART/board actions, demo services, and Vivado/Zynq bitstream goals in small characterization-backed milestones.

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
