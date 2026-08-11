from __future__ import annotations

import hashlib
import json
import shutil
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from tools.gpgpu.artifacts import artifact_dir, read_artifact_status, resolve_artifact_inputs, resolve_artifact_outputs
from tools.gpgpu.config import ConfigResolver
from tools.gpgpu.planner import Planner


def _sha256_for_test(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


class ArtifactValidationTests(unittest.TestCase):
    def setUp(self):
        self.config = ConfigResolver().resolve(set_values=["program=nbody"])
        self.node = Planner(self.config, repo_root=ROOT).plan("sw.program.elf").root
        self.directory = artifact_dir(ROOT, self.node)
        shutil.rmtree(ROOT / "out" / "artifacts" / "sw.program.elf", ignore_errors=True)
        self.directory.mkdir(parents=True, exist_ok=True)

    def tearDown(self):
        shutil.rmtree(ROOT / "out" / "artifacts" / "sw.program.elf", ignore_errors=True)
        input_file = ROOT / "sw" / "programs" / "nbody" / "nbody.c"
        if hasattr(self, "_input_snapshot"):
            input_file.write_text(self._input_snapshot, encoding="utf-8")

    def write_metadata(self, extra: str = "") -> None:
        (self.directory / "artifact.toml").write_text(
            "\n".join(
                [
                    f'goal = "{self.node.goal_id}"',
                    f'kind = "{self.node.kind}"',
                    f'identity = "{self.node.identity}"',
                    "cacheable = true",
                    "public = true",
                    f'description = "{self.node.description}"',
                    extra,
                    "",
                ]
            ),
            encoding="utf-8",
        )

    def write_validated_metadata(self) -> tuple[Path, Path]:
        outputs = resolve_artifact_outputs(self.directory, self.node, self.config)
        input_paths = resolve_artifact_inputs(ROOT, self.node, self.config)
        for output in outputs:
            output.write_text(f"contents for {output.name}\n", encoding="utf-8")
        self.write_metadata(
            "\n".join(
                [
                    "[produced]",
                    "files = [" + ", ".join(json.dumps(path.relative_to(self.directory).as_posix()) for path in outputs) + "]",
                    "",
                    "[output_hashes]",
                    *[
                        f'{json.dumps(path.relative_to(self.directory).as_posix())} = "{_sha256_for_test(path)}"'
                        for path in outputs
                    ],
                    "",
                    "[input_hashes]",
                    *[
                        f'{json.dumps(path.relative_to(ROOT).as_posix())} = "{_sha256_for_test(path)}"'
                        for path in input_paths
                    ],
                ]
            )
        )
        source_under_test = next(path for path in input_paths if path.relative_to(ROOT).as_posix() == "sw/programs/nbody/nbody.c")
        return outputs[0], source_under_test

    def test_goal_identity_only_metadata_is_unknown_and_compact_miss(self):
        self.write_metadata()

        status = read_artifact_status(ROOT, self.node)
        rendered = Planner(self.config, repo_root=ROOT).plan("sw.program.elf").format_plan(verbose=True)

        self.assertEqual(status.state, "unknown")
        self.assertFalse(status.is_hit)
        self.assertIn("CACHE MISS", rendered)
        self.assertIn("↳ cache       unknown", rendered)
        self.assertIn("metadata lacks validation hashes", rendered)

    def test_matching_output_and_input_hashes_are_a_hit(self):
        self.write_validated_metadata()

        status = read_artifact_status(ROOT, self.node)

        self.assertEqual(status.state, "hit")
        self.assertTrue(status.is_hit)

    def test_artifact_inputs_resolve_from_declarative_spec(self):
        inputs = resolve_artifact_inputs(ROOT, self.node, self.config)
        relative = {path.relative_to(ROOT).as_posix() for path in inputs}

        self.assertIn("sw/programs/Makefile", relative)
        self.assertIn("sw/programs/nbody/nbody.c", relative)
        self.assertIn("sw/programs/nbody/fpga.py", relative)

    def test_artifact_outputs_resolve_from_declarative_spec(self):
        outputs = resolve_artifact_outputs(self.directory, self.node, self.config)
        relative = {path.relative_to(self.directory).as_posix() for path in outputs}

        self.assertEqual(relative, {"nbody.elf", "nbody.map"})

    def test_new_matching_input_file_makes_old_metadata_stale(self):
        self.write_validated_metadata()
        extra = ROOT / "sw" / "programs" / "nbody" / "cache_validation_extra.c"
        try:
            extra.write_text("int cache_validation_extra(void) { return 0; }\n", encoding="utf-8")
            status = read_artifact_status(ROOT, self.node)
        finally:
            extra.unlink(missing_ok=True)

        self.assertEqual(status.state, "stale")
        self.assertIn("input set changed", status.reason)

    def test_missing_declared_output_is_incomplete_even_if_metadata_omits_it(self):
        output = self.directory / "nbody.elf"
        output.write_text("elf contents\n", encoding="utf-8")
        input_paths = resolve_artifact_inputs(ROOT, self.node, self.config)
        self.write_metadata(
            "\n".join(
                [
                    "[produced]",
                    'files = ["nbody.elf"]',
                    "",
                    "[output_hashes]",
                    f'"nbody.elf" = "{_sha256_for_test(output)}"',
                    "",
                    "[input_hashes]",
                    *[
                        f'{json.dumps(path.relative_to(ROOT).as_posix())} = "{_sha256_for_test(path)}"'
                        for path in input_paths
                    ],
                ]
            )
        )
        status = read_artifact_status(ROOT, self.node)
        self.assertEqual(status.state, "incomplete")
        self.assertIn("missing output: nbody.map", status.reason)
        self.assertTrue(output.exists())

    def test_executor_no_longer_owns_transitional_input_selector(self):
        from tools.gpgpu.executor import Executor

        self.assertFalse(hasattr(Executor, "_input_paths_for"))

    def test_absolute_artifact_spec_path_is_rejected(self):
        from tools.gpgpu.goals import GoalConfigError, load_goals

        fixture = ROOT / "tests" / "fixtures" / "bad_gpgpu_goal_absolute_artifact_path" / "goals.toml"
        with self.assertRaisesRegex(GoalConfigError, "artifact paths must be repository-relative"):
            load_goals(fixture, schema=ConfigResolver.SCHEMA)

    def test_unknown_artifact_placeholder_is_rejected(self):
        from tools.gpgpu.goals import GoalConfigError, load_goals

        fixture = ROOT / "tests" / "fixtures" / "bad_gpgpu_goal_unknown_placeholder" / "goals.toml"
        with self.assertRaisesRegex(GoalConfigError, "Unknown artifact placeholder"):
            load_goals(fixture, schema=ConfigResolver.SCHEMA)

    def test_missing_produced_file_is_incomplete_and_compact_miss(self):
        output, _ = self.write_validated_metadata()
        output.unlink()

        status = read_artifact_status(ROOT, self.node)
        rendered = Planner(self.config, repo_root=ROOT).plan("sw.program.elf").format_plan(verbose=True)

        self.assertEqual(status.state, "incomplete")
        self.assertFalse(status.is_hit)
        self.assertIn("CACHE MISS", rendered)
        self.assertIn("missing output: nbody.elf", rendered)

    def test_changed_output_hash_is_invalid_and_compact_miss(self):
        output, _ = self.write_validated_metadata()
        output.write_text("changed output\n", encoding="utf-8")

        status = read_artifact_status(ROOT, self.node)
        rendered = Planner(self.config, repo_root=ROOT).plan("sw.program.elf").format_plan(verbose=True)

        self.assertEqual(status.state, "invalid")
        self.assertFalse(status.is_hit)
        self.assertIn("CACHE MISS", rendered)
        self.assertIn("output hash mismatch: nbody.elf", rendered)

    def test_changed_input_hash_is_stale_and_compact_miss(self):
        _, input_file = self.write_validated_metadata()
        self._input_snapshot = input_file.read_text(encoding="utf-8")
        input_file.write_text(self._input_snapshot + "\n/* cache validation test */\n", encoding="utf-8")

        status = read_artifact_status(ROOT, self.node)
        rendered = Planner(self.config, repo_root=ROOT).plan("sw.program.elf").format_plan(verbose=True)

        self.assertEqual(status.state, "stale")
        self.assertFalse(status.is_hit)
        self.assertIn("CACHE MISS", rendered)
        self.assertIn("input changed: sw/programs/nbody/nbody.c", rendered)

    def test_dependency_identity_mismatch_is_stale_and_compact_miss(self):
        image_node = Planner(self.config, repo_root=ROOT).plan("sw.program.image").root
        image_dir = artifact_dir(ROOT, image_node)
        shutil.rmtree(ROOT / "out" / "artifacts" / "sw.program.image", ignore_errors=True)
        image_dir.mkdir(parents=True, exist_ok=True)
        outputs = resolve_artifact_outputs(image_dir, image_node, self.config)
        for output in outputs:
            output.write_text(f"contents for {output.name}\n", encoding="utf-8")
        input_paths = resolve_artifact_inputs(ROOT, image_node, self.config)
        (image_dir / "artifact.toml").write_text(
            "\n".join(
                [
                    f'goal = "{image_node.goal_id}"',
                    f'identity = "{image_node.identity}"',
                    "",
                    "[produced]",
                    "files = [" + ", ".join(json.dumps(path.relative_to(image_dir).as_posix()) for path in outputs) + "]",
                    "",
                    "[output_hashes]",
                    *[
                        f'{json.dumps(path.relative_to(image_dir).as_posix())} = "{_sha256_for_test(path)}"'
                        for path in outputs
                    ],
                    "",
                    "[input_hashes]",
                    *[
                        f'{json.dumps(path.relative_to(ROOT).as_posix())} = "{_sha256_for_test(path)}"'
                        for path in input_paths
                    ],
                    "",
                    "[dependencies]",
                    '"sw.program.elf" = "wrong-identity"',
                    "",
                ]
            ),
            encoding="utf-8",
        )
        try:
            status = read_artifact_status(ROOT, image_node)
            rendered = Planner(self.config, repo_root=ROOT).plan("sw.program.image").format_plan(verbose=True)
        finally:
            shutil.rmtree(ROOT / "out" / "artifacts" / "sw.program.image", ignore_errors=True)

        self.assertEqual(status.state, "stale")
        self.assertFalse(status.is_hit)
        self.assertIn("CACHE MISS", rendered)
        self.assertIn("dependency identity changed: sw.program.elf", rendered)


if __name__ == "__main__":
    unittest.main()
