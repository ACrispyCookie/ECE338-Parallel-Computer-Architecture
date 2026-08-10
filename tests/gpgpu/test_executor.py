from __future__ import annotations

import contextlib
import io
import os
import shutil
import sys
import tomllib
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from tools.gpgpu.cli import main
from tools.gpgpu.config import ConfigResolver
from tools.gpgpu.executor import Executor, RunResult, format_run_summary
from tools.gpgpu.planner import Planner
from tools.gpgpu.reporter import InteractiveRunReporter, PlainRunReporter


class ExecutorStructureTests(unittest.TestCase):
    def test_program_adapters_are_registered_by_goal_id(self):
        from tools.gpgpu.adapters import ADAPTERS

        self.assertIn("sw.program.native", ADAPTERS)
        self.assertIn("sw.program.elf", ADAPTERS)
        self.assertIn("sw.program.image", ADAPTERS)
        self.assertNotIn("test.program", ADAPTERS)

    def test_executor_does_not_own_domain_specific_program_methods(self):
        from tools.gpgpu.executor import Executor

        self.assertFalse(hasattr(Executor, "_run_sw_program_native"))
        self.assertFalse(hasattr(Executor, "_run_sw_program_elf"))
        self.assertFalse(hasattr(Executor, "_run_sw_program_image"))

    def test_program_adapters_do_not_own_artifact_layout_policy(self):
        adapter_source = (ROOT / "tools" / "gpgpu" / "adapters" / "sw_programs.py").read_text()

        self.assertNotIn('"out"', adapter_source)
        self.assertNotIn('"artifacts"', adapter_source)
        self.assertNotIn("_artifact_dir", adapter_source)

    def test_artifact_dir_helper_uses_goal_and_identity_without_program_component(self):
        from tools.gpgpu.artifacts import artifact_dir

        config = ConfigResolver().resolve(set_values=["program=nbody"])
        node = Planner(config).plan("sw.program.elf").root

        self.assertEqual(
            artifact_dir(ROOT, node),
            ROOT / "out" / "artifacts" / "sw.program.elf" / node.identity,
        )


