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

## Current implementation scope

### Milestone 9: RISC-V ELF compatibility adapter

Objective: add the next narrow `gpgpu run` compatibility adapter for the existing RISC-V ELF build artifact.

Scope:

- support `tools/gpgpu/gpgpu run sw.program.elf --set program=<program>`;
- delegate to `make -C sw/programs PROG=<program> <program>/<program>.elf`;
- verify the legacy ELF artifact at `sw/programs/<program>/<program>.elf`;
- keep `sw.program.image` and hardware/demo goals unsupported by the executor;
- document the current config/Makefile mismatch for `program.optimization`, `program.march`, and `program.mabi`.

Non-goals:

- no Makefile rewrite;
- no ELF/MAP relocation into `out/` yet;
- no instruction-memory image adapter yet;
- no UART, hardware, Vivado, or demo execution;
- no caching or artifact injection.

Expected evidence:

- ELF adapter reports the exact legacy Make command;
- ELF adapter produces `sw/programs/nbody/nbody.elf`;
- unsupported `sw.program.image` still fails clearly;
- native adapter behavior is unchanged;
- planner, executor, legacy characterization, and full discovery tests pass.

## Future `executor.py` direction

The executor should stay small while adapters are few, but it must not grow into a long unstructured `if goal_id == ...` chain.

Near-term direction:

- keep `executor.py` as a thin coordinator;
- introduce a tiny adapter registry when the next few adapters accumulate;
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

`executor.py` should own generic execution concerns: adapter lookup, repository root, subprocess execution, stdout/stderr capture, result formatting, error handling, and later dry-run/force/verbosity/service lifecycle behavior.

Domain adapter modules should own command construction and artifact verification for their area.

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

1. Complete Milestone 9 RISC-V ELF adapter.
2. Add `sw.program.image` compatibility adapter after characterizing generated assembly and memory-image artifacts.
3. Decide when generated program artifacts begin moving from `sw/programs/*` into `out/`.
4. Connect RTL test goals behind adapters only after characterization.
5. Connect UART/board action goals behind explicit hardware-state policies.
6. Connect Vivado/Zynq bitstream goals after a reproducible flow is specified.

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
