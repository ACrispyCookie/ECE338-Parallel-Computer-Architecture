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


class NativeProgramAdapterTests(unittest.TestCase):
    program = "nbody"

    def setUp(self):
        self.native_exe = ROOT / "programs" / self.program / f"{self.program}_x86"
        self.out_native = ROOT / "out" / f"{self.program}_x86"
        self.native_exe.unlink(missing_ok=True)
        self.out_native.unlink(missing_ok=True)

    def tearDown(self):
        self.native_exe.unlink(missing_ok=True)
        self.out_native.unlink(missing_ok=True)

    def require_native_tools(self):
        if shutil.which("make") is None:
            self.skipTest("make is required for native compatibility adapter test")
        if shutil.which("gcc") is None:
            self.skipTest("gcc is required for native compatibility adapter test")

    def test_unsupported_run_goal_fails_clearly(self):
        stdout = io.StringIO()
        stderr = io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            code = main(["--color", "never", "run", "hw.board.bitstream"])
        self.assertEqual(code, 2)
        self.assertEqual(stdout.getvalue(), "")
        self.assertIn("no executor adapter registered for hw.board.bitstream", stderr.getvalue())

    def test_native_adapter_builds_legacy_executable(self):
        self.require_native_tools()
        stdout = io.StringIO()
        stderr = io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            code = main(["--color", "never", "run", "sw.program.native", "--set", f"program={self.program}"])

        rendered = stdout.getvalue()
        self.assertEqual(code, 0, stderr.getvalue() + rendered)
        self.assertIn("Run: sw.program.native", rendered)
        self.assertIn("make -C programs PROG=nbody x86", rendered)
        self.assertIn("Produced:", rendered)
        self.assertIn("programs/nbody/nbody_x86", rendered)
        self.assertTrue(self.native_exe.exists())
        self.assertTrue(os.access(self.native_exe, os.X_OK))
        self.assertFalse(self.out_native.exists())

    def test_native_adapter_does_not_run_program_or_create_data_csv(self):
        self.require_native_tools()
        data_csv = ROOT / "programs" / self.program / "data.csv"
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


if __name__ == "__main__":
    unittest.main()
