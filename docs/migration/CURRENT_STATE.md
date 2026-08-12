# Current Control-Plane State — Milestone 22

This document reevaluates the current `gpgpu` control-plane implementation after Milestone 22. It intentionally analyzes the implementation source files and migration records, not the test suite.

## Baseline and branch context

- Authoritative upstream baseline remains `7c5c12f20e7151773c2c8d72842d43f064244a9d`.
- Current branch: `gpgpu-planner-foundation`.
- Current implementation contains a real control-plane foundation plus narrow software compatibility adapters.
- Existing legacy scripts remain behavioral references and compatibility surfaces unless explicitly retired.

## Executive summary

The repository now has a working typed goal planner, config resolver, graph executor, progress reporters, artifact layout/metadata helpers, conservative artifact cleaner, validated cache-status reporting, declarative goal/artifact specs, strict typed artifact output contracts, and a generated software ABI artifact. Executable adapters currently cover `sw.abi` plus the software-program artifact adapters around the existing `sw/programs/Makefile`.

The foundation is useful, but it is not yet a complete build system for the original project mission. Most hardware, RTL, check, demo, UART, Vivado, and visualization workflows remain planned-only.

Most important cleanup findings after Milestone 23:

1. Dependency identities are still recorded in metadata by goal id, which will not handle multiple instances of the same goal.
2. `implementation_version = "mock-v1"` is still the default for artifact identity, even for real software adapters.
3. Configuration schema now lives in nested `config/schema.yaml`; Python loads, flattens, and validates it into canonical dotted setting IDs.
4. Goal/dependency/artifact definitions now live in nested `config/goals.yaml`; Python loads, flattens, and validates them into canonical dotted goal IDs.
5. Artifact cache validation now compares current declarative input/output specs against recorded metadata, so newly added matching source files invalidate old artifacts.
6. CLI selection settings are schema-declared manifest selectors and CLI passes one repo root into planner, executor, and cleaner.
7. Software adapters now fail if `make` returns success but a declared output is missing.
8. Dependency artifacts are now consumed by dependency goal id and output role, not filename suffix scans.
9. Goal definitions now use one production-shaped `params` field for every goal kind; check/action/service parameters are planned deterministically without artifact-only naming.
10. Some migration docs still mix historical and current status; `CURRENT_STATE.md` remains the current branch map.

## Current goal coverage

The registered goal graph currently contains:

```text
14 total goals
10 public goals
4 internal goals
```

By kind:

```text
artifact: 8
action:   3
service:  1
check:    2
```

Executable adapters currently exist for only:

```text
sw.abi
sw.program.native
sw.program.elf
sw.program.image
```

That means:

```text
4 / 14 registered goals have execution adapters
10 / 14 registered goals are planner-only or unsupported by `gpgpu run`
```

### Goal matrix

| Goal | Kind | Visibility | Adapter | Current status |
|---|---:|---:|---:|---|
| `sw.abi` | artifact | internal | yes | Generates `gpgpu_runtime.h`, `gpgpu.ld`, and `gpgpu_abi.json` from the selected architecture ABI settings. |
| `sw.program.native` | artifact | public | yes | Builds native executable through `sw/programs/Makefile`. |
| `sw.program.elf` | artifact | public | yes | Builds RISC-V ELF/map through `sw/programs/Makefile`, consuming generated ABI header/linker artifacts from `sw.abi`. |
| `sw.program.image` | artifact | public | yes | Builds instruction-memory image/dump through `sw/programs/Makefile`; consumes the planned ELF artifact. |
| `hw.board.project` | artifact | internal | no | Planner-only mock Vivado-project placeholder. |
| `hw.board.bitstream` | artifact | public | no | Planner-only bitstream artifact goal. |
| `hw.board.program` | action | public | no | Planner-only board-configuration action. |
| `hw.board.kernel.load` | action | public | no | Planner-only UART/kernel-load action. |
| `hw.board.kernel.run` | action | public | no | Planner-only kernel-run action. |
| `demo.run` | service | public | no | Planner-only service goal with conditional fake/FPGA dependencies. |
| `test.rtl` | check | public | no | Planner-only RTL check. |
| `test.program` | check | public | no | Planner-only program comparison check. |
| `hw.rtl.assemble` | artifact | internal | no | Planner-only RTL assembly fixture artifact. |
| `hw.rtl.sim_executable` | artifact | internal | no | Planner-only simulator executable artifact. |

