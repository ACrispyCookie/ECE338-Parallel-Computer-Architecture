from __future__ import annotations

import contextlib
import hashlib
import io
import json
import os
import shutil
import sys
import tempfile
import tomllib
import unittest
from unittest import mock
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from tools.gpgpu.cli import main
from tools.gpgpu.config import ConfigResolver
from tools.gpgpu.artifacts import artifact_dir
from tools.gpgpu.executor import Executor, ProducedArtifact, RunResult, format_run_summary
from tools.gpgpu.planner import Planner
from tools.gpgpu.reporter import InteractiveRunReporter, PlainRunReporter


class ExecutorStructureTests(unittest.TestCase):
    def test_program_adapters_are_registered_by_goal_id(self):
        from tools.gpgpu.adapters import ADAPTERS

        self.assertIn("sw.abi", ADAPTERS)
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

    def test_program_adapters_do_not_guess_dependency_artifacts_by_suffix(self):
        adapter_source = (ROOT / "tools" / "gpgpu" / "adapters" / "sw_programs.py").read_text()

        self.assertNotIn("suffix=", adapter_source)
        self.assertNotIn("endswith", adapter_source)

    def test_artifact_dir_helper_uses_goal_and_identity_without_program_component(self):
        from tools.gpgpu.artifacts import artifact_dir

        config = ConfigResolver().resolve(set_values=["program=nbody"])
        node = Planner(config).plan("sw.program.elf").root

        self.assertEqual(
            artifact_dir(ROOT, node),
            ROOT / "out" / "artifacts" / "sw.program.elf" / node.identity,
        )

    def test_executor_keeps_graph_execution_as_the_only_public_run_api(self):
        from tools.gpgpu.executor import Executor

        self.assertTrue(hasattr(Executor, "run_plan"))
        self.assertFalse(hasattr(Executor, "run"))


