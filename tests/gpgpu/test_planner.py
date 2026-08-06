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

    def test_profile_overrides_selected_manifest_defaults(self):
        config = ConfigResolver().resolve(profile="zed-demo")
        self.assertEqual(config.get("program.optimization"), "O2")
        self.assertIn("profiles.toml:profiles.zed-demo", config.provenance_for("program.optimization").source)

    def test_variant_is_not_part_of_initial_schema(self):
        config = ConfigResolver().resolve(profile="zed-demo")
        keys = {key for key, _, _ in config.normalized_items()}
        self.assertNotIn("variant", keys)
        with self.assertRaisesRegex(ConfigError, "Unknown setting"):
            ConfigResolver().resolve(set_values=["variant=debug"])

    def test_file_backed_profile_loads_with_provenance(self):
        config = ConfigResolver().resolve(profile="zed-demo", set_values=["demo.fps=30"])
        self.assertEqual(config.get("program"), "nbody-3d")
        self.assertEqual(config.get("backend"), "fpga-uart")
        self.assertEqual(config.get("demo.dataset"), "rings")
        self.assertIn("config/gpgpu/profiles.toml:profiles.zed-demo", config.provenance_for("backend").source)
        self.assertIn("config/gpgpu/profiles.toml:profiles.zed-demo", config.provenance_for("program.optimization").source)
        provenance = config.provenance_for("demo.fps")
        self.assertEqual(config.get("demo.fps"), 30)
        self.assertEqual(provenance.source, "CLI --set")

    def test_unknown_profile_is_rejected(self):
        with self.assertRaisesRegex(ConfigError, "Unknown profile"):
            ConfigResolver().resolve(profile="missing-profile")

    def test_unknown_manifest_setting_is_rejected(self):
        resolver = ConfigResolver(config_root=ROOT / "tests" / "fixtures" / "bad_gpgpu_unknown")
        with self.assertRaisesRegex(ConfigError, "Unknown setting"):
            resolver.resolve()

    def test_type_invalid_manifest_setting_is_rejected(self):
        resolver = ConfigResolver(config_root=ROOT / "tests" / "fixtures" / "bad_gpgpu_type")
        with self.assertRaisesRegex(ConfigError, "expected integer"):
            resolver.resolve()

    def test_local_board_config_is_optional_and_gitignored(self):
        config = ConfigResolver().resolve(profile="zed-demo")
        self.assertEqual(config.get("board.port"), "/dev/ttyACM0")
        self.assertIn("local.example.toml", config.provenance_for("board.port").source)
        self.assertTrue((ROOT / "config" / "gpgpu" / "local.example.toml").exists())
        gitignore = (ROOT / ".gitignore").read_text()
        self.assertIn("config/gpgpu/local.toml", gitignore)

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

    def test_local_wrapper_cli_executes_list(self):
        import subprocess

        result = subprocess.run(
            [str(ROOT / "tools" / "gpgpu" / "gpgpu"), "list"],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("demo.run", result.stdout)
        self.assertIn("hw.board.bitstream", result.stdout)

    def test_cli_can_render_colorized_output(self):
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            code = main(["--color", "always", "list"])
        self.assertEqual(code, 0)
        rendered = stdout.getvalue()
        self.assertIn("\x1b[", rendered)
        self.assertIn("●", rendered)
        self.assertIn("demo.run", rendered)

    def test_cli_plain_output_stays_machine_readable(self):
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            code = main(["--color", "never", "plan", "demo.run", "--profile", "zed-demo"])
        self.assertEqual(code, 0)
        rendered = stdout.getvalue()
        self.assertNotIn("\x1b[", rendered)
        self.assertIn("BUILD", rendered)
        self.assertIn("SERVICE", rendered)


if __name__ == "__main__":
    unittest.main()
