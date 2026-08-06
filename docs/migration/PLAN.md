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

## Current uncommitted follow-up scope

- Rename initial goal identifiers to accepted hierarchical names.
- Create migration records under `docs/migration/`.
- Do not commit until approval.

## Intended next milestones

1. Review and commit naming/docs follow-up if approved.
2. Add a real console-script entry point for `gpgpu` without changing legacy scripts.
3. Move mock profile/manifests from code to documented file-backed manifests.
4. Add planner output details: expected outputs, side effects, service lifecycle, and omitted conditional dependencies.
5. Add characterization tests for legacy help and dry-run behavior.
6. Add compatibility wrapper for one small non-hardware workflow.
7. Connect program/toolchain goals behind adapters only after characterization.
8. Connect RTL test goals behind adapters only after characterization.
9. Connect UART/board action goals behind explicit hardware-state policies.
10. Connect Vivado/Zynq bitstream goals after a reproducible flow is specified.

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