class GraphRunTests(unittest.TestCase):
    program = "nbody"

    def setUp(self):
        self._clean_program_artifacts()

    def tearDown(self):
        self._clean_program_artifacts()

    def _clean_program_artifacts(self):
        for goal_id in ("sw.abi", "sw.program.native", "sw.program.elf", "sw.program.image"):
            shutil.rmtree(ROOT / "out" / "artifacts" / goal_id, ignore_errors=True)

    def config(self):
        return ConfigResolver().resolve(set_values=[f"program={self.program}"])

    def test_run_plan_executes_registered_dependencies_before_root(self):
        config = self.config()
        plan = Planner(config).plan("sw.program.image")
        calls: list[str] = []

        def record(name: str):
            def adapter(context):
                calls.append(context.goal_id)
                for output in context.declared_outputs.values():
                    output.path.write_text(f"{name}\n", encoding="utf-8")
                return RunResult(
                    goal_id=context.goal_id,
                    command=("fake", name),
                    returncode=0,
                    produced=tuple(context.declared_outputs.values()),
                )
            return adapter

        summary = Executor(
            config,
            adapters={
                "sw.abi": record("abi"),
                "sw.program.elf": record("elf"),
                "sw.program.image": record("image"),
            },
        ).run_plan(plan)

        self.assertEqual(calls, ["sw.abi", "sw.program.elf", "sw.program.image"])
        self.assertEqual(summary.returncode, 0)
        rendered = format_run_summary(summary, repo_root=ROOT)
        self.assertIn("Run: sw.program.image", rendered)
        self.assertIn("Plan: 3 executable goals, 3 planned goals", rendered)
        self.assertNotIn("SKIPPED", rendered)
        self.assertNotIn("sw.program.compile_riscv", rendered)
        self.assertLess(rendered.index("RUNNING   sw.abi"), rendered.index("RUNNING   sw.program.elf"))
        self.assertLess(rendered.index("RUNNING   sw.program.elf"), rendered.index("RUNNING   sw.program.image"))
        self.assertIn("DONE      sw.abi", rendered)
        self.assertIn("DONE      sw.program.elf", rendered)
        self.assertIn("DONE      sw.program.image", rendered)
        self.assertIn("completed: 3", rendered)
        self.assertIn("skipped:   0", rendered)
        self.assertIn("failed:    0", rendered)

    def test_successful_adapter_missing_declared_output_fails_goal(self):
        config = self.config()
        plan = Planner(config).plan("sw.program.native")
        shutil.rmtree(ROOT / "out" / "artifacts" / "sw.program.native", ignore_errors=True)

        def native(context):
            return RunResult(goal_id=context.goal_id, command=("fake", "native"), returncode=0, produced=())

        summary = Executor(config, adapters={"sw.program.native": native}).run_plan(plan)

        self.assertEqual(summary.returncode, 1)
        self.assertEqual(summary.failed_count, 1)
        rendered = format_run_summary(summary, repo_root=ROOT)
        self.assertIn("FAILED    sw.program.native", rendered)
        self.assertIn("declared output missing: executable -> nbody_x86", rendered)

    def test_dependency_outputs_are_addressed_by_dependency_and_output_role(self):
        config = self.config()
        plan = Planner(config).plan("sw.program.image")
        seen_elf_path: list[Path] = []

        def elf(context):
            output = context.declared_outputs["elf"]
            output.path.write_text("elf\n", encoding="utf-8")
            context.declared_outputs["map"].path.write_text("map\n", encoding="utf-8")
            return RunResult(
                goal_id=context.goal_id,
                command=("fake", "elf"),
                returncode=0,
                produced=tuple(context.declared_outputs.values()),
            )

        def image(context):
            seen_elf_path.append(context.dependency_outputs["sw.program.elf"]["elf"].path)
            for output in context.declared_outputs.values():
                output.path.write_text(f"{output.role}\n", encoding="utf-8")
            return RunResult(
                goal_id=context.goal_id,
                command=("fake", "image"),
                returncode=0,
                produced=tuple(context.declared_outputs.values()),
            )

        def abi(context):
            for output in context.declared_outputs.values():
                output.path.write_text(f"{output.role}\n", encoding="utf-8")
            return RunResult(goal_id=context.goal_id, command=("fake", "abi"), returncode=0, produced=tuple(context.declared_outputs.values()))

        summary = Executor(config, adapters={"sw.abi": abi, "sw.program.elf": elf, "sw.program.image": image}).run_plan(plan)

        self.assertEqual(summary.returncode, 0)
        self.assertEqual(seen_elf_path, [artifact_dir(ROOT, plan.nodes[1]) / "nbody.elf"])

    def test_run_plan_skips_validated_artifact_cache_hit(self):
        from tools.gpgpu.artifacts import artifact_dir, resolve_artifact_inputs, resolve_artifact_outputs, write_artifact_metadata

        config = self.config()
        initial = Planner(config, repo_root=ROOT).plan("sw.program.native")
        abi_node = initial.nodes[0]
        native_node = initial.root
        abi_dir = artifact_dir(ROOT, abi_node)
        out_dir = artifact_dir(ROOT, initial.root)
        shutil.rmtree(ROOT / "out" / "artifacts" / "sw.abi", ignore_errors=True)
        shutil.rmtree(ROOT / "out" / "artifacts" / "sw.program.native", ignore_errors=True)
        abi_dir.mkdir(parents=True, exist_ok=True)
        abi_outputs = resolve_artifact_outputs(abi_dir, abi_node, config)
        for output in abi_outputs:
            output.path.write_text("abi output\n", encoding="utf-8")
        write_artifact_metadata(
            abi_dir,
            node=abi_node,
            produced=abi_outputs,
            dependency_identities={},
            input_paths=resolve_artifact_inputs(ROOT, abi_node, config),
            repo_root=ROOT,
        )
        out_dir.mkdir(parents=True, exist_ok=True)
        outputs = resolve_artifact_outputs(out_dir, native_node, config)
        for output in outputs:
            output.path.write_text("native output\n", encoding="utf-8")
        write_artifact_metadata(
            out_dir,
            node=native_node,
            produced=outputs,
            dependency_identities={"sw.abi": abi_node.identity},
            input_paths=resolve_artifact_inputs(ROOT, native_node, config),
            repo_root=ROOT,
        )
        calls: list[str] = []

        def native(context):
            calls.append(context.goal_id)
            raise AssertionError("cache-hit artifact adapter should not run")

        try:
            plan = Planner(config, repo_root=ROOT).plan("sw.program.native")
            self.assertIn("CACHE HIT", plan.format_plan())
            summary = Executor(config, adapters={"sw.program.native": native}).run_plan(plan)
        finally:
            shutil.rmtree(ROOT / "out" / "artifacts" / "sw.abi", ignore_errors=True)
            shutil.rmtree(ROOT / "out" / "artifacts" / "sw.program.native", ignore_errors=True)

        self.assertEqual(summary.returncode, 0)
        self.assertEqual(calls, [])
        self.assertEqual(summary.completed_count, 0)
        self.assertEqual(summary.skipped_count, 2)
        self.assertEqual(summary.records[-1].status, "skipped")
        self.assertEqual(summary.records[-1].reason, "artifact cache hit")

    def test_cache_hit_dependency_outputs_are_available_to_dependent_adapter(self):
        from tools.gpgpu.artifacts import artifact_dir, resolve_artifact_inputs, resolve_artifact_outputs, write_artifact_metadata

        config = self.config()
        initial = Planner(config, repo_root=ROOT).plan("sw.program.elf")
        elf_dir = artifact_dir(ROOT, initial.root)
        shutil.rmtree(ROOT / "out" / "artifacts" / "sw.program.elf", ignore_errors=True)
        shutil.rmtree(ROOT / "out" / "artifacts" / "sw.program.image", ignore_errors=True)
        elf_dir.mkdir(parents=True, exist_ok=True)
        elf_outputs = resolve_artifact_outputs(elf_dir, initial.root, config)
        for output in elf_outputs:
            output.path.write_text(f"cached {output.role}\n", encoding="utf-8")
        write_artifact_metadata(
            elf_dir,
            node=initial.root,
            produced=elf_outputs,
            dependency_identities=dict(initial.root.dependency_identities),
            input_paths=resolve_artifact_inputs(ROOT, initial.root, config),
            repo_root=ROOT,
        )
        calls: list[str] = []
        seen_elf_path: list[Path] = []

        def elf(context):
            calls.append(context.goal_id)
            raise AssertionError("cache-hit dependency adapter should not run")

        def image(context):
            calls.append(context.goal_id)
            seen_elf_path.append(context.dependency_outputs["sw.program.elf"]["elf"].path)
            for output in context.declared_outputs.values():
                output.path.write_text(f"{output.role}\n", encoding="utf-8")
            return RunResult(goal_id=context.goal_id, command=("fake", "image"), returncode=0, produced=tuple(context.declared_outputs.values()))

        try:
            plan = Planner(config, repo_root=ROOT).plan("sw.program.image")
            self.assertIn("CACHE HIT", next(line for line in plan.format_plan().splitlines() if "sw.program.elf" in line))
            summary = Executor(config, adapters={"sw.program.elf": elf, "sw.program.image": image}).run_plan(plan)
        finally:
            shutil.rmtree(ROOT / "out" / "artifacts" / "sw.program.elf", ignore_errors=True)
            shutil.rmtree(ROOT / "out" / "artifacts" / "sw.program.image", ignore_errors=True)

        self.assertEqual(summary.returncode, 0)
        self.assertEqual(calls, ["sw.program.image"])
        self.assertEqual(seen_elf_path, [elf_dir / "nbody.elf"])

    def test_run_summary_supports_colorized_status_output(self):
        config = self.config()
        plan = Planner(config).plan("sw.program.native")

        def native(context):
            for output in context.declared_outputs.values():
                output.path.write_text("native\n", encoding="utf-8")
            return RunResult(goal_id=context.goal_id, command=("fake", "native"), returncode=0, produced=tuple(context.declared_outputs.values()))

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

    def test_adapter_exception_is_reported_as_failed_goal_without_escaping_executor(self):
        config = self.config()
        plan = Planner(config).plan("sw.program.native")

        def broken_adapter(context):
            raise RuntimeError("adapter exploded")

        summary = Executor(config, adapters={"sw.program.native": broken_adapter}).run_plan(plan)

        self.assertEqual(summary.returncode, 1)
        rendered = format_run_summary(summary, repo_root=ROOT)
        self.assertIn("FAILED    sw.program.native", rendered)
        self.assertIn("adapter exploded", rendered)
        self.assertNotIn("Traceback", rendered)

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
                for output in context.declared_outputs.values():
                    output.path.write_text(f"{name}\n", encoding="utf-8")
                return RunResult(
                    goal_id=context.goal_id,
                    command=("fake", name),
                    returncode=0,
                    produced=tuple(context.declared_outputs.values()),
                )
            return adapter

        summary = Executor(
            config,
            adapters={"sw.abi": record("abi"), "sw.program.elf": record("elf"), "sw.program.image": record("image")},
        ).run_plan(plan, reporter=PlainRunReporter(stream, repo_root=ROOT, color=False))

        rendered = stream.getvalue()
        self.assertEqual(summary.returncode, 0)
        self.assertIn("gpgpu run sw.program.image", rendered)
        self.assertIn("✓ sw.abi", rendered)
        self.assertIn("✓ sw.program.elf", rendered)
        self.assertIn("✓ sw.program.image", rendered)
        self.assertNotIn("sw.program.compile_riscv", rendered)
        self.assertIn("Summary: 3 completed, 0 skipped, 0 failed", rendered)
        self.assertNotIn("RUNNING", rendered)
        self.assertNotIn("DONE", rendered)

    def test_interactive_reporter_replaces_spinner_with_completed_goal_area(self):
        config = self.config()
        plan = Planner(config).plan("sw.program.native")
        stream = io.StringIO()

        def native(context):
            for output in context.declared_outputs.values():
                output.path.write_text("native\n", encoding="utf-8")
            return RunResult(
                goal_id=context.goal_id,
                command=("fake", "native"),
                returncode=0,
                produced=tuple(context.declared_outputs.values()),
            )

        summary = Executor(config, adapters={"sw.program.native": native}).run_plan(
            plan,
            reporter=InteractiveRunReporter(stream, repo_root=ROOT, color=False),
        )

        rendered = stream.getvalue()
        self.assertEqual(summary.returncode, 0)
        self.assertIn("╭─ [1/1] sw.program.native", rendered)
        self.assertIn("\r\033[2K│  ✓ completed", rendered)
        self.assertIn("│  produced: nbody_x86", rendered)
        self.assertIn("╰─ 1 completed, 1 skipped, 0 failed", rendered)
        self.assertNotIn("running fake native\n✓", rendered)

    def test_interactive_reporter_uses_richer_color_for_goal_area(self):
        config = self.config()
        plan = Planner(config).plan("sw.program.native")
        stream = io.StringIO()

        def native(context):
            for output in context.declared_outputs.values():
                output.path.write_text("native\n", encoding="utf-8")
            return RunResult(goal_id=context.goal_id, command=("fake", "native"), returncode=0, produced=tuple(context.declared_outputs.values()))

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
        self.assertIn("✓ sw.abi", rendered)
        self.assertIn("Summary: 2 completed, 0 skipped, 0 failed", rendered)
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
        for goal_id in ("sw.abi", "sw.program.native", "sw.program.elf", "sw.program.image"):
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

    def test_sw_abi_adapter_generates_runtime_linker_and_metadata(self):
        out_dir = self.artifact_dir("sw.abi")
        runtime_header = out_dir / "gpgpu_runtime.h"
        linker_script = out_dir / "gpgpu.ld"
        abi_json = out_dir / "gpgpu_abi.json"

        stdout = io.StringIO()
        stderr = io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            code = main(["--color", "never", "run", "sw.abi", "--set", f"program={self.program}"])

        rendered = stdout.getvalue()
        self.assertEqual(code, 0, stderr.getvalue() + rendered)
        self.assertIn("gpgpu run sw.abi", rendered)
        self.assertTrue(runtime_header.exists())
        self.assertTrue(linker_script.exists())
        self.assertTrue(abi_json.exists())

        header = runtime_header.read_text()
        self.assertIn("#define GPGPU_NUM_CORES    32u", header)
        self.assertIn("#define GPGPU_STACK_STRIDE 64u", header)
        self.assertIn('\"mv %0, x31\"', header)
        self.assertIn('"slli x6, x5, 6\\n"', header)

        linker = linker_script.read_text()
        self.assertIn("IMEM (rx)  : ORIGIN = 0x00000000, LENGTH = 8K", linker)
        self.assertIn("__gpu_args_base      = 0x00000040;", linker)
        self.assertIn("__gpu_stack_bottom   = 0x00001800;", linker)

        metadata = json.loads(abi_json.read_text())
        self.assertEqual(metadata["architecture"], "gpgpu32")
        self.assertEqual(metadata["abi"]["args"]["base_byte"], 0x40)
        self.assertEqual(metadata["abi"]["data"]["limit_byte"], 0x1800)
        self.assertEqual(metadata["abi"]["stack"]["bottom_byte"], 0x1800)

    def test_sw_abi_adapter_reports_python_adapter_command(self):
        out_dir = self.artifact_dir("sw.abi")
        shutil.rmtree(out_dir, ignore_errors=True)
        config = ConfigResolver().resolve(set_values=[f"program={self.program}"])
        plan = Planner(config, repo_root=ROOT).plan("sw.abi")

        summary = Executor(config, repo_root=ROOT).run_plan(plan)

        self.assertEqual(summary.returncode, 0)
        result = summary.records[-1].result
        assert result is not None
        self.assertEqual(result.command, ("python-adapter", "sw.abi"))

    def test_sw_abi_templates_are_artifact_inputs_without_architecture_manifest_glob(self):
        from tools.gpgpu.artifacts import resolve_artifact_inputs

        config = ConfigResolver().resolve(set_values=[f"program={self.program}"])
        node = Planner(config, repo_root=ROOT).plan("sw.abi").root
        relative = {path.relative_to(ROOT).as_posix() for path in resolve_artifact_inputs(ROOT, node, config)}

        self.assertEqual(
            relative,
            {
                "sw/programs/gpgpu_runtime.h.in",
                "sw/programs/gpgpu.ld.in",
            },
        )

    def test_sw_abi_template_renderer_rejects_unknown_variables(self):
        from tools.gpgpu.adapters import sw_abi

        with tempfile.TemporaryDirectory() as tmp:
            template = Path(tmp) / "bad_template.in"
            template.write_text("value=${architecture.rtl.thread.typo}\n", encoding="utf-8")
            model = sw_abi.AbiModel(
                architecture="gpgpu32",
                word_bytes=4,
                thread_count=32,
                thread_id_register="x31",
                imem_origin=0,
                imem_words=2048,
                dmem_origin=0,
                dmem_words=2048,
                args_base_word=16,
                args_words=4,
                data_base_word=1024,
                stack_per_lane_bytes=64,
                stack_top_word=2048,
            )

            with self.assertRaisesRegex(ValueError, "unknown ABI template variable 'architecture.rtl.thread.typo'"):
                sw_abi._render_template(template, sw_abi._template_variables(model))

    def test_sw_abi_template_renderer_accepts_resolved_config_values(self):
        from tools.gpgpu.adapters import sw_abi

        with tempfile.TemporaryDirectory() as tmp:
            template = Path(tmp) / "resolved_setting.in"
            template.write_text("sp=${architecture.rtl.sp_per_sm}\n", encoding="utf-8")
            config = ConfigResolver().resolve()
            model = sw_abi.AbiModel(
                architecture="gpgpu32",
                word_bytes=4,
                thread_count=32,
                thread_id_register="x31",
                imem_origin=0,
                imem_words=2048,
                dmem_origin=0,
                dmem_words=2048,
                args_base_word=16,
                args_words=4,
                data_base_word=1024,
                stack_per_lane_bytes=64,
                stack_top_word=2048,
            )

            rendered = sw_abi._render_template(template, sw_abi._template_variables(model, config.values))

        self.assertEqual(rendered, "sp=32\n")

    def test_sw_abi_template_variables_do_not_overwrite_resolved_config_values(self):
        from tools.gpgpu.adapters import sw_abi

        model = sw_abi.AbiModel(
            architecture="gpgpu32",
            word_bytes=4,
            thread_count=32,
            thread_id_register="x31",
            imem_origin=0,
            imem_words=2048,
            dmem_origin=0,
            dmem_words=2048,
            args_base_word=16,
            args_words=4,
            data_base_word=1024,
            stack_per_lane_bytes=64,
            stack_top_word=2048,
        )

        variables = sw_abi._template_variables(model, {"architecture.rtl.thread.count": 64})

        self.assertEqual(variables["architecture.rtl.thread.count"], "64")

    def test_sw_abi_template_variables_reject_derived_config_overlap(self):
        from tools.gpgpu.adapters import sw_abi

        model = sw_abi.AbiModel(
            architecture="gpgpu32",
            word_bytes=4,
            thread_count=32,
            thread_id_register="x31",
            imem_origin=0,
            imem_words=2048,
            dmem_origin=0,
            dmem_words=2048,
            args_base_word=16,
            args_words=4,
            data_base_word=1024,
            stack_per_lane_bytes=64,
            stack_top_word=2048,
        )

        with self.assertRaisesRegex(ValueError, "derived ABI template variables overlap resolved config"):
            sw_abi._template_variables(model, {"architecture.memory.imem.bytes": 8192})

    def test_sw_abi_unknown_template_variable_fails_cli_without_traceback(self):
        from tools.gpgpu.adapters import sw_abi

        with tempfile.TemporaryDirectory() as tmp:
            bad_template = Path(tmp) / "bad_runtime.h.in"
            bad_template.write_text("value=${architecture.rtl.thread.typo}\n", encoding="utf-8")
            stdout = io.StringIO()
            stderr = io.StringIO()

            with mock.patch.object(sw_abi, "_RUNTIME_HEADER_TEMPLATE", bad_template):
                with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                    code = main(["--color", "never", "run", "sw.abi", "--progress", "plain"])

        rendered = stdout.getvalue() + stderr.getvalue()
        self.assertEqual(code, 1, rendered)
        self.assertIn("✗ sw.abi", rendered)
        self.assertIn("unknown ABI template variable 'architecture.rtl.thread.typo'", rendered)
        self.assertNotIn("Traceback", rendered)

    def test_sw_abi_adapter_does_not_embed_generated_header_or_linker_body(self):
        source = (ROOT / "tools" / "gpgpu" / "adapters" / "sw_abi.py").read_text(encoding="utf-8")

        self.assertNotIn("#ifndef GPGPU_RUNTIME_H", source)
        self.assertNotIn("SECTIONS", source)
        self.assertIn("#ifndef GPGPU_RUNTIME_H", (ROOT / "sw" / "programs" / "gpgpu_runtime.h.in").read_text(encoding="utf-8"))
        self.assertIn("SECTIONS", (ROOT / "sw" / "programs" / "gpgpu.ld.in").read_text(encoding="utf-8"))

    def test_sw_program_elf_depends_on_generated_abi(self):
        config = ConfigResolver().resolve(set_values=[f"program={self.program}"])
        plan = Planner(config, repo_root=ROOT).plan("sw.program.elf")
        ids = [node.goal_id for node in plan.nodes]

        self.assertEqual(ids, ["sw.abi", "sw.program.elf"])
        self.assertEqual(plan.root.dependencies, (plan.nodes[0].key,))

    def test_sw_program_native_depends_on_generated_abi(self):
        config = ConfigResolver().resolve(set_values=[f"program={self.program}"])
        plan = Planner(config, repo_root=ROOT).plan("sw.program.native")
        ids = [node.goal_id for node in plan.nodes]

        self.assertEqual(ids, ["sw.abi", "sw.program.native"])
        self.assertEqual(plan.root.dependencies, (plan.nodes[0].key,))

    def test_native_adapter_passes_generated_abi_include_dir_to_make(self):
        config = ConfigResolver().resolve(set_values=[f"program={self.program}"])
        plan = Planner(config, repo_root=ROOT).plan("sw.program.native")
        seen_command: list[tuple[str, ...]] = []

        def abi(context):
            for output in context.declared_outputs.values():
                output.path.write_text("generated\n")
            return RunResult(goal_id=context.goal_id, command=("fake", "abi"), returncode=0, produced=tuple(context.declared_outputs.values()))

        def native(context):
            module = __import__("tools.gpgpu.adapters.sw_programs", fromlist=["run_native"])
            with mock.patch.object(module.subprocess, "run") as run:
                run.return_value.returncode = 0
                run.return_value.stdout = ""
                run.return_value.stderr = ""
                command = module.run_native(context).command
                seen_command.append(command)
            for output in context.declared_outputs.values():
                output.path.write_text(output.role)
            return RunResult(goal_id=context.goal_id, command=command, returncode=0, produced=tuple(context.declared_outputs.values()))

        summary = Executor(config, adapters={"sw.abi": abi, "sw.program.native": native}).run_plan(plan)

        self.assertEqual(summary.returncode, 0)
        command = seen_command[0]
        self.assertIn("ABI_INCLUDE_DIR=" + str(artifact_dir(ROOT, plan.nodes[0])), command)

    def test_elf_adapter_passes_generated_abi_files_to_make(self):
        config = ConfigResolver().resolve(set_values=[f"program={self.program}"])
        plan = Planner(config, repo_root=ROOT).plan("sw.program.elf")
        seen_command: list[tuple[str, ...]] = []

        def abi(context):
            for output in context.declared_outputs.values():
                output.path.write_text("generated\n")
            return RunResult(goal_id=context.goal_id, command=("fake", "abi"), returncode=0, produced=tuple(context.declared_outputs.values()))

        def elf(context):
            module = __import__("tools.gpgpu.adapters.sw_programs", fromlist=["run_elf"])
            with mock.patch.object(module.subprocess, "run") as run:
                run.return_value.returncode = 0
                run.return_value.stdout = ""
                run.return_value.stderr = ""
                command = module.run_elf(context).command
                seen_command.append(command)
            for output in context.declared_outputs.values():
                output.path.write_text(output.role)
            return RunResult(goal_id=context.goal_id, command=command, returncode=0, produced=tuple(context.declared_outputs.values()))

        summary = Executor(config, adapters={"sw.abi": abi, "sw.program.elf": elf}).run_plan(plan)

        self.assertEqual(summary.returncode, 0)
        command = seen_command[0]
        self.assertIn("ABI_INCLUDE_DIR=" + str(artifact_dir(ROOT, plan.nodes[0])), command)
        self.assertIn("LINKER_SCRIPT=" + str(artifact_dir(ROOT, plan.nodes[0]) / "gpgpu.ld"), command)

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
        self.assertIn("[1/2] sw.abi", rendered)
        self.assertIn("[2/2] sw.program.native", rendered)
        self.assertIn("✓ sw.abi", rendered)
        self.assertIn("✓ sw.program.native", rendered)
        self.assertIn("produced nbody_x86", rendered)
        self.assertIn(f"out/artifacts/sw.program.native/{out_dir.name}", rendered)
        self.assertNotIn(f"out/artifacts/sw.program.native/{self.program}/{out_dir.name}", rendered)
        self.assertTrue(out_native.exists())
        metadata = self.metadata(out_dir)
        self.assertEqual(metadata["goal"], "sw.program.native")
        self.assertEqual(metadata["identity"], out_dir.name)
        self.assertEqual(metadata["params"]["program"], self.program)
        self.assertEqual(metadata["produced"]["executable"], {"path": f"{self.program}_x86"})
        self.assertIn(f"{self.program}_x86", metadata["output_hashes"])
        self.assertIn("sw/programs/Makefile", metadata["input_hashes"])
        self.assertIn(f"sw/programs/{self.program}/nbody.c", metadata["input_hashes"])
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
        self.assertIn("[1/2] sw.abi", rendered)
        self.assertIn("[2/2] sw.program.elf", rendered)
        self.assertIn("✓ sw.abi", rendered)
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
        self.assertEqual(metadata["produced"]["elf"], {"path": f"{self.program}.elf"})
        self.assertEqual(metadata["produced"]["map"], {"path": f"{self.program}.map"})
        self.assertIn(f"{self.program}.elf", metadata["output_hashes"])
        self.assertIn(f"{self.program}.map", metadata["output_hashes"])
        self.assertIn("sw/programs/Makefile", metadata["input_hashes"])
        self.assertIn(f"sw/programs/{self.program}/nbody.c", metadata["input_hashes"])
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
        self.assertIn("[1/3] sw.abi", rendered)
        self.assertIn("[2/3] sw.program.elf", rendered)
        self.assertIn("[3/3] sw.program.image", rendered)
        self.assertIn("✓ sw.abi", rendered)
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
            metadata["produced"]["imem"],
            {"path": f"{self.program}_instructions.mem"},
        )
        self.assertEqual(
            metadata["produced"]["objdump"],
            {"path": f"{self.program}_dump_real.asm"},
        )
        self.assertEqual(metadata["dependencies"]["sw.program.elf"], elf_dir.name)
        self.assertIn(f"{self.program}_instructions.mem", metadata["output_hashes"])
        self.assertIn(f"{self.program}_dump_real.asm", metadata["output_hashes"])
        self.assertIn("sw/programs/Makefile", metadata["input_hashes"])
        self.assertIn(f"sw/programs/{self.program}/nbody.c", metadata["input_hashes"])
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