class GraphRunTests(unittest.TestCase):
    program = "nbody"

    def config(self):
        return ConfigResolver().resolve(set_values=[f"program={self.program}"])

    def test_run_plan_executes_registered_dependencies_before_root(self):
        config = self.config()
        plan = Planner(config).plan("sw.program.image")
        calls: list[str] = []

        def record(name: str):
            def adapter(context):
                calls.append(context.goal_id)
                return RunResult(
                    goal_id=context.goal_id,
                    command=("fake", name),
                    returncode=0,
                    produced=(context.artifact_dir / f"{name}.artifact",),
                )
            return adapter

        summary = Executor(
            config,
            adapters={
                "sw.program.elf": record("elf"),
                "sw.program.image": record("image"),
            },
        ).run_plan(plan)

        self.assertEqual(calls, ["sw.program.elf", "sw.program.image"])
        self.assertEqual(summary.returncode, 0)
        rendered = format_run_summary(summary, repo_root=ROOT)
        self.assertIn("Run: sw.program.image", rendered)
        self.assertIn("Plan: 2 executable goals, 2 planned goals", rendered)
        self.assertNotIn("SKIPPED", rendered)
        self.assertNotIn("sw.program.compile_riscv", rendered)
        self.assertLess(rendered.index("RUNNING   sw.program.elf"), rendered.index("RUNNING   sw.program.image"))
        self.assertIn("DONE      sw.program.elf", rendered)
        self.assertIn("DONE      sw.program.image", rendered)
        self.assertIn("completed: 2", rendered)
        self.assertIn("skipped:   0", rendered)
        self.assertIn("failed:    0", rendered)

    def test_run_plan_still_executes_when_artifact_metadata_exists(self):
        from tools.gpgpu.artifacts import artifact_dir

        config = self.config()
        initial = Planner(config, repo_root=ROOT).plan("sw.program.native")
        out_dir = artifact_dir(ROOT, initial.root)
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "artifact.toml").write_text(
            f'goal = "sw.program.native"\nidentity = "{initial.root.identity}"\n',
            encoding="utf-8",
        )
        calls: list[str] = []

        def native(context):
            calls.append(context.goal_id)
            return RunResult(goal_id=context.goal_id, command=("fake", "native"), returncode=0, produced=())

        try:
            plan = Planner(config, repo_root=ROOT).plan("sw.program.native")
            self.assertIn("CACHE HIT", plan.format_plan())
            summary = Executor(config, adapters={"sw.program.native": native}).run_plan(plan)
        finally:
            shutil.rmtree(ROOT / "out" / "artifacts" / "sw.program.native", ignore_errors=True)

        self.assertEqual(summary.returncode, 0)
        self.assertEqual(calls, ["sw.program.native"])

    def test_run_summary_supports_colorized_status_output(self):
        config = self.config()
        plan = Planner(config).plan("sw.program.native")

        def native(context):
            return RunResult(goal_id=context.goal_id, command=("fake", "native"), returncode=0, produced=())

        summary = Executor(config, adapters={"sw.program.native": native}).run_plan(plan)
        rendered = format_run_summary(summary, repo_root=ROOT, color=True)

        self.assertIn("\033[", rendered)
        self.assertIn("RUNNING", rendered)
        self.assertIn("DONE", rendered)

    def test_run_plan_stops_after_failed_dependency_and_prints_output(self):
        config = self.config()
        plan = Planner(config).plan("sw.program.image")
        calls: list[str] = []

        def failing_elf(context):
            calls.append(context.goal_id)
            return RunResult(
                goal_id=context.goal_id,
                command=("fake", "elf"),
                returncode=7,
                produced=(),
                stdout="compile stdout",
                stderr="compile stderr",
            )

        def image(context):
            calls.append(context.goal_id)
            return RunResult(goal_id=context.goal_id, command=("fake", "image"), returncode=0, produced=())

        summary = Executor(
            config,
            adapters={"sw.program.elf": failing_elf, "sw.program.image": image},
        ).run_plan(plan)

        self.assertEqual(calls, ["sw.program.elf"])
        self.assertEqual(summary.returncode, 7)
        rendered = format_run_summary(summary, repo_root=ROOT)
        self.assertIn("FAILED    sw.program.elf", rendered)
        self.assertIn("stdout:", rendered)
        self.assertIn("compile stdout", rendered)
        self.assertIn("stderr:", rendered)
        self.assertIn("compile stderr", rendered)
        self.assertIn("STOPPED   sw.program.image", rendered)
        self.assertIn("dependency sw.program.elf failed", rendered)

    def test_missing_required_public_adapter_fails_before_dependencies_run(self):
        config = self.config()
        plan = Planner(config).plan("test.program")
        calls: list[str] = []

        def native(context):
            calls.append(context.goal_id)
            return RunResult(goal_id=context.goal_id, command=("fake", "native"), returncode=0, produced=())

        with self.assertRaisesRegex(Exception, "no executor adapter registered for required goal test.program"):
            Executor(
                config,
                adapters={
                    "sw.program.native": native,
                    "sw.program.elf": native,
                    "sw.program.image": native,
                },
            ).run_plan(plan)

        self.assertEqual(calls, [])

    def test_plain_reporter_prints_compact_completed_goals(self):
        config = self.config()
        plan = Planner(config).plan("sw.program.image")
        stream = io.StringIO()

        def record(name: str):
            def adapter(context):
                return RunResult(
                    goal_id=context.goal_id,
                    command=("fake", name),
                    returncode=0,
                    produced=(context.artifact_dir / f"{name}.artifact",),
                )
            return adapter

        summary = Executor(
            config,
            adapters={"sw.program.elf": record("elf"), "sw.program.image": record("image")},
        ).run_plan(plan, reporter=PlainRunReporter(stream, repo_root=ROOT, color=False))

        rendered = stream.getvalue()
        self.assertEqual(summary.returncode, 0)
        self.assertIn("gpgpu run sw.program.image", rendered)
        self.assertIn("✓ sw.program.elf", rendered)
        self.assertIn("✓ sw.program.image", rendered)
        self.assertNotIn("sw.program.compile_riscv", rendered)
        self.assertIn("Summary: 2 completed, 0 skipped, 0 failed", rendered)
        self.assertNotIn("RUNNING", rendered)
        self.assertNotIn("DONE", rendered)

    def test_interactive_reporter_replaces_spinner_with_completed_goal_area(self):
        config = self.config()
        plan = Planner(config).plan("sw.program.native")
        stream = io.StringIO()

        def native(context):
            return RunResult(
                goal_id=context.goal_id,
                command=("fake", "native"),
                returncode=0,
                produced=(context.artifact_dir / "native.artifact",),
            )

        summary = Executor(config, adapters={"sw.program.native": native}).run_plan(
            plan,
            reporter=InteractiveRunReporter(stream, repo_root=ROOT, color=False),
        )

        rendered = stream.getvalue()
        self.assertEqual(summary.returncode, 0)
        self.assertIn("╭─ [1/1] sw.program.native", rendered)
        self.assertIn("\r\033[2K│  ✓ completed", rendered)
        self.assertIn("│  produced: native.artifact", rendered)
        self.assertIn("╰─ 1 completed, 0 skipped, 0 failed", rendered)
        self.assertNotIn("running fake native\n✓", rendered)

    def test_interactive_reporter_uses_richer_color_for_goal_area(self):
        config = self.config()
        plan = Planner(config).plan("sw.program.native")
        stream = io.StringIO()

        def native(context):
            return RunResult(goal_id=context.goal_id, command=("fake", "native"), returncode=0, produced=())

        Executor(config, adapters={"sw.program.native": native}).run_plan(
            plan,
            reporter=InteractiveRunReporter(stream, repo_root=ROOT, color=True),
        )

        rendered = stream.getvalue()
        self.assertIn("\033[1;36m╭─", rendered)
        self.assertIn("\033[32m✓ completed", rendered)
        self.assertIn("\033[2m", rendered)

    def test_cli_progress_plain_uses_compact_reporter(self):
        stdout = io.StringIO()
        stderr = io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            code = main([
                "--color",
                "never",
                "run",
                "sw.program.native",
                "--progress",
                "plain",
                "--set",
                f"program={self.program}",
            ])

        rendered = stdout.getvalue()
        self.assertEqual(code, 0, stderr.getvalue() + rendered)
        self.assertIn("gpgpu run sw.program.native", rendered)
        self.assertIn("✓ sw.program.native", rendered)
        self.assertIn("Summary: 1 completed, 0 skipped, 0 failed", rendered)
        self.assertNotIn("Run: sw.program.native", rendered)


