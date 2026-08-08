from __future__ import annotations

import contextlib
import io
import shutil
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from tools.gpgpu.artifacts import artifact_dir
from tools.gpgpu.cli import main
from tools.gpgpu.config import ConfigResolver
from tools.gpgpu.planner import Planner


class CleanerTests(unittest.TestCase):
    def setUp(self):
        shutil.rmtree(ROOT / "out" / "artifacts" / "sw.program.native", ignore_errors=True)
        shutil.rmtree(ROOT / "out" / "artifacts" / "sw.program.elf", ignore_errors=True)
        shutil.rmtree(ROOT / "out" / "artifacts" / "sw.program.image", ignore_errors=True)
        shutil.rmtree(ROOT / "out" / "artifacts" / "unsafe.test", ignore_errors=True)

    def tearDown(self):
        self.setUp()

    def config(self, *set_values: str):
        return ConfigResolver().resolve(set_values=["program=nbody", *set_values])

    def plan(self, goal_id: str, *set_values: str):
        return Planner(self.config(*set_values)).plan(goal_id)

    def make_artifact_dir(self, goal_id: str) -> Path:
        plan = self.plan(goal_id)
        path = artifact_dir(ROOT, plan.root)
        path.mkdir(parents=True, exist_ok=True)
        (path / "marker.txt").write_text("keep", encoding="utf-8")
        return path

    def test_clean_dry_run_reports_root_artifact_without_deleting(self):
        from tools.gpgpu.cleaner import Cleaner

        plan = self.plan("sw.program.image")
        path = artifact_dir(ROOT, plan.root)
        path.mkdir(parents=True)
        marker = path / "marker.txt"
        marker.write_text("keep", encoding="utf-8")

        summary = Cleaner(repo_root=ROOT).clean_plan(plan, dry_run=True)

        self.assertTrue(marker.exists())
        self.assertEqual([(record.node.goal_id, record.status, record.path) for record in summary.records], [
            ("sw.program.image", "would-remove", path),
        ])

    def test_clean_reports_missing_root_artifact_as_non_error(self):
        from tools.gpgpu.cleaner import Cleaner

        plan = self.plan("sw.program.image")
        path = artifact_dir(ROOT, plan.root)

        summary = Cleaner(repo_root=ROOT).clean_plan(plan)

        self.assertFalse(path.exists())
        self.assertEqual(summary.records[0].status, "missing")
        self.assertEqual(summary.records[0].path, path)

    def test_clean_removes_root_artifact_directory(self):
        from tools.gpgpu.cleaner import Cleaner

        plan = self.plan("sw.program.image")
        path = artifact_dir(ROOT, plan.root)
        path.mkdir(parents=True)
        (path / "marker.txt").write_text("delete", encoding="utf-8")

        summary = Cleaner(repo_root=ROOT).clean_plan(plan)

        self.assertFalse(path.exists())
        self.assertEqual(summary.records[0].status, "removed")

    def test_clean_refuses_broad_and_outside_paths(self):
        from tools.gpgpu.cleaner import CleanError, Cleaner

        cleaner = Cleaner(repo_root=ROOT)
        broad_paths = [
            ROOT / "out",
            ROOT / "out" / "artifacts",
            ROOT / "out" / "artifacts" / "sw.program.image",
        ]
        for path in broad_paths:
            with self.subTest(path=path):
                with self.assertRaisesRegex(CleanError, "broad artifact path"):
                    cleaner._assert_safe_artifact_path(path)
        with self.assertRaisesRegex(CleanError, "outside out/artifacts"):
            cleaner._assert_safe_artifact_path(ROOT / "sw" / "programs" / "nbody")

    def test_clean_refuses_symlink_artifact_directory(self):
        from tools.gpgpu.cleaner import CleanError, Cleaner

        plan = self.plan("sw.program.image")
        path = artifact_dir(ROOT, plan.root)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.symlink_to(ROOT / "sw" / "programs", target_is_directory=True)

        with self.assertRaisesRegex(CleanError, "symlink artifact path"):
            Cleaner(repo_root=ROOT).clean_plan(plan)

    def test_clean_with_deps_selects_artifact_dependencies_in_plan_order(self):
        from tools.gpgpu.cleaner import Cleaner

        plan = self.plan("sw.program.image")
        summary = Cleaner(repo_root=ROOT).clean_plan(plan, deps=True, dry_run=True)

        self.assertEqual([record.node.goal_id for record in summary.records], ["sw.program.elf", "sw.program.image"])

    def test_clean_non_artifact_root_without_deps_errors(self):
        from tools.gpgpu.cleaner import CleanError, Cleaner

        config = ConfigResolver().resolve(set_values=["demo=nbody-3d", "backend=fake"])
        plan = Planner(config).plan("demo.run")

        with self.assertRaisesRegex(CleanError, "artifact goals only"):
            Cleaner(repo_root=ROOT).clean_plan(plan)

    def test_clean_demo_with_deps_cleans_artifact_dependencies_only(self):
        from tools.gpgpu.cleaner import Cleaner

        config = ConfigResolver().resolve(set_values=["demo=nbody-3d", "backend=fake"])
        plan = Planner(config).plan("demo.run")

        summary = Cleaner(repo_root=ROOT).clean_plan(plan, deps=True, dry_run=True)

        self.assertEqual([record.node.goal_id for record in summary.records], ["sw.program.native"])

    def test_format_clean_summary_reports_dry_run_counts(self):
        from tools.gpgpu.cleaner import Cleaner, format_clean_summary

        plan = self.plan("sw.program.image")
        artifact_dir(ROOT, plan.root).mkdir(parents=True)
        summary = Cleaner(repo_root=ROOT).clean_plan(plan, dry_run=True)

        rendered = format_clean_summary(summary, dry_run=True, deps=False, repo_root=ROOT)

        self.assertIn("Clean: sw.program.image", rendered)
        self.assertIn("Mode: dry-run root-only", rendered)
        self.assertIn("WOULD REMOVE", rendered)
        self.assertIn("out/artifacts/sw.program.image/", rendered)
        self.assertNotIn("out/artifacts/sw.program.image/nbody/", rendered)
        self.assertIn("would-remove: 1", rendered)

    def test_cli_clean_dry_run_reports_without_deleting(self):
        plan = self.plan("sw.program.image")
        path = artifact_dir(ROOT, plan.root)
        path.mkdir(parents=True)
        marker = path / "marker.txt"
        marker.write_text("keep", encoding="utf-8")

        stdout = io.StringIO()
        stderr = io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            code = main(["--color", "never", "clean", "sw.program.image", "--dry-run", "--set", "program=nbody"])

        self.assertEqual(code, 0, stderr.getvalue() + stdout.getvalue())
        self.assertTrue(marker.exists())
        self.assertIn("WOULD REMOVE", stdout.getvalue())

    def test_cli_clean_removes_owned_artifact_directory(self):
        path = self.make_artifact_dir("sw.program.image")

        stdout = io.StringIO()
        stderr = io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            code = main(["--color", "never", "clean", "sw.program.image", "--set", "program=nbody"])

        self.assertEqual(code, 0, stderr.getvalue() + stdout.getvalue())
        self.assertFalse(path.exists())
        self.assertIn("REMOVED", stdout.getvalue())

    def test_cli_clean_unknown_goal_returns_error(self):
        stdout = io.StringIO()
        stderr = io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            code = main(["--color", "never", "clean", "no.such.goal", "--dry-run"])

        self.assertEqual(code, 2)
        self.assertEqual(stdout.getvalue(), "")
        self.assertIn("Unknown goal", stderr.getvalue())


if __name__ == "__main__":
    unittest.main()