## Original mission coverage

| Original capability | Current status |
|---|---|
| RTL builds | Not implemented. Internal support goals exist only as planner nodes. |
| RTL simulation and verification | Planned as `test.rtl`; no adapter. |
| RISC-V program compilation | Partially implemented as `sw.program.elf`. |
| Native reference-program execution | Native executable build exists; no native run/check goal yet. |
| FPGA project generation | Planned as `hw.board.project`; no Vivado adapter. |
| FPGA bitstream generation | Planned as `hw.board.bitstream`; no adapter. |
| Zynq-7000 integration | Config/manifests only; no execution path. |
| FPGA configuration | Planned as `hw.board.program`; no adapter. |
| GPGPU instruction/data-memory loading | Planned as `hw.board.kernel.load`; no adapter. |
| Kernel execution | Planned as `hw.board.kernel.run`; no adapter. |
| UART communication | Legacy scripts characterized; not wrapped by `gpgpu` yet. |
| Interactive demos | Planned as `demo.run`; no service adapter. |
| Visualization/result reporting | Legacy scripts exist; no control-plane adapter. |
| `gpgpu list` | Implemented. |
| `gpgpu plan` | Implemented. |
| `gpgpu explain` | Implemented. |
| `gpgpu run` | Implemented for `sw.abi` plus three software program artifact adapters. |
| `gpgpu clean` | Implemented for owned artifact directories only. |
| Artifact metadata | Implemented as `artifact.toml`. |
| Cache status | Implemented as validated reporting. |
| Cache skipping | Implemented for validated artifact `hit` only; every other artifact state executes. |
| Artifact injection | Not implemented. |

## Source-file responsibility map

### `tools/gpgpu/goals.py`

Responsibilities:

- Defines goal-related dataclasses:
  - `GoalDependency`
  - `GoalNote`
  - `GoalDefinition`
- Loads the central `GOALS` registry from nested `config/goals.yaml`.
- Records goal kind, visibility, description, param names, implementation version, lifecycle, artifact input/output specs, side effects, declarative dependencies, and conditional notes.

Justification:

- This is the correct home for semantic build-system topology.
- It replaced planner hardcoding for dependencies in Milestone 15.
- It gives `list`, `plan`, `explain`, `run`, and `clean` a shared vocabulary.

Current issues:

- `implementation_version` defaults to `"mock-v1"`, which is stale for real software adapters.
- `hw.board.project` is still explicitly mock-only.
- `sw.program.image` now declares current adapter reality: instruction-memory image plus objdump artifact, not a fake data-memory artifact.
- Artifact outputs use a minimal typed contract: role, path template, and semantic type string.
- All goal kinds declare one `params` tuple for normalized goal-instance parameters; artifact-only `artifact_params` and action/service-only `runtime_params` fields are no longer part of the goal schema.

### `tools/gpgpu/config.py`

Responsibilities:

- Defines typed settings, defaults, enum choices, and manifest selectors using `SettingSpec` loaded from nested `config/schema.yaml`.
- Resolves config from schema defaults, defaults YAML, selected manifests, profiles, local config, tool defaults, and CLI `--set`.
- Preserves provenance through `Provenance` and `ResolvedConfig`.
- Rejects unknown settings and type-invalid settings.

Justification:

- Centralized typed config with provenance is required for deterministic planning and `gpgpu explain`.
- The current precedence order follows the approved initial model.

Current issues:

