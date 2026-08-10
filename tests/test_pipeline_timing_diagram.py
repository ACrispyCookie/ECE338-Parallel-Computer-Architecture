from __future__ import annotations

import importlib.util
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = REPO_ROOT / "test" / "pipeline_timing_diagram.py"
SPEC = importlib.util.spec_from_file_location("pipeline_timing_diagram", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
pipeline_timing_diagram = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(pipeline_timing_diagram)


class PipelineTimingDiagramTests(unittest.TestCase):
    def test_reset_pcs_are_hidden_only_while_pipeline_fills(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            tests_dir = Path(temporary_directory)
            case = tests_dir / "test1"
            case.mkdir()
            (case / "program.asm").write_text(
                "\n".join(
                    [
                        "addi x1,x0,1",
                        "addi x2,x0,2",
                        "addi x3,x0,3",
                        "addi x4,x0,4",
                        "addi x5,x0,5",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )
            (case / "trace.csv").write_text(
                "\n".join(
                    [
                        "1,0000,0000,0000,0000,0000",
                        "2,0004,0000,0000,0000,0000",
                        "3,0008,0004,0000,0000,0000",
                        "4,000c,0008,0004,0000,0000",
                        "5,0010,000c,0008,0004,0000",
                        # Once every stage has filled, PC zero is real trace data.
                        "6,0000,0000,0000,0000,0000",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )

            payload = pipeline_timing_diagram.load_test(tests_dir, 1)

        cycles = payload["cycles"]
        self.assertIsNotNone(cycles[0]["if"])
        self.assertIsNone(cycles[0]["id"])
        self.assertIsNone(cycles[0]["ex"])
        self.assertIsNone(cycles[0]["mem"])
        self.assertIsNone(cycles[0]["wb"])
        self.assertIsNotNone(cycles[1]["id"])
        self.assertIsNone(cycles[1]["ex"])
        self.assertIsNotNone(cycles[2]["ex"])
        self.assertIsNone(cycles[2]["mem"])
        self.assertIsNotNone(cycles[3]["mem"])
        self.assertIsNone(cycles[3]["wb"])
        self.assertIsNotNone(cycles[4]["wb"])

        first_instruction = payload["timing"][0]
        self.assertEqual(first_instruction["cells"][1], ["IF"])
        self.assertEqual(first_instruction["cells"][2], ["ID"])
        self.assertEqual(first_instruction["cells"][3], ["EX"])
        self.assertEqual(first_instruction["cells"][4], ["MEM"])
        self.assertEqual(first_instruction["cells"][5], ["WB"])
        self.assertEqual(first_instruction["cells"][6], ["IF", "ID", "EX", "MEM", "WB"])


if __name__ == "__main__":
    unittest.main()
