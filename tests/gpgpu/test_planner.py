import contextlib
import io
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from tools.gpgpu.cli import main
from tools.gpgpu.config import ConfigError, ConfigResolver
from tools.gpgpu.planner import Planner


class PlannerFoundationTests(unittest.TestCase):
    def make_planner(self, *sets):
        config = ConfigResolver().resolve(profile=None, set_values=list(sets))
        return Planner(config)

    def test_runtime_options_do_not_change_native_program_identity(self):
        slow = self.make_planner("demo.fps=12", "demo=nbody-3d", "backend=fake")
        fast = self.make_planner("demo.fps=60", "demo=nbody-3d", "backend=fake")

        slow_image = slow.plan("demo.run").require_instance("sw.program.native")
        fast_image = fast.plan("demo.run").require_instance("sw.program.native")

        self.assertEqual(slow_image.identity, fast_image.identity)

    def test_artifact_affecting_options_change_program_image_identity(self):
        o2 = self.make_planner("program.optimization=O2")
        o3 = self.make_planner("program.optimization=O3")

        self.assertNotEqual(
            o2.plan("sw.program.image").root.identity,
            o3.plan("sw.program.image").root.identity,
        )

    def test_unknown_settings_are_rejected(self):
        with self.assertRaisesRegex(ConfigError, "Unknown setting"):
            ConfigResolver().resolve(set_values=["fpga.unknown=1"])

    def test_type_invalid_settings_are_rejected(self):
        with self.assertRaisesRegex(ConfigError, "expected integer"):
            ConfigResolver().resolve(set_values=["demo.fps=fast"])

    def test_configuration_precedence_is_deterministic(self):
        resolver = ConfigResolver()
        a = resolver.resolve(profile="zed-demo", set_values=["demo.fps=30"])
        b = resolver.resolve(profile="zed-demo", set_values=["demo.fps=30"])
        self.assertEqual(a.normalized_items(), b.normalized_items())
        self.assertEqual(a.get("demo.fps"), 30)

    def test_configuration_provenance_is_reported(self):
        config = ConfigResolver().resolve(profile="zed-demo", set_values=["demo.fps=30"])
        provenance = config.provenance_for("demo.fps")
        self.assertEqual(config.get("demo.fps"), 30)
        self.assertEqual(provenance.source, "CLI --set")

    def test_identical_dependency_instances_are_deduplicated(self):
        plan = self.make_planner("backend=fpga-uart").plan("demo.run")
        bitstreams = [node for node in plan.nodes if node.goal_id == "hw.board.bitstream"]
        self.assertEqual(len(bitstreams), 1)

    def test_artifact_goals_are_cacheable(self):
        node = self.make_planner().plan("sw.program.image").root
        self.assertEqual(node.kind, "artifact")
        self.assertTrue(node.cacheable)

    def test_action_goals_are_not_cacheable(self):
        node = self.make_planner().plan("hw.board.program").root
        self.assertEqual(node.kind, "action")
        self.assertFalse(node.cacheable)

    def test_service_goals_have_lifecycle_classification(self):
        node = self.make_planner("demo=nbody-3d").plan("demo.run").root
        self.assertEqual(node.kind, "service")
        self.assertEqual(node.lifecycle, "long-running")

    def test_fake_demo_adds_no_fpga_dependencies(self):
        plan = self.make_planner("demo=nbody-3d", "backend=fake").plan("demo.run")
        goal_ids = {node.goal_id for node in plan.nodes}
        self.assertIn("sw.program.native", goal_ids)
        self.assertNotIn("hw.board.bitstream", goal_ids)
        self.assertNotIn("hw.board.program", goal_ids)
        self.assertNotIn("hw.board.kernel.load", goal_ids)

    def test_fpga_demo_includes_fpga_and_kernel_dependencies(self):
        plan = self.make_planner("demo=nbody-3d", "backend=fpga-uart").plan("demo.run")
        goal_ids = {node.goal_id for node in plan.nodes}
        self.assertIn("hw.board.bitstream", goal_ids)
        self.assertIn("hw.board.program", goal_ids)
        self.assertIn("sw.program.image", goal_ids)
        self.assertIn("hw.board.kernel.load", goal_ids)

    def test_public_and_internal_goal_visibility_works(self):
        planner = self.make_planner()
        public_ids = {goal.goal_id for goal in planner.list_goals(include_internal=False)}
        all_ids = {goal.goal_id for goal in planner.list_goals(include_internal=True)}
        self.assertIn("demo.run", public_ids)
        self.assertNotIn("sw.program.compile_riscv", public_ids)
        self.assertIn("sw.program.compile_riscv", all_ids)
        self.assertNotIn("demo.nbody3d", all_ids)

    def test_plan_output_is_deterministic(self):
        first = self.make_planner("backend=fpga-uart").plan("demo.run").format_plan()
        second = self.make_planner("backend=fpga-uart").plan("demo.run").format_plan()
        self.assertEqual(first, second)

    def test_cli_list_plan_and_explain(self):
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            code = main(["list"])
        self.assertEqual(code, 0)
        self.assertIn("demo.run", stdout.getvalue())

        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            code = main(["plan", "demo.run", "--set", "demo=nbody-3d", "--set", "backend=fake"])
        self.assertEqual(code, 0)
        self.assertIn("SERVICE", stdout.getvalue())
        self.assertNotIn("hw.board.bitstream", stdout.getvalue())

        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            code = main(["explain", "demo.run", "--profile", "zed-demo", "--set", "demo.fps=30"])
        self.assertEqual(code, 0)
        self.assertIn("Configuration provenance", stdout.getvalue())
        self.assertIn("demo.fps", stdout.getvalue())
        self.assertIn("CLI --set", stdout.getvalue())


if __name__ == "__main__":
    unittest.main()
