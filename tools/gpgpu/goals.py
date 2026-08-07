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
    expected_outputs: tuple[str, ...] = ()
    side_effects: tuple[str, ...] = ()

    @property
    def cacheable(self) -> bool:
        return self.kind == "artifact"


GOALS: dict[str, GoalDefinition] = {
    "sw.program.native": GoalDefinition(
        goal_id="sw.program.native",
        kind="artifact",
        public=True,
        description="Build a native reference executable for a selected program.",
        artifact_params=("program", "program.optimization"),
        expected_outputs=("native reference executable artifact",),
    ),
    "sw.program.elf": GoalDefinition(
        goal_id="sw.program.elf",
        kind="artifact",
        public=True,
        description="Build a RISC-V ELF for the selected GPGPU program.",
        artifact_params=("program", "architecture", "program.optimization", "program.march", "program.mabi"),
        expected_outputs=("RISC-V ELF artifact",),
    ),
    "sw.program.image": GoalDefinition(
        goal_id="sw.program.image",
        kind="artifact",
        public=True,
        description="Build an instruction-memory image for the selected program.",
        artifact_params=("program", "architecture", "program.optimization", "program.march", "program.mabi"),
        expected_outputs=("instruction-memory image artifact", "data-memory image artifact"),
    ),
    "sw.program.compile_riscv": GoalDefinition(
        goal_id="sw.program.compile_riscv",
        kind="artifact",
        public=False,
        description="Internal RISC-V compiler invocation.",
        artifact_params=("program", "architecture", "program.optimization", "program.march", "program.mabi"),
        expected_outputs=("RISC-V compiler invocation artifact",),
    ),
    "hw.board.project": GoalDefinition(
        goal_id="hw.board.project",
        kind="artifact",
        public=False,
        description="Internal mock Vivado project artifact.",
        artifact_params=("architecture", "board_type", "rtl.sp_per_sm", "rtl.imem_words", "rtl.dmem_words", "fpga.part"),
        expected_outputs=("board project artifact",),
    ),
    "hw.board.bitstream": GoalDefinition(
        goal_id="hw.board.bitstream",
        kind="artifact",
        public=True,
        description="Build a programmable-logic bitstream.",
        artifact_params=("architecture", "board_type", "rtl.sp_per_sm", "rtl.imem_words", "rtl.dmem_words", "fpga.part", "fpga.synth.strategy"),
        expected_outputs=("bitstream artifact",),
    ),
    "hw.board.program": GoalDefinition(
        goal_id="hw.board.program",
        kind="action",
        public=True,
        description="Configure the selected board with a compatible bitstream.",
        runtime_params=("board", "board.configure_policy", "board.port"),
        side_effects=("configure selected board FPGA fabric",),
    ),
    "hw.board.kernel.load": GoalDefinition(
        goal_id="hw.board.kernel.load",
        kind="action",
        public=True,
        description="Load a GPGPU program image and initial data into hardware.",
        runtime_params=("board", "kernel.load_policy", "uart.baud"),
        side_effects=("load selected program image into board memory",),
    ),
    "hw.board.kernel.run": GoalDefinition(
        goal_id="hw.board.kernel.run",
        kind="action",
        public=True,
        description="Run a loaded GPGPU kernel through the current transport.",
        runtime_params=("board", "kernel.kernel_calls"),
        side_effects=("run loaded kernel on selected board",),
    ),
    "demo.run": GoalDefinition(
        goal_id="demo.run",
        kind="service",
        public=True,
        description="Run the selected interactive demo service.",
        runtime_params=("demo", "backend", "demo.fps", "demo.dataset", "demo.steps_per_frame", "demo.http_host", "demo.http_port"),
        lifecycle="long-running",
        side_effects=("start selected interactive demo service",),
    ),
    "test.rtl": GoalDefinition(
        goal_id="test.rtl",
        kind="check",
        public=True,
        description="Run the RTL simulation test suite.",
        artifact_params=("architecture", "rtl.sp_per_sm", "rtl.imem_words", "rtl.dmem_words"),
        expected_outputs=("RTL check result",),
    ),
    "test.program": GoalDefinition(
        goal_id="test.program",
        kind="check",
        public=True,
        description="Compare a native program run against generated program artifacts.",
        artifact_params=("program", "architecture", "program.optimization"),
        expected_outputs=("program comparison check result",),
    ),
    "hw.rtl.assemble": GoalDefinition(
        goal_id="hw.rtl.assemble",
        kind="artifact",
        public=False,
        description="Internal assembly fixture generation.",
        artifact_params=("architecture", "rtl.imem_words", "rtl.dmem_words"),
        expected_outputs=("RTL assembly fixture artifact",),
    ),
    "hw.rtl.sim_executable": GoalDefinition(
        goal_id="hw.rtl.sim_executable",
        kind="artifact",
        public=False,
        description="Internal Icarus simulation executable.",
        artifact_params=("architecture", "rtl.sp_per_sm", "rtl.imem_words", "rtl.dmem_words"),
        expected_outputs=("RTL simulation executable artifact",),
    ),
}