class ProgramAdapterTests(unittest.TestCase):
    program = "nbody"

    def setUp(self):
        self.program_dir = ROOT / "sw" / "programs" / self.program
        self.native_exe = self.program_dir / f"{self.program}_x86"
        self.elf = self.program_dir / f"{self.program}.elf"
        self.map_file = self.program_dir / f"{self.program}.map"
        self.dump_asm = self.program_dir / f"{self.program}_dump_real.asm"
        self.mem = self.program_dir / f"{self.program}_instructions.mem"
        self.program_asm = self.program_dir / f"{self.program}_program.asm"
        self.program_asm_snapshot = self.program_asm.read_text() if self.program_asm.exists() else None
        self.clean_generated_outputs()

    def tearDown(self):
        self.clean_generated_outputs()
        if self.program_asm_snapshot is not None:
            self.program_asm.write_text(self.program_asm_snapshot)

    def clean_generated_outputs(self):
        self.native_exe.unlink(missing_ok=True)
        self.elf.unlink(missing_ok=True)
        self.map_file.unlink(missing_ok=True)
        self.dump_asm.unlink(missing_ok=True)
        self.mem.unlink(missing_ok=True)
        for goal_id in ("sw.program.native", "sw.program.elf", "sw.program.image"):
            shutil.rmtree(ROOT / "out" / "artifacts" / goal_id, ignore_errors=True)

    def require_native_tools(self):
        if shutil.which("make") is None:
            self.skipTest("make is required for native compatibility adapter test")
        if shutil.which("gcc") is None:
            self.skipTest("gcc is required for native compatibility adapter test")

    def require_riscv_tools(self):
        if shutil.which("make") is None:
            self.skipTest("make is required for RISC-V compatibility adapter test")
        if shutil.which("riscv64-unknown-elf-gcc") is None and shutil.which("riscv-none-elf-gcc") is None:
            self.skipTest("riscv64-unknown-elf-gcc or riscv-none-elf-gcc is required for RISC-V compatibility adapter test")

    def artifact_dir(self, goal_id: str, *set_values: str) -> Path:
        from tools.gpgpu.artifacts import artifact_dir

        config = ConfigResolver().resolve(set_values=[f"program={self.program}", *set_values])
        node = Planner(config).plan(goal_id).root
        return artifact_dir(ROOT, node)

    def metadata(self, out_dir: Path) -> dict:
        with (out_dir / "artifact.toml").open("rb") as handle:
            return tomllib.load(handle)

    def test_unsupported_run_goal_fails_clearly(self):
        stdout = io.StringIO()
        stderr = io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            code = main(["--color", "never", "run", "hw.board.bitstream"])
        self.assertEqual(code, 2)
        self.assertEqual(stdout.getvalue(), "")
        self.assertIn("no executor adapter registered for required goal hw.board.bitstream", stderr.getvalue())

    def test_unimplemented_program_check_still_fails_clearly(self):
        stdout = io.StringIO()
        stderr = io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            code = main(["--color", "never", "run", "test.program", "--set", f"program={self.program}"])
        self.assertEqual(code, 2)
        self.assertEqual(stdout.getvalue(), "")
        self.assertIn("no executor adapter registered for required goal test.program", stderr.getvalue())

    def test_native_adapter_builds_artifact_under_out(self):
        self.require_native_tools()
        out_dir = self.artifact_dir("sw.program.native")
        out_native = out_dir / f"{self.program}_x86"

        stdout = io.StringIO()
        stderr = io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            code = main(["--color", "never", "run", "sw.program.native", "--set", f"program={self.program}"])

        rendered = stdout.getvalue()
        self.assertEqual(code, 0, stderr.getvalue() + rendered)
        self.assertIn("gpgpu run sw.program.native", rendered)
        self.assertIn("[1/1] sw.program.native", rendered)
        self.assertIn("✓ sw.program.native", rendered)
        self.assertIn("produced nbody_x86", rendered)
        self.assertIn(f"out/artifacts/sw.program.native/{out_dir.name}", rendered)
        self.assertNotIn(f"out/artifacts/sw.program.native/{self.program}/{out_dir.name}", rendered)
        self.assertTrue(out_native.exists())
        metadata = self.metadata(out_dir)
        self.assertEqual(metadata["goal"], "sw.program.native")
        self.assertEqual(metadata["identity"], out_dir.name)
        self.assertEqual(metadata["params"]["program"], self.program)
        self.assertEqual(metadata["produced"]["files"], [f"{self.program}_x86"])
        self.assertTrue(os.access(out_native, os.X_OK))
        self.assertFalse(self.native_exe.exists())

    def test_native_adapter_does_not_run_program_or_create_data_csv(self):
        self.require_native_tools()
        data_csv = self.program_dir / "data.csv"
        data_csv.unlink(missing_ok=True)
        try:
            stdout = io.StringIO()
            stderr = io.StringIO()
            with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                code = main(["--color", "never", "run", "sw.program.native", "--set", f"program={self.program}"])
            self.assertEqual(code, 0, stderr.getvalue() + stdout.getvalue())
            self.assertFalse(data_csv.exists())
        finally:
            data_csv.unlink(missing_ok=True)

    def test_elf_adapter_builds_artifacts_under_out(self):
        self.require_riscv_tools()
        out_dir = self.artifact_dir("sw.program.elf")
        out_elf = out_dir / f"{self.program}.elf"
        out_map = out_dir / f"{self.program}.map"

        stdout = io.StringIO()
        stderr = io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            code = main(["--color", "never", "run", "sw.program.elf", "--set", f"program={self.program}"])

        rendered = stdout.getvalue()
        self.assertEqual(code, 0, stderr.getvalue() + rendered)
        self.assertIn("gpgpu run sw.program.elf", rendered)
        self.assertNotIn("sw.program.compile_riscv", rendered)
        self.assertIn("[1/1] sw.program.elf", rendered)
        self.assertIn("✓ sw.program.elf", rendered)
        self.assertIn("produced nbody.elf, nbody.map", rendered)
        self.assertIn(f"out/artifacts/sw.program.elf/{out_dir.name}", rendered)
        self.assertNotIn(f"out/artifacts/sw.program.elf/{self.program}/{out_dir.name}", rendered)
        self.assertTrue(out_elf.exists())
        self.assertTrue(out_map.exists())
        metadata = self.metadata(out_dir)
        self.assertEqual(metadata["goal"], "sw.program.elf")
        self.assertEqual(metadata["identity"], out_dir.name)
        self.assertEqual(metadata["params"]["program"], self.program)
        self.assertEqual(metadata["produced"]["files"], [f"{self.program}.elf", f"{self.program}.map"])
        self.assertFalse(self.elf.exists())
        self.assertFalse(self.map_file.exists())

    def test_image_adapter_builds_artifacts_under_out(self):
        self.require_riscv_tools()
        elf_dir = self.artifact_dir("sw.program.elf")
        out_dir = self.artifact_dir("sw.program.image")
        out_mem = out_dir / f"{self.program}_instructions.mem"
        out_dump = out_dir / f"{self.program}_dump_real.asm"
        out_elf = out_dir / f"{self.program}.elf"
        out_map = out_dir / f"{self.program}.map"

        stdout = io.StringIO()
        stderr = io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            code = main(["--color", "never", "run", "sw.program.image", "--set", f"program={self.program}"])

        rendered = stdout.getvalue()
        self.assertEqual(code, 0, stderr.getvalue() + rendered)
        self.assertIn("gpgpu run sw.program.image", rendered)
        self.assertNotIn("sw.program.compile_riscv", rendered)
        self.assertIn("[1/2] sw.program.elf", rendered)
        self.assertIn("[2/2] sw.program.image", rendered)
        self.assertIn("✓ sw.program.elf", rendered)
        self.assertIn("✓ sw.program.image", rendered)
        self.assertIn("produced nbody_instructions.mem, nbody_dump_real.asm", rendered)
        self.assertIn(f"out/artifacts/sw.program.elf/{elf_dir.name}", rendered)
        self.assertIn(f"out/artifacts/sw.program.image/{out_dir.name}", rendered)
        self.assertNotIn(f"out/artifacts/sw.program.image/{self.program}/{out_dir.name}", rendered)
        self.assertTrue(out_mem.exists())
        self.assertTrue(out_dump.exists())
        metadata = self.metadata(out_dir)
        self.assertEqual(metadata["goal"], "sw.program.image")
        self.assertEqual(metadata["identity"], out_dir.name)
        self.assertEqual(metadata["params"]["program"], self.program)
        self.assertEqual(
            metadata["produced"]["files"],
            [f"{self.program}_instructions.mem", f"{self.program}_dump_real.asm"],
        )
        self.assertEqual(metadata["dependencies"]["sw.program.elf"], elf_dir.name)
        self.assertFalse(out_elf.exists())
        self.assertFalse(out_map.exists())
        self.assertFalse(self.elf.exists())
        self.assertFalse(self.map_file.exists())
        self.assertFalse(self.dump_asm.exists())
        self.assertFalse(self.mem.exists())

    def test_artifact_affecting_option_changes_output_directory(self):
        o2_dir = self.artifact_dir("sw.program.image", "program.optimization=O2")
        o3_dir = self.artifact_dir("sw.program.image", "program.optimization=O3")

        self.assertNotEqual(o2_dir, o3_dir)

    def test_runtime_option_does_not_change_output_directory(self):
        default_dir = self.artifact_dir("sw.program.image")
        fps_dir = self.artifact_dir("sw.program.image", "demo.fps=30")

        self.assertEqual(default_dir, fps_dir)


if __name__ == "__main__":
    unittest.main()
