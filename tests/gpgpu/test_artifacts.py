from __future__ import annotations

import hashlib
import shutil
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from tools.gpgpu.artifacts import artifact_dir, read_artifact_status
from tools.gpgpu.config import ConfigResolver
from tools.gpgpu.planner import Planner


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
        output = self.directory / "nbody.elf"
        output.write_text("elf contents\n", encoding="utf-8")
        input_file = ROOT / "sw" / "programs" / "nbody" / "nbody.c"
        output_hash = hashlib.sha256(output.read_bytes()).hexdigest()
        input_hash = hashlib.sha256(input_file.read_bytes()).hexdigest()
        self.write_metadata(
            "\n".join(
                [
                    "[produced]",
                    'files = ["nbody.elf"]',
                    "",
                    "[output_hashes]",
                    f'"nbody.elf" = "sha256:{output_hash}"',
                    "",
                    "[input_hashes]",
                    f'"sw/programs/nbody/nbody.c" = "sha256:{input_hash}"',
                ]
            )
        )
        return output, input_file

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
        output = image_dir / "nbody_instructions.mem"
        output.write_text("mem contents\n", encoding="utf-8")
        input_file = ROOT / "sw" / "programs" / "nbody" / "nbody.c"
        output_hash = hashlib.sha256(output.read_bytes()).hexdigest()
        input_hash = hashlib.sha256(input_file.read_bytes()).hexdigest()
        (image_dir / "artifact.toml").write_text(
            "\n".join(
                [
                    f'goal = "{image_node.goal_id}"',
                    f'identity = "{image_node.identity}"',
                    "",
                    "[produced]",
                    'files = ["nbody_instructions.mem"]',
                    "",
                    "[output_hashes]",
                    f'"nbody_instructions.mem" = "sha256:{output_hash}"',
                    "",
                    "[input_hashes]",
                    f'"sw/programs/nbody/nbody.c" = "sha256:{input_hash}"',
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
