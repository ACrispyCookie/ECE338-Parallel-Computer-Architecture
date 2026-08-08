from __future__ import annotations

import importlib.util
import subprocess
import sys
import unittest
from pathlib import Path
from types import ModuleType

ROOT = Path(__file__).resolve().parents[2]


class LegacyCliCharacterizationTests(unittest.TestCase):
    maxDiff = None

    def run_cmd(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            list(args),
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
        )

    def test_root_run_help_is_stable_and_non_interactive(self):
        result = self.run_cmd("./run.sh", "--help")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Optional build targets:", result.stdout)
        self.assertIn("--fpga", result.stdout)
        self.assertIn("--kernel-calls N", result.stdout)
        self.assertIn("Adapter-specific FPGA options:", result.stdout)

    def test_programs_run_help_matches_root_entry_point_surface(self):
        root_help = self.run_cmd("./run.sh", "--help")
        programs_help = self.run_cmd("./programs/run.sh", "--help")
        self.assertEqual(programs_help.returncode, 0, programs_help.stderr)
        for marker in (
            "Optional build targets:",
            "--port PORT",
            "--baud BAUD",
            "--skip-load-imem",
            "Put program-specific options after --",
        ):
            self.assertIn(marker, root_help.stdout)
            self.assertIn(marker, programs_help.stdout)

    def test_fpga_run_help_characterizes_common_uart_loop_options(self):
        result = self.run_cmd(sys.executable, "programs/fpga_run.py", "--help")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Run a programs/<program> kernel on the FPGA over UART", result.stdout)
        self.assertIn("--program PROGRAM", result.stdout)
        self.assertIn("--adapter-help", result.stdout)
        self.assertIn("--kernel-calls KERNEL_CALLS", result.stdout)
        self.assertIn("--args-offset ARGS_OFFSET", result.stdout)
        self.assertIn("--skip-load-imem", result.stdout)

    def test_host_uart_tester_help_characterizes_hardware_test_surface(self):
        result = self.run_cmd(sys.executable, "test/host_uart_tester.py", "--help")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Run GPGPU tests through UART monitor.", result.stdout)
        self.assertIn("--port PORT", result.stdout)
        self.assertIn("--dmem-words DMEM_WORDS", result.stdout)
        self.assertIn("--dmem-offset DMEM_OFFSET", result.stdout)
        self.assertIn("--check-words CHECK_WORDS", result.stdout)

    def test_uart_protocol_module_imports_without_opening_serial(self):
        baremetal = ROOT / "host" / "baremetal"
        sys.path.insert(0, str(baremetal))
        try:
            import gpgpu_uart  # type: ignore[import-not-found]
        finally:
            try:
                sys.path.remove(str(baremetal))
            except ValueError:
                pass

        self.assertEqual(gpgpu_uart.DEPTH, 2048)
        self.assertEqual(gpgpu_uart.PROMPT, "gpgpu>")
        self.assertEqual(gpgpu_uart.normalize_word(1), "00000001")
        self.assertEqual(gpgpu_uart.trim_program_at_ret(["00000013", "00008067", "deadbeef"]), ["00000013", "00008067"])

    def test_fpga_run_common_constants_match_uart_protocol_assumptions(self):
        baremetal = ROOT / "host" / "baremetal"
        sys.path.insert(0, str(baremetal))
        module_name = "legacy_fpga_run_for_test"
        spec = importlib.util.spec_from_file_location(module_name, ROOT / "programs" / "fpga_run.py")
        if spec is None or spec.loader is None:
            self.fail("Could not create import spec for programs/fpga_run.py")
        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        try:
            spec.loader.exec_module(module)
        finally:
            sys.modules.pop(module_name, None)
            try:
                sys.path.remove(str(baremetal))
            except ValueError:
                pass

        self.assertIsInstance(module, ModuleType)

        self.assertEqual(module.GPU_ARGS_BASE_WORDS, 0x00000040 // 4)
        self.assertEqual(module.GPU_ARGS_WORDS, 4)
        self.assertEqual(module.normalize_kernel_args([1, "0x2"]), ["00000001", "00000002", "00000000", "00000000"])
        with self.assertRaises(module.AdapterProtocolError):
            module.normalize_kernel_args([1, 2, 3, 4, 5])

    def test_host_uart_tester_reuses_protocol_module_constants(self):
        source = (ROOT / "test" / "host_uart_tester.py").read_text()
        self.assertIn("from gpgpu_uart import DEPTH", source)
        self.assertIn("GpgpuUartMonitor as GpgpuUart", source)
        self.assertIn("trim_program_at_ret", source)
        self.assertIn("uart.load_imem_bin", source)
        self.assertIn("uart.dump_dmem_bin", source)


if __name__ == "__main__":
    unittest.main()
