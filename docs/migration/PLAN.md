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

## Current implementation scope

### Milestone 2: file-backed manifests and local CLI wrapper

Objective: move selected entities, profiles, and machine-local defaults out of `tools/gpgpu/config.py` into repo-owned TOML files while preserving current planner behavior.

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

Commit policy: make and verify the changes, then stop with an uncommitted diff for approval before committing.

## Intended next milestones

1. Review and commit Milestone 2 if approved.
2. Add planner output details: expected outputs, side effects, service lifecycle, and omitted conditional dependencies.
3. Add characterization tests for legacy help and dry-run behavior.
4. Add compatibility wrapper for one small non-hardware workflow.
5. Connect program/toolchain goals behind adapters only after characterization.
6. Connect RTL test goals behind adapters only after characterization.
7. Connect UART/board action goals behind explicit hardware-state policies.
8. Connect Vivado/Zynq bitstream goals after a reproducible flow is specified.

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
