import contextlib
import hashlib
import io
import json
import shutil
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

    def tearDown(self):
        for goal_id in ("sw.program.native", "sw.program.elf", "sw.program.image"):
            shutil.rmtree(ROOT / "out" / "artifacts" / goal_id, ignore_errors=True)

    def write_metadata(self, node, *, goal_id=None, identity=None):
        from tools.gpgpu.artifacts import artifact_dir

        directory = artifact_dir(ROOT, node)
        directory.mkdir(parents=True, exist_ok=True)
        (directory / "artifact.toml").write_text(
            "\n".join(
                [
                    f'goal = "{goal_id or node.goal_id}"',
                    f'kind = "{node.kind}"',
                    f'identity = "{identity or node.identity}"',
                    "cacheable = true",
                    "public = true",
                    f'description = "{node.description}"',
                    "",
                ]
            ),
            encoding="utf-8",
        )
        return directory

    def write_validated_metadata(self, node):
        directory = self.write_metadata(node)
        output = directory / "validated.out"
        output.write_text("validated output\n", encoding="utf-8")
        input_path = ROOT / "sw" / "programs" / "nbody" / "nbody.c"
        output_hash = hashlib.sha256(output.read_bytes()).hexdigest()
        input_hash = hashlib.sha256(input_path.read_bytes()).hexdigest()
        with (directory / "artifact.toml").open("a", encoding="utf-8") as handle:
            handle.write("[produced]\n")
            handle.write('files = ["validated.out"]\n\n')
            handle.write("[output_hashes]\n")
            handle.write(f'"validated.out" = "sha256:{output_hash}"\n\n')
            handle.write("[input_hashes]\n")
            handle.write(f'"sw/programs/nbody/nbody.c" = "sha256:{input_hash}"\n')
        return directory

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
        self.assertIn("profiles/zed-demo.toml:profile", config.provenance_for("program.optimization").source)

    def test_manifest_selectors_are_declared_in_schema(self):
        manifest_selectors = {
            key: spec.manifest_dir
            for key, spec in ConfigResolver.SCHEMA.items()
            if spec.manifest_dir is not None
        }
        self.assertEqual(
            manifest_selectors,
            {
                "architecture": "architectures",
                "board_type": "board_types",
                "program": "programs",
                "demo": "demos",
            },
        )

    def test_cli_selection_override_reloads_selected_program_manifest_defaults(self):
        config = ConfigResolver().resolve(set_values=["program=nbody"])

        self.assertEqual(config.get("program"), "nbody")
        self.assertEqual(config.get("program.optimization"), "O2")
        self.assertIn("config/gpgpu/programs/nbody.toml:defaults", config.provenance_for("program.optimization").source)

    def test_cli_specific_setting_override_wins_after_selection_manifest_defaults(self):
        config = ConfigResolver().resolve(set_values=["program=nbody", "program.optimization=O3"])

        self.assertEqual(config.get("program"), "nbody")
        self.assertEqual(config.get("program.optimization"), "O3")
        self.assertEqual(config.provenance_for("program.optimization").source, "CLI --set")

    def test_variant_is_not_part_of_initial_schema(self):
        config = ConfigResolver().resolve(profile="zed-demo")
        keys = {key for key, _, _ in config.normalized_items()}
        self.assertNotIn("variant", keys)
        with self.assertRaisesRegex(ConfigError, "Unknown setting"):
            ConfigResolver().resolve(set_values=["variant=debug"])

    def test_file_backed_profile_loads_with_provenance(self):
        config = ConfigResolver().resolve(profile="zed-demo", set_values=["demo.fps=30"])
        self.assertEqual(config.get("program"), "nbody-3d")
        self.assertEqual(config.get("board_type"), "zynq7000-zedboard")
        self.assertEqual(config.get("board"), "zedboard")
        self.assertEqual(config.get("backend"), "fpga-uart")
        self.assertEqual(config.get("demo.dataset"), "rings")
        self.assertIn("config/gpgpu/profiles/zed-demo.toml:profile", config.provenance_for("backend").source)
        self.assertIn("config/gpgpu/profiles/zed-demo.toml:profile", config.provenance_for("program.optimization").source)
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
        self.assertEqual(config.get("board"), "zedboard")
        self.assertIn("local: config/gpgpu/local.example.toml", config.provenance_for("board").source)
        self.assertIn("local: config/gpgpu/local.example.toml", config.provenance_for("board.port").source)
        self.assertTrue((ROOT / "config" / "gpgpu" / "local.example.toml").exists())
        gitignore = (ROOT / ".gitignore").read_text()
        self.assertIn("config/gpgpu/local.toml", gitignore)
        self.assertIn("docs/migration/CONFIGURATION.md", gitignore)

    def test_approved_config_cleanup_shape(self):
        config_root = ROOT / "config" / "gpgpu"
        self.assertTrue((config_root / "defaults.toml").exists())
        self.assertFalse((config_root / "components.toml").exists())
        self.assertTrue((config_root / "board_types" / "zynq7000-zedboard.toml").exists())
        self.assertFalse((config_root / "platforms").exists())
        self.assertTrue((config_root / "profiles" / "zed-demo.toml").exists())
        self.assertFalse((config_root / "profiles.toml").exists())

        config = ConfigResolver().resolve(profile="zed-demo")
        self.assertEqual(config.get("board_type"), "zynq7000-zedboard")
        self.assertEqual(config.get("board"), "zedboard")
        self.assertEqual(config.get("fpga.part"), "xc7z020clg484-1")
        with self.assertRaisesRegex(ConfigError, "Unknown setting"):
            config.get("platform")

    def test_kernel_calls_stays_for_future_kernel_run(self):
        config = ConfigResolver().resolve(set_values=["kernel.kernel_calls=3"])
        self.assertEqual(config.get("kernel.kernel_calls"), 3)
        node = Planner(config).plan("hw.board.kernel.run").root
        self.assertIn(("kernel.kernel_calls", 3), node.params)

    def test_goal_dependencies_are_declared_on_goal_definitions(self):
        from tools.gpgpu.goals import GOALS

        image_deps = GOALS["sw.program.image"].dependencies
        self.assertEqual(tuple(dep.goal_id for dep in image_deps), ("sw.program.elf",))
        self.assertEqual(image_deps[0].role, "elf")

        kernel_load_deps = GOALS["hw.board.kernel.load"].dependencies
        self.assertEqual(
            tuple(dep.goal_id for dep in kernel_load_deps),
            ("hw.board.program", "sw.program.image"),
        )
        self.assertEqual(tuple(dep.role for dep in kernel_load_deps), ("configured_board", "program_image"))

    def test_demo_dependencies_are_conditional_declarations(self):
        from tools.gpgpu.goals import GOALS

        declared = {(dep.goal_id, dep.when) for dep in GOALS["demo.run"].dependencies}
        self.assertIn(("sw.program.native", (("backend", "fake"),)), declared)
        self.assertIn(("hw.board.kernel.load", (("backend", "fpga-uart"),)), declared)

    def test_compile_riscv_placeholder_is_not_a_goal_boundary(self):
        from tools.gpgpu.goals import GOALS

        self.assertNotIn("sw.program.compile_riscv", GOALS)
        plan = self.make_planner().plan("sw.program.elf")
        self.assertEqual([node.goal_id for node in plan.nodes], ["sw.program.elf"])

    def test_goal_parameter_scopes_are_consistent_with_schema(self):
        from tools.gpgpu.config import ConfigResolver
        from tools.gpgpu.goals import GOALS

        for goal in GOALS.values():
            for name in goal.artifact_params:
                self.assertIn(ConfigResolver.SCHEMA[name].scope, {"artifact", "shared"}, f"{goal.goal_id}:{name}")
            for name in goal.runtime_params:
                self.assertIn(
                    ConfigResolver.SCHEMA[name].scope,
                    {"runtime", "machine-local", "shared"},
                    f"{goal.goal_id}:{name}",
                )

    def test_no_fake_test_settings_are_added_yet(self):
        with self.assertRaisesRegex(ConfigError, "Unknown setting"):
            ConfigResolver().resolve(set_values=["test.rtl.simulator=iverilog"])

    def test_identical_dependency_instances_are_deduplicated(self):
        plan = self.make_planner("backend=fpga-uart").plan("demo.run")
        bitstreams = [node for node in plan.nodes if node.goal_id == "hw.board.bitstream"]
        self.assertEqual(len(bitstreams), 1)

    def test_artifact_goals_are_cacheable(self):
        node = self.make_planner().plan("sw.program.image").root
        self.assertEqual(node.kind, "artifact")
        self.assertTrue(node.cacheable)

    def test_plan_reports_cache_miss_when_artifact_metadata_is_missing(self):
        config = ConfigResolver().resolve(set_values=["program=nbody"])
        plan = Planner(config, repo_root=ROOT).plan("sw.program.image")

        rendered = plan.format_plan()

        self.assertIn("BUILD    CACHE MISS", rendered)
        self.assertIn("sw.program.elf", rendered)
        self.assertIn("sw.program.image", rendered)

    def test_plan_reports_cache_hit_for_matching_artifact_metadata(self):
        config = ConfigResolver().resolve(set_values=["program=nbody"])
        initial = Planner(config, repo_root=ROOT).plan("sw.program.elf")
        self.write_validated_metadata(initial.root)

        rendered = Planner(config, repo_root=ROOT).plan("sw.program.elf").format_plan()

        self.assertIn("BUILD    CACHE HIT", rendered)
        self.assertNotIn("CACHE MISS", rendered)

    def test_verbose_plan_reports_cache_miss_reason_for_metadata_mismatch(self):
        config = ConfigResolver().resolve(set_values=["program=nbody"])
        initial = Planner(config, repo_root=ROOT).plan("sw.program.elf")
        self.write_metadata(initial.root, identity="wrong-identity")

        rendered = Planner(config, repo_root=ROOT).plan("sw.program.elf").format_plan(verbose=True)

        self.assertIn("CACHE MISS", rendered)
        self.assertIn("↳ cache       invalid", rendered)
        self.assertIn("artifact metadata mismatch", rendered)
        self.assertIn("out/artifacts/sw.program.elf/", rendered)

    def test_non_artifact_goals_do_not_show_compact_cache_status(self):
        rendered = Planner(
            ConfigResolver().resolve(set_values=["demo=nbody-3d", "backend=fake"]),
            repo_root=ROOT,
        ).plan("demo.run").format_plan()

        service_line = next(line for line in rendered.splitlines() if "demo.run" in line and line.startswith("SERVICE"))
        self.assertNotIn("CACHE", service_line)

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
        self.assertNotIn("sw.program.compile_riscv", all_ids)
        self.assertNotIn("demo.nbody3d", all_ids)

    def test_plan_output_is_deterministic(self):
        first = self.make_planner("backend=fpga-uart").plan("demo.run").format_plan()
        second = self.make_planner("backend=fpga-uart").plan("demo.run").format_plan()
        self.assertEqual(first, second)

    def test_default_plan_output_stays_compact(self):
        rendered = Planner(ConfigResolver().resolve(profile="zed-demo")).plan("demo.run").format_plan()
        self.assertIn("Plan: demo.run", rendered)
        self.assertIn("◇ 01.", rendered)
        self.assertIn("BUILD", rendered)
        self.assertIn("+", rendered)
        self.assertNotIn("↳ outputs", rendered)
        self.assertNotIn("↳ effects", rendered)
        self.assertNotIn("INCLUDED", rendered)

    def test_verbose_plan_shows_outputs_side_effects_and_lifecycle(self):
        rendered = Planner(ConfigResolver().resolve(profile="zed-demo")).plan("demo.run").format_plan(verbose=True)
        self.assertIn("↳ outputs      bitstream artifact", rendered)
        self.assertIn("↳ outputs      instruction-memory image artifact", rendered)
        self.assertIn("↳ effects      configure selected board FPGA fabric", rendered)
        self.assertIn("↳ effects      load selected program image into board memory", rendered)
        self.assertIn("↳ lifecycle    long-running", rendered)

    def test_verbose_plan_reports_backend_dependency_notes(self):
        fake = ConfigResolver().resolve(set_values=["backend=fake", "demo=nbody-3d"])
        fake_plan = Planner(fake).plan("demo.run")
        fake_rendered = fake_plan.format_plan(verbose=True)
        self.assertIn("OMITTED", fake_rendered)
        self.assertIn("backend=fake uses native reference path", fake_rendered)
        self.assertIn("hw.board.bitstream", fake_rendered)
        self.assertNotIn("hw.board.bitstream", {node.goal_id for node in fake_plan.nodes})

        fpga_rendered = Planner(ConfigResolver().resolve(profile="zed-demo")).plan("demo.run").format_plan(verbose=True)
        self.assertIn("Notes:", fpga_rendered)
        self.assertIn("INCLUDED", fpga_rendered)
        self.assertIn("backend=fpga-uart requires hardware program-image load", fpga_rendered)

    def test_verbose_explain_shows_artifact_identities(self):
        config = ConfigResolver().resolve(profile="zed-demo")
        rendered = Planner(config).plan("demo.run").format_explain(config, verbose=True)
        self.assertIn("Artifact identities:", rendered)
        self.assertIn("hw.board.bitstream", rendered)
        self.assertIn("sw.program.image", rendered)

    def test_rendering_metadata_does_not_change_artifact_identity(self):
        config = ConfigResolver().resolve(profile="zed-demo")
        plan = Planner(config).plan("demo.run")
        node = plan.require_instance("hw.board.bitstream")
        identity_before = node.identity
        plan.format_plan(verbose=True)
        plan.format_explain(config, verbose=True)
        self.assertEqual(identity_before, plan.require_instance("hw.board.bitstream").identity)

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
        self.assertIn("local: config/gpgpu/local.example.toml", stdout.getvalue())

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

    def test_cli_plan_uses_repo_root_for_cache_paths_outside_repo_cwd(self):
        original_cwd = Path.cwd()
        tmp = ROOT / "out" / "tmp-cli-cwd"
        tmp.mkdir(parents=True, exist_ok=True)
        try:
            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                import os

                os.chdir(tmp)
                code = main([
                    "--color",
                    "never",
                    "plan",
                    "sw.program.elf",
                    "--set",
                    "program=nbody",
                    "--verbose",
                ])
        finally:
            import os

            os.chdir(original_cwd)
            shutil.rmtree(tmp, ignore_errors=True)
        self.assertEqual(code, 0)
        rendered = stdout.getvalue()
        self.assertIn(str(ROOT / "out" / "artifacts" / "sw.program.elf"), rendered)
        self.assertNotIn(str(tmp / "out" / "artifacts"), rendered)

    def test_cli_verbose_flag_enables_full_plan_output(self):
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            code = main(["--color", "never", "plan", "demo.run", "--profile", "zed-demo", "--verbose"])
        self.assertEqual(code, 0)
        rendered = stdout.getvalue()
        self.assertIn("↳ outputs      bitstream artifact", rendered)
        self.assertIn("↳ effects      configure selected board FPGA fabric", rendered)

        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            code = main(["--color", "never", "explain", "demo.run", "--profile", "zed-demo", "-v"])
        self.assertEqual(code, 0)
        self.assertIn("Artifact identities:", stdout.getvalue())


if __name__ == "__main__":
    unittest.main()
