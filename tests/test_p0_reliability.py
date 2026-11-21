from __future__ import annotations

import importlib.util
import json
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import producer  # noqa: E402
import studio_pipeline  # noqa: E402


class P0ReliabilityIntegrationTests(unittest.TestCase):
    def test_generated_kaggle_worker_receives_nonempty_manifest_dict(self):
        """Exercise the real manifest-injection path, then import the generated worker."""
        manifest = {
            "job_id": "p0-integration-job",
            "status": "dispatching",
            "reels": [{
                "reel_id": "reel_01_test",
                "title": "एक छोटी कहानी",
                "beats": [{"scene_index": 1, "video_prompt": "A detailed cinematic prompt."}],
            }],
        }
        with tempfile.TemporaryDirectory() as folder:
            temp_root = Path(folder)
            (temp_root / "scripts").mkdir()
            shutil.copy2(ROOT / "scripts" / "kaggle_gpu_runner.py", temp_root / "scripts" / "kaggle_gpu_runner.py")
            with patch.object(studio_pipeline, "ROOT", temp_root), patch.dict(
                os.environ, {"KAGGLE_USERNAME": "test-owner", "KAGGLE_KERNEL_SLUG": "bsk-test-kernel"}
            ):
                kernel_dir = studio_pipeline.build_kaggle_kernel(manifest)
                generated = kernel_dir / "studio_kaggle.py"
                spec = importlib.util.spec_from_file_location("bsk_generated_worker_p0_test", generated)
                module = importlib.util.module_from_spec(spec)
                assert spec and spec.loader
                spec.loader.exec_module(module)
                self.assertIsInstance(module.MANIFEST, dict)
                self.assertEqual(module.MANIFEST["job_id"], "p0-integration-job")
                self.assertEqual(module.MANIFEST["reels"][0]["reel_id"], "reel_01_test")
                self.assertEqual(module.MANIFEST["reels"][0]["beats"][0]["scene_index"], 1)

    def test_owner_approval_qualifies_only_delivered_qa_passed_reel(self):
        history = {
            "topics": [{
                "title": "आखिरी चिट्ठी",
                "status": "ready_for_manual_publish_not_confirmed_published",
                "reel_id": "reel_01_123456",
                "job_id": "job-123",
                "qa_passed": True,
                "visual_qa_status": "reviewed",
                "motion_diagnostics_status": "passed",
                "metadata_ocr_status": "passed",
                "telegram_delivered": True,
            }]
        }
        result = producer._parse_review_message(
            "/approve title=आखिरी चिट्ठी", history, approved=True
        )
        self.assertTrue(result["weekly_qualification_created"])
        qualification = history["one_reel_qualification"]
        self.assertEqual(qualification["status"], "qualified")
        self.assertIs(qualification["qa_passed"], True)
        self.assertIs(qualification["telegram_delivered"], True)
        self.assertIs(qualification["owner_approved"], True)
        self.assertEqual(qualification["reel_id"], "reel_01_123456")

        lock = {"gpu_benchmark": {"qualified": True, "estimated_3_reel_hours": 5.5}}
        studio_pipeline.require_weekly_qualification(history, lock)

    def test_plan_week_processes_telegram_approval_before_applying_gate(self):
        """Simulate /approve arriving in the same plan-week invocation; do not call APIs."""
        with tempfile.TemporaryDirectory() as folder:
            base = Path(folder)
            pending_path = base / "pending_gpu_job.json"
            pending_path.write_text("{}", encoding="utf-8")
            history_path = base / "history.json"
            history_path.write_text(json.dumps({"topics": [{
                "title": "दरवाज़े पर रखा खाना",
                "status": "ready_for_manual_publish_not_confirmed_published",
                "reel_id": "reel_01_pilot", "job_id": "pilot-job",
                "qa_passed": True, "visual_qa_status": "reviewed",
                "motion_diagnostics_status": "passed", "metadata_ocr_status": "passed",
                "telegram_delivered": True,
            }]}), encoding="utf-8")
            lock_path = base / "toolchain_lock.json"
            lock_path.write_text(json.dumps({"gpu_benchmark": {
                "qualified": True, "estimated_3_reel_hours": 6.0
            }}), encoding="utf-8")

            def simulate_telegram_approval(_history):
                fresh = producer.load_history()
                producer._parse_review_message(
                    "/approve title=दरवाज़े पर रखा खाना", fresh, approved=True
                )
                producer.save_history(fresh)
                return 0  # approval is not counted as an insight row

            with patch.object(studio_pipeline, "PENDING", pending_path), \
                 patch.object(studio_pipeline, "TOOLCHAIN_LOCK", lock_path), \
                 patch.object(studio_pipeline.producer, "HISTORY_PATH", history_path), \
                 patch.object(studio_pipeline.producer, "require_env"), \
                 patch.object(studio_pipeline, "configure_kaggle_cli"), \
                 patch.object(studio_pipeline.producer, "process_telegram_feedback", side_effect=simulate_telegram_approval), \
                 patch.object(studio_pipeline.producer, "next_post_slots", side_effect=RuntimeError("AFTER_WEEKLY_GATE")):
                with self.assertRaisesRegex(RuntimeError, "AFTER_WEEKLY_GATE"):
                    studio_pipeline.plan_week(3)

            saved = json.loads(history_path.read_text(encoding="utf-8"))
            self.assertEqual(saved["one_reel_qualification"]["reel_id"], "reel_01_pilot")

    def test_five_scene_one_reel_can_produce_a_gpu_benchmark(self):
        """A valid one-Reel story may have five beats; do not make the weekly gate impossible."""
        with tempfile.TemporaryDirectory() as folder:
            old_path = studio_pipeline.TOOLCHAIN_LOCK
            studio_pipeline.TOOLCHAIN_LOCK = Path(folder) / "toolchain_lock.json"
            observed = {
                "comfyui_commit": "comfy-sha",
                "comfyui_gguf_commit": "gguf-sha",
                "model_revisions": {"unet": "unet-sha", "clip": "clip-sha", "vae": "vae-sha"},
                "runtime_packages": {"torch": "2.x"},
                "total_elapsed_seconds": 1800,
                "scenes": [{"generation_elapsed_seconds": 120} for _ in range(5)],
            }
            try:
                locked = studio_pipeline.verify_or_lock_toolchain(observed, "five-scene-pilot")
                self.assertTrue(locked["gpu_benchmark"]["qualified"])
                self.assertEqual(locked["gpu_benchmark"]["sample_scene_count"], 5)
            finally:
                studio_pipeline.TOOLCHAIN_LOCK = old_path

    def test_gpu_benchmark_alone_cannot_unlock_weekly_batch(self):
        lock = {"gpu_benchmark": {"qualified": True, "estimated_3_reel_hours": 5.0}}
        with self.assertRaisesRegex(RuntimeError, "plan-one Reel"):
            studio_pipeline.require_weekly_qualification({"topics": []}, lock)

    def test_rejected_or_undelivered_reel_cannot_create_weekly_qualification(self):
        for qa_passed, delivered in ((False, True), (True, False)):
            with self.subTest(qa_passed=qa_passed, delivered=delivered):
                history = {"topics": [{
                    "title": "परीक्षण कहानी",
                    "status": "ready_for_manual_publish_not_confirmed_published",
                    "reel_id": "reel_bad",
                    "qa_passed": qa_passed,
                    "telegram_delivered": delivered,
                }]}
                producer._parse_review_message(
                    "/approve title=परीक्षण कहानी", history, approved=True
                )
                self.assertNotIn("one_reel_qualification", history)

    def test_slug_uses_safe_default_for_unset_empty_and_whitespace(self):
        self.assertEqual(studio_pipeline.configured_kaggle_slug(""), "bina-shor-ke-studio-video")
        self.assertEqual(studio_pipeline.configured_kaggle_slug("   "), "bina-shor-ke-studio-video")
        with patch.dict(os.environ, {"KAGGLE_KERNEL_SLUG": ""}):
            self.assertEqual(studio_pipeline.configured_kaggle_slug(None), studio_pipeline.DEFAULT_KAGGLE_SLUG)
        self.assertEqual(studio_pipeline.configured_kaggle_slug(" BSK-Test "), "bsk-test")

    def test_new_plan_is_blocked_while_checkpoint_is_saved(self):
        with tempfile.TemporaryDirectory() as folder:
            pending_path = Path(folder) / "pending_gpu_job.json"
            pending_path.write_text(json.dumps({
                "status": "gpu_checkpoint_saved", "job_id": "saved-checkpoint-job"
            }), encoding="utf-8")
            with patch.object(studio_pipeline, "PENDING", pending_path), \
                 patch.object(studio_pipeline.producer, "require_env"), \
                 patch.object(studio_pipeline, "configure_kaggle_cli"):
                with self.assertRaisesRegex(RuntimeError, "unfinished GPU batch"):
                    studio_pipeline.plan_week(1)
            saved = json.loads(pending_path.read_text(encoding="utf-8"))
            self.assertEqual(saved["job_id"], "saved-checkpoint-job")

    def test_reel_qa_and_telegram_delivery_guards_fail_closed(self):
        valid_visual = {
            "status": "reviewed",
            "critical_issue": False,
            "missing_required_scores": [],
            "full_video_motion_diagnostics": {"status": "passed", "full_video_scanned": True},
            "metadata_ocr_qa": {"status": "passed"},
        }
        studio_pipeline.ensure_reel_qa_passed({"technical": {
            "technical_checks_passed": True,
            "rendered_frame_visual_qa": valid_visual,
        }})
        with self.assertRaisesRegex(RuntimeError, "technical QA"):
            studio_pipeline.ensure_reel_qa_passed({"technical": {"technical_checks_passed": False}})
        with self.assertRaisesRegex(RuntimeError, "visual QA"):
            studio_pipeline.ensure_reel_qa_passed({"technical": {
                "technical_checks_passed": True,
                "rendered_frame_visual_qa": {"status": "warning"},
            }})
        with self.assertRaisesRegex(RuntimeError, "Full-video motion diagnostics"):
            studio_pipeline.ensure_reel_qa_passed({"technical": {
                "technical_checks_passed": True,
                "rendered_frame_visual_qa": {
                    **valid_visual,
                    "full_video_motion_diagnostics": {"status": "review_required", "full_video_scanned": True},
                },
            }})
        with self.assertRaisesRegex(RuntimeError, "metadata OCR"):
            studio_pipeline.ensure_reel_qa_passed({"technical": {
                "technical_checks_passed": True,
                "rendered_frame_visual_qa": {**valid_visual, "metadata_ocr_qa": {"status": "not_completed"}},
            }})
        studio_pipeline.ensure_complete_telegram_delivery({
            "video": True, "cover": True, "message": True, "publish_kit": True
        })
        with self.assertRaisesRegex(RuntimeError, "publish_kit"):
            studio_pipeline.ensure_complete_telegram_delivery({
                "video": True, "cover": True, "message": True, "publish_kit": False
            })

    def test_telegram_workflow_skips_drain_and_commit_without_token(self):
        body = (ROOT / ".github" / "workflows" / "telegram-feedback-sync.yml").read_text(encoding="utf-8")
        drain = body.split("- name: Drain pinned owner's Telegram commands", 1)[1].split("- name:", 1)[0]
        self.assertIn("if: env.TELEGRAM_BOT_TOKEN != ''", drain)
        persist = body.split("- name: Persist owner cursor, reviews and performance metrics", 1)[1]
        self.assertIn("if: success() && env.TELEGRAM_BOT_TOKEN != ''", persist)


if __name__ == "__main__":
    unittest.main(verbosity=2)
