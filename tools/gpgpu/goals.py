from __future__ import annotations

from dataclasses import dataclass


GoalKind = str


@dataclass(frozen=True)
class GoalDefinition:
    goal_id: str
    kind: GoalKind
    public: bool
    description: str
    artifact_params: tuple[str, ...] = ()
    runtime_params: tuple[str, ...] = ()
    implementation_version: str = "mock-v1"
    lifecycle: str | None = None

    @property
    def cacheable(self) -> bool:
        return self.kind == "artifact"


GOALS: dict[str, GoalDefinition] = {
    "program.native_exe": GoalDefinition(
        goal_id="program.native_exe",
        kind="artifact",
        public=True,
        description="Build a native reference executable for a selected program.",
        artifact_params=("program", "program.optimization"),
    ),
    "program.elf": GoalDefinition(
        goal_id="program.elf",
        kind="artifact",
        public=True,
        description="Build a RISC-V ELF for the selected GPGPU program.",
        artifact_params=("program", "architecture", "program.optimization", "program.march", "program.mabi"),
    ),
    "program.image": GoalDefinition(
        goal_id="program.image",
        kind="artifact",
        public=True,
        description="Build an instruction-memory image for the selected program.",
        artifact_params=("program", "architecture", "program.optimization", "program.march", "program.mabi"),
    ),
    "program.compile_riscv": GoalDefinition(
        goal_id="program.compile_riscv",
        kind="artifact",
        public=False,
        description="Internal RISC-V compiler invocation.",
        artifact_params=("program", "architecture", "program.optimization", "program.march", "program.mabi"),
    ),
    "fpga.project": GoalDefinition(
        goal_id="fpga.project",
        kind="artifact",
        public=False,
        description="Internal mock Vivado project artifact.",
        artifact_params=("architecture", "platform", "rtl.sp_per_sm", "rtl.imem_words", "rtl.dmem_words", "fpga.part"),
    ),
    "fpga.bitstream": GoalDefinition(
        goal_id="fpga.bitstream",
        kind="artifact",
        public=True,
        description="Build a programmable-logic bitstream.",
        artifact_params=("architecture", "platform", "rtl.sp_per_sm", "rtl.imem_words", "rtl.dmem_words", "fpga.part", "fpga.synth.strategy"),
    ),
    "board.configure": GoalDefinition(
        goal_id="board.configure",
        kind="action",
        public=True,
        description="Configure the selected board with a compatible bitstream.",
        runtime_params=("board", "board.configure_policy", "board.port"),
    ),
    "kernel.load": GoalDefinition(
        goal_id="kernel.load",
        kind="action",
        public=True,
        description="Load a GPGPU program image and initial data into hardware.",
        runtime_params=("board", "kernel.load_policy", "uart.baud"),
    ),
    "kernel.run": GoalDefinition(
        goal_id="kernel.run",
        kind="action",
        public=True,
        description="Run a loaded GPGPU kernel through the current transport.",
        runtime_params=("board", "kernel.kernel_calls"),
    ),
    "demo.run": GoalDefinition(
        goal_id="demo.run",
        kind="service",
        public=True,
        description="Run the selected interactive demo service.",
        runtime_params=("demo", "backend", "demo.fps", "demo.dataset", "demo.steps_per_frame", "demo.http_host", "demo.http_port"),
        lifecycle="long-running",
    ),
    "test.rtl": GoalDefinition(
        goal_id="test.rtl",
        kind="check",
        public=True,
        description="Run the RTL simulation test suite.",
        artifact_params=("architecture", "rtl.sp_per_sm", "rtl.imem_words", "rtl.dmem_words"),
    ),
    "test.program": GoalDefinition(
        goal_id="test.program",
        kind="check",
        public=True,
        description="Compare a native program run against generated program artifacts.",
        artifact_params=("program", "architecture", "program.optimization"),
    ),
    "rtl.assemble": GoalDefinition(
        goal_id="rtl.assemble",
        kind="artifact",
        public=False,
        description="Internal assembly fixture generation.",
        artifact_params=("architecture", "rtl.imem_words", "rtl.dmem_words"),
    ),
    "rtl.sim_executable": GoalDefinition(
        goal_id="rtl.sim_executable",
        kind="artifact",
        public=False,
        description="Internal Icarus simulation executable.",
        artifact_params=("architecture", "rtl.sp_per_sm", "rtl.imem_words", "rtl.dmem_words"),
    ),
}
