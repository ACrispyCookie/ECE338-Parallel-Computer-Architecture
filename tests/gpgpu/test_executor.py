from __future__ import annotations

import contextlib
import io
import os
import shutil
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from tools.gpgpu.cli import main
from tools.gpgpu.config import ConfigResolver
from tools.gpgpu.planner import Planner


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
            shutil.rmtree(ROOT / "out" / "artifacts" / goal_id / self.program, ignore_errors=True)

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
        config = ConfigResolver().resolve(set_values=[f"program={self.program}", *set_values])
        identity = Planner(config).plan(goal_id).root.identity
        return ROOT / "out" / "artifacts" / goal_id / self.program / identity

    def test_unsupported_run_goal_fails_clearly(self):
        stdout = io.StringIO()
        stderr = io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            code = main(["--color", "never", "run", "hw.board.bitstream"])
        self.assertEqual(code, 2)
        self.assertEqual(stdout.getvalue(), "")
        self.assertIn("no executor adapter registered for hw.board.bitstream", stderr.getvalue())

    def test_unimplemented_program_check_still_fails_clearly(self):
        stdout = io.StringIO()
        stderr = io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            code = main(["--color", "never", "run", "test.program", "--set", f"program={self.program}"])
        self.assertEqual(code, 2)
        self.assertEqual(stdout.getvalue(), "")
        self.assertIn("no executor adapter registered for test.program", stderr.getvalue())

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
        self.assertIn("Run: sw.program.native", rendered)
        self.assertIn("make -C sw/programs PROG=nbody OUT_DIR=", rendered)
        self.assertIn(" native", rendered)
        self.assertIn("Produced:", rendered)
        self.assertIn(f"out/artifacts/sw.program.native/nbody/{out_dir.name}/nbody_x86", rendered)
        self.assertTrue(out_native.exists())
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
        self.assertIn("Run: sw.program.elf", rendered)
        self.assertIn("make -C sw/programs PROG=nbody OUT_DIR=", rendered)
        self.assertIn(" elf", rendered)
        self.assertIn(f"out/artifacts/sw.program.elf/nbody/{out_dir.name}/nbody.elf", rendered)
        self.assertTrue(out_elf.exists())
        self.assertTrue(out_map.exists())
        self.assertFalse(self.elf.exists())
        self.assertFalse(self.map_file.exists())

    def test_image_adapter_builds_artifacts_under_out(self):
        self.require_riscv_tools()
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
        self.assertIn("Run: sw.program.image", rendered)
        self.assertIn("make -C sw/programs PROG=nbody OUT_DIR=", rendered)
        self.assertIn(" image", rendered)
        self.assertIn(f"out/artifacts/sw.program.image/nbody/{out_dir.name}/nbody_instructions.mem", rendered)
        self.assertIn(f"out/artifacts/sw.program.image/nbody/{out_dir.name}/nbody_dump_real.asm", rendered)
        self.assertTrue(out_mem.exists())
        self.assertTrue(out_dump.exists())
        self.assertTrue(out_elf.exists())
        self.assertTrue(out_map.exists())
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