- `ConfigResolver` owns schema loading, nested YAML flattening, coercion, precedence, and provenance.
- CLI selection settings declare `manifest_dir` in `SettingSpec`; selection overrides are applied before selected manifests and all CLI overrides are applied again at final precedence.
- Config values such as `program.optimization`, `program.march`, and `program.mabi` affect identities, but the Makefile backend still hardcodes corresponding compiler flags. ABI header/linker selection is now wired through generated `sw.abi` artifacts.

### `tools/gpgpu/planner.py`

Responsibilities:

- Defines planning dataclasses:
  - `PlanNote`
  - `GoalInstance`
  - `Plan`
- Recursively instantiates dependencies from the `GOALS` registry.
- Deduplicates identical goal instances.
- Computes artifact identities.
- Attaches artifact cache status.
- Formats `plan` and `explain` output.

Current flow:

1. `Planner.plan(goal_id)` validates the root goal.
2. `_require()` recursively instantiates dependency goals.
3. `_params_for()` selects normalized params for each instance.
4. `_identity_for()` hashes goal id, implementation version, params, and dependency identities for artifacts.
5. Artifact instances receive `ArtifactStatus` from `read_artifact_status()`.
6. `_topological()` returns dependency-before-dependent order.

Justification:

- This is the main build graph engine.
- It is intentionally deterministic and side-effect-free.

Current issues:

- Non-artifact identities are generic strings such as `"service"` or `"check"`, which is weak for future reporting/traceability.
- CLI passes a shared repo root into the planner so CLI cache paths match run/clean roots; direct `Planner(...)` default still uses `Path.cwd()` for non-CLI use.
- Artifact identity still does not include tool versions or generated config hashes.

### `tools/gpgpu/artifacts.py`

Responsibilities:

- Owns artifact root layout:
  - `out/artifacts/<goal>/<identity>/`
- Computes artifact directories.
- Reads validated artifact status.
- Writes `artifact.toml` metadata.
- Computes SHA-256 hashes for produced outputs and recorded inputs.

Main data structure:

- `ArtifactStatus(state, path, reason)`

Status semantics:

- `hit`: metadata and validation checks pass.
- `missing`: directory or metadata absent.
- `unknown`: metadata lacks validation hashes.
- `incomplete`: expected produced output missing.
- `invalid`: malformed/mismatching metadata or output hash mismatch.
- `stale`: recorded input/dependency changed.
- `not-artifact`: non-artifact goal.

Justification:

- Artifact path and metadata policy must be centralized so executor, cleaner, planner, and future artifact injection do not diverge.

Current issues:

- Validation now compares recorded input/output metadata against current declarative artifact specs before checking hashes.
- `_dependency_identities(node)` uses a hidden `GoalInstance` attribute contract.
- Metadata dependency identities are keyed by dependency goal id, matching the current role-less dependency model.
- `write_artifact_metadata()` can infer repo root from `directory.parents[3]` if none is passed; this fallback is brittle.

### `tools/gpgpu/executor.py`

Responsibilities:

- Defines execution dataclasses:
  - `RunResult`
  - `ExecutionContext`
  - `RunRecord`
  - `RunSummary`
- Preflights a plan against the adapter registry.
- Runs executable nodes in topological order.
- Skips artifact adapters when cache status is a validated `hit`.
- Skips internal planner-only artifact nodes with no adapter.
- Stops dependents after a failure.
- Passes dependency artifacts to adapters.
- Writes artifact metadata after successful artifact goals.
- Emits reporter events.

Justification:

- Keeps graph execution separate from domain-specific adapter commands.
- Provides one central side-effect boundary for `gpgpu run`.

Current issues:

- Artifact input selection is now delegated to declarative specs through `resolve_artifact_inputs()`.
- `format_run_result()` and `format_run_summary()` overlap with `reporter.py` and may be legacy debug helpers.
- Adapter success now requires all declared produced files to exist.
- Direct dependency outputs are passed by dependency goal id and output role.
- Cache-hit artifact outputs are passed to dependents without re-running the producer adapter.
- Direct dependency identities are recorded in metadata by dependency goal id.

