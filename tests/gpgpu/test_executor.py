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
        self.out_native = ROOT / "out" / f"{self.program}_x86"
        self.out_elf = ROOT / "out" / f"{self.program}.elf"
        self.out_mem = ROOT / "out" / f"{self.program}_instructions.mem"
        self.native_exe.unlink(missing_ok=True)
        self.elf.unlink(missing_ok=True)
        self.map_file.unlink(missing_ok=True)
        self.dump_asm.unlink(missing_ok=True)
        self.mem.unlink(missing_ok=True)
        self.out_native.unlink(missing_ok=True)
        self.out_elf.unlink(missing_ok=True)
        self.out_mem.unlink(missing_ok=True)

    def tearDown(self):
        self.native_exe.unlink(missing_ok=True)
        self.elf.unlink(missing_ok=True)
        self.map_file.unlink(missing_ok=True)
        self.dump_asm.unlink(missing_ok=True)
        self.mem.unlink(missing_ok=True)
        self.out_native.unlink(missing_ok=True)
        self.out_elf.unlink(missing_ok=True)
        self.out_mem.unlink(missing_ok=True)
        if self.program_asm_snapshot is not None:
            self.program_asm.write_text(self.program_asm_snapshot)

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

    def test_native_adapter_builds_legacy_executable(self):
        self.require_native_tools()
        stdout = io.StringIO()
        stderr = io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            code = main(["--color", "never", "run", "sw.program.native", "--set", f"program={self.program}"])

        rendered = stdout.getvalue()
        self.assertEqual(code, 0, stderr.getvalue() + rendered)
        self.assertIn("Run: sw.program.native", rendered)
        self.assertIn("make -C sw/programs PROG=nbody x86", rendered)
        self.assertIn("Produced:", rendered)
        self.assertIn("sw/programs/nbody/nbody_x86", rendered)
        self.assertTrue(self.native_exe.exists())
        self.assertTrue(os.access(self.native_exe, os.X_OK))
        self.assertFalse(self.out_native.exists())

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

    def test_elf_adapter_builds_legacy_riscv_elf(self):
        self.require_riscv_tools()
        stdout = io.StringIO()
        stderr = io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            code = main(["--color", "never", "run", "sw.program.elf", "--set", f"program={self.program}"])

        rendered = stdout.getvalue()
        self.assertEqual(code, 0, stderr.getvalue() + rendered)
        self.assertIn("Run: sw.program.elf", rendered)
        self.assertIn("make -C sw/programs PROG=nbody nbody/nbody.elf", rendered)
        self.assertIn("Produced:", rendered)
        self.assertIn("sw/programs/nbody/nbody.elf", rendered)
        self.assertTrue(self.elf.exists())
        self.assertFalse(self.out_elf.exists())

    def test_image_adapter_builds_legacy_instruction_memory(self):
        self.require_riscv_tools()
        stdout = io.StringIO()
        stderr = io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            code = main(["--color", "never", "run", "sw.program.image", "--set", f"program={self.program}"])

        rendered = stdout.getvalue()
        self.assertEqual(code, 0, stderr.getvalue() + rendered)
        self.assertIn("Run: sw.program.image", rendered)
        self.assertIn("make -C sw/programs PROG=nbody nbody/nbody_instructions.mem", rendered)
        self.assertIn("Produced:", rendered)
        self.assertIn("sw/programs/nbody/nbody_instructions.mem", rendered)
        self.assertIn("sw/programs/nbody/nbody_dump_real.asm", rendered)
        self.assertTrue(self.mem.exists())
        self.assertTrue(self.dump_asm.exists())
        self.assertFalse(self.out_mem.exists())


if __name__ == "__main__":
    unittest.main()