### `tools/gpgpu/adapters/sw_programs.py`

Responsibilities:

- Implements software artifact compatibility adapters:
  - `run_native()`
  - `run_elf()`
  - `run_image()`
- Invokes `make -C sw/programs` with `PROG`, `OUT_DIR`, optional `ELF_IN`, and a named target.
- Converts process output and declared produced artifacts into `RunResult`.

Current commands:

```bash
make -C sw/programs PROG=<program> OUT_DIR=<artifact-dir> native
make -C sw/programs PROG=<program> OUT_DIR=<artifact-dir> elf
make -C sw/programs PROG=<program> OUT_DIR=<artifact-dir> ELF_IN=<elf-artifact> image
```

Justification:

- This preserves existing Makefile behavior instead of reimplementing compiler/linker/objdump details prematurely.
- `sw.program.image` now consumes the planned `sw.program.elf` artifact instead of rebuilding ELF inside the image artifact directory.

Current issues:

- Planner config flags are not passed to Makefile flags.

### `tools/gpgpu/adapters/__init__.py`

Responsibilities:

- Registers current adapters in `ADAPTERS`.

Justification:

- Keeps executor independent from domain adapter imports until runtime.

Current issues:

- None urgent. The registry will need domain growth as hardware/check/demo adapters are added.

### `tools/gpgpu/adapters/types.py`

Responsibilities:

- Defines `Adapter = Callable[[ExecutionContext], RunResult]`.

Justification:

- Simple shared type alias.

Current issues:

- None urgent.

### `tools/gpgpu/cleaner.py`

Responsibilities:

- Deletes exact owned artifact directories for a planned artifact goal.
- Supports root-only clean and dependency clean.
- Refuses broad paths, outside paths, and symlink artifact paths.
- Formats clean summaries.

Justification:

- Keeps cleaning scoped and avoids broad `make clean` side effects.

Current issues:

- Only artifact cleanup exists, which is correct for now.
- `--deps` selects all artifact nodes, including internal planner-only artifacts. This is safe now but should be reevaluated when internal artifacts are real.

### `tools/gpgpu/reporter.py`

Responsibilities:

- Defines the run-progress event sink interface.
- Implements deterministic `PlainRunReporter`.
- Implements TTY-oriented `InteractiveRunReporter`.

Justification:

- Keeps presentation separate from executor behavior.
- Supports Docker-like output while preserving deterministic CI output.

Current issues:

- Uses `Any` instead of explicit protocols/types.
- Does not stream subprocess output live.
- Interactive presentation can still be refined, but it is not architecturally blocking.

### `tools/gpgpu/cli.py`

Responsibilities:

- Defines the `gpgpu` CLI surface:
  - `list`
  - `plan`
  - `explain`
  - `run`
  - `clean`
- Resolves config.
- Dispatches to planner, executor, reporter, and cleaner.
- Handles color and error formatting.

Justification:

- Thin top-level command dispatcher.

Current issues:

- `Planner(config)` does not receive the same explicit repo root as executor/cleaner.
- `list` resolves config even though listing does not need it.
- No convenience aliases/flags beyond `--set` yet.

### `tools/gpgpu/__main__.py`

Responsibilities:

- Runs `cli.main()` for `python -m tools.gpgpu`.

Current issues:

- None.

### `tools/gpgpu/__init__.py`

Responsibilities:

- Package marker and version string.

Current issues:

- `__version__ = "0.1.0"` is package metadata only and should not be confused with goal implementation versions.

### `sw/programs/Makefile`

Responsibilities:

- Compatibility backend for current software artifacts.
- Supports `OUT_DIR` and named targets:
  - `native`
  - `elf`
  - `image`
- Supports `ELF_IN` so `sw.program.image` can consume the planned ELF artifact.

Justification:

- Preserves existing workflow behavior while moving generated outputs into `out/artifacts`.

Current issues:

- Hardcodes native and RISC-V compiler flags.
- Does not consume planner config values for optimization/march/mabi.
- `image` produces instruction memory and dump output, not a full typed program image/data-memory artifact set.

## Current end-to-end flows

### `gpgpu list`

```text
CLI -> Planner.list_goals() -> format_goal_list()
```

Shows public goals by default and internal goals with `--internal`.

### `gpgpu plan <goal>`

```text
CLI
  -> ConfigResolver.resolve()
  -> Planner.plan(goal)
      -> instantiate dependencies from GOALS
      -> compute normalized params
      -> compute artifact identities
      -> attach cache status for artifact nodes
      -> topologically order graph
  -> Plan.format_plan()
```

### `gpgpu explain <goal>`

```text
gpgpu plan flow
  -> Plan.format_explain()
      -> plan output
      -> artifact identities
      -> configuration provenance
```

### `gpgpu run sw.program.image`

```text
CLI
  -> ConfigResolver.resolve()
  -> Planner.plan("sw.program.image")
      -> sw.program.elf
      -> sw.program.image
  -> Executor.run_plan()
      -> preflight adapters
      -> run sw.program.elf adapter
          -> make -C sw/programs ... elf
          -> write artifact.toml
      -> run sw.program.image adapter
          -> use ELF from sw.program.elf artifact
          -> make -C sw/programs ... image
          -> write artifact.toml with dependency identity
      -> reporter output
```

### `gpgpu clean sw.program.image --deps`

```text
CLI
  -> ConfigResolver.resolve()
  -> Planner.plan("sw.program.image")
  -> Cleaner.clean_plan(deps=True)
      -> select artifact nodes
      -> compute exact artifact dirs
      -> safety-check paths
      -> delete or report missing
```

## Current artifact/cache model

Artifact directory:

```text
out/artifacts/<goal>/<identity>/
```

Artifact metadata:

```text
artifact.toml
```

Current metadata records:

- goal id;
- kind;
- identity;
- cacheable/public flags;
- description;
- normalized params;
- produced files;
- produced output hashes;
- explicit input hashes;
- dependency identities.

Current compact cache rendering:

```text
hit -> CACHE HIT
anything else -> CACHE MISS
```

Current execution policy:

- `gpgpu run` skips artifact goals only when their planner cache status is validated `hit`.
- Every non-hit artifact state (`missing`, `unknown`, `incomplete`, `invalid`, `stale`) is treated as executable miss behavior.
- Action, check, and service goals are never cache-skipped.

## Transitional and not-clean code inventory

### Transitional but now documented

| Location | Issue | Current note |
|---|---|---|
| Artifact specs | Declarative goal-owned specs now live in `config/goals.yaml`, removing executor-side software input selection. | Extend specs with typed produced artifacts and command/tool fingerprints later. |
| `sw.program.*` adapters | Compatibility wrappers over Makefile. | Documented as current compatibility backend. |
| `hw.board.project` | Mock internal Vivado artifact. | Name/description marks mock. Needs replacement before Vivado work. |
| `gpgpu run` cache behavior | Validated artifact hits skip execution. | Non-hit artifact states execute; action/check/service goals are not cache-skipped. |

### Transitional or unclean and needing better documentation/cleanup

| Location | Issue | Why it matters | Recommended cleanup |
|---|---|---|---|
| Metadata dependency identities | Dependency identities are keyed by dependency goal id in `artifact.toml`. | Multiple instances of the same dependency goal are not currently modeled. | Add dependency-local binding/aliases only when a real multi-instance use case exists. |
| `GoalDefinition.implementation_version` | Default `"mock-v1"`. | Real adapters now use mock identity version. | Assign explicit implementation versions per goal/adapter. |
| `artifacts.py` input validation | Validates recorded inputs only. | Newly added inputs may not invalidate old artifacts. | Compare against declarative current input specs. |
| `artifacts.py` dependency metadata | Keyed by dependency goal id. | Cannot represent two instances of same goal. | Keep simple until dependency-local binding/aliases are introduced. |
| `Executor._direct_dependency_identities()` | Keyed by dependency goal id. | Same multi-instance limitation. | Add dependency-local binding/aliases only with a real multi-instance use case. |
| CLI repo-root coordination | CLI computes one repo root via `ConfigResolver` and passes it to planner, executor, and cleaner. | Prevents CLI cache paths from depending on current working directory. | Keep explicit root passing; avoid adding a helper file until path policy grows. |
| Config manifest selection | `SettingSpec.manifest_dir` declares which settings select manifests. | Avoids hardcoded selector-key sets and fixes `--set program=...` manifest defaults. | Extend schema metadata for future manifest-selected settings. |
| `format_run_result()`/`format_run_summary()` | Older formatting alongside reporters. | Duplicate presentation paths. | Keep as debug helpers or remove in a later formatting cleanup. |
| Migration docs status split | Historical milestone records and current branch status are mixed in long docs. | Readers can confuse old milestone facts with current status. | Keep `CURRENT_STATE.md` as the current map and split historical/current sections where needed. |
| Artifact output descriptions | Stored beside each declared output path/type. | Top-level `expected_outputs` was removed from declarative goals. | Keep descriptions local to the output they describe. |
| Makefile flag hardcoding | Planner settings affect identity but not actual command. | Identity can vary while output command does not. | Decide Make variable pass-through vs Python-native backend. |
| Reporter type hints | Uses `Any`. | Less clear contracts. | Use protocols once interfaces settle. |

## Recommended cleanup milestones after this reevaluation

### Milestone 20 — source-of-truth cleanup

Status: partially completed by the schema-driven selection/root cleanup milestone.

Completed:

- CLI repo root is now computed once and passed to planner, executor, and cleaner without adding a new helper file.
- Manifest-selecting settings are declared through `SettingSpec.manifest_dir`, avoiding hardcoded selector-key sets.
- CLI selection overrides such as `--set program=nbody` now load the selected manifest defaults before final CLI precedence.
- The obsolete direct `Executor.run()` API was removed; graph execution through `run_plan()` is the only executor run path.

Remaining cleanup:

- Decide whether `format_run_result()` and `format_run_summary()` remain debug helpers or move/retire later.
- Continue splitting historical/current documentation where it still causes confusion.

### Milestone 21 — declarative artifact specs

Scope:

- Move `_input_paths_for()` out of executor.
- Add declarative input/output specs for current software artifact goals.
- Make validation compare current expected input set with recorded input set.
- Keep cache skipping disabled.

### Milestone 22 — strict adapter output contracts

Scope:

- Make adapters fail if required outputs are missing after a successful command.
- Replace suffix-based dependency artifact lookup with typed produced artifact selection.
- Align `expected_outputs` with actual produced files.

### Milestone 23 — parameter model cleanup for checks/actions/services

Scope:

- Fix check-goal parameter modeling.
- Separate display params, identity-affecting params, runtime params, and executor params more explicitly.
- Prepare `test.program` and `test.rtl` for real adapters.

### Milestone 24 — command/tool fingerprints

Scope:

- Record Make command fingerprints.
- Record compiler/objdump tool identities.
- Still reporting-only unless cache skipping is separately approved.

## Recommended immediate next decision

Before implementing more workflows, approve one of these paths:

1. **Clean foundation first**: Milestones 20–22 before new adapters.
2. **Connect one more workflow first**: implement `test.program` or `test.rtl`, accepting current technical debt temporarily.
3. **Artifact-spec refactor first**: make input/output/dependency contracts declarative before any further run behavior.

Recommendation: choose path 1, because the current foundation is stable enough to document and clean, but not clean enough to safely extend into hardware/check/demo execution without accumulating confusing transitional code.
