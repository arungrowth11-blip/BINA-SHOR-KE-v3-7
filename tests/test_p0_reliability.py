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
                "manual_external_review_required": True,
                "manual_external_reviewers_required": 3,
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
                "manual_external_review_required": True,
                "manual_external_reviewers_required": 3,
            }]}), encoding="utf-8")
            lock_path = base / "toolchain_lock.json"
            lock_path.write_text(json.dumps({
                "status": "locked",
                "comfyui_commit": "a" * 40,
                "comfyui_gguf_commit": "b" * 40,
                "model_revisions": {"unet": "c" * 40, "clip": "d" * 40, "vae": "e" * 40},
            }), encoding="utf-8")
            image_lock_path = base / "image_toolchain_lock.json"
            image_lock_path.write_text(json.dumps({"gpu_benchmark": {
                "qualified": True, "estimated_3_reel_hours": 6.0
            }}), encoding="utf-8")

            def simulate_telegram_approval(_history):
                fresh = producer.load_history()
                producer._parse_review_message(
                    "/approve title=दरवाज़े पर रखा खाना", fresh, approved=True
                )
                producer.save_history(fresh)
                return 0  # approval is not counted as an insight row

            with patch.dict(os.environ, {"BSK_FREE_TIER_ONLY_ACK": "true"}), \
                 patch.object(studio_pipeline, "PENDING", pending_path), \
                 patch.object(studio_pipeline, "TOOLCHAIN_LOCK", lock_path), \
                 patch.object(studio_pipeline, "IMAGE_TOOLCHAIN_LOCK", image_lock_path), \
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
                if not qa_passed:
                    with self.assertRaisesRegex(ValueError, "has not completed its QA path"):
                        producer._parse_review_message(
                            "/approve title=परीक्षण कहानी", history, approved=True
                        )
                    self.assertEqual(
                        history["topics"][0]["status"],
                        "ready_for_manual_publish_not_confirmed_published",
                    )
                else:
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
            with patch.dict(os.environ, {"BSK_FREE_TIER_ONLY_ACK": "true"}), \
                 patch.object(studio_pipeline, "PENDING", pending_path), \
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



    def test_gpu_output_manifest_is_bound_to_exact_job_renderer_and_scene_inventory(self):
        pending = {
            "job_id": "job-image-first-1",
            "kaggle_kernel_id": "owner/private-worker",
            "manifest": {"job_id": "job-image-first-1", "generation_mode": "still_image_first"},
            "reels": [{
                "reel_id": "reel_01_test",
                "concept": {"beats": [{}, {}, {}]},
            }],
        }
        gpu_manifest = {
            "job_id": "job-image-first-1",
            "status": "complete",
            "generation_mode": "still_image_first",
            "scenes": [
                {"reel_id": "reel_01_test", "scene_index": 1, "media_type": "image/png"},
                {"reel_id": "reel_01_test", "scene_index": 2, "media_type": "image/png"},
                {"reel_id": "reel_01_test", "scene_index": 3, "media_type": "image/png"},
            ],
            "parallax_scenes": [
                {"reel_id": "reel_01_test", "scene_index": 1},
                {"reel_id": "reel_01_test", "scene_index": 2},
                {"reel_id": "reel_01_test", "scene_index": 3},
            ],
        }
        with patch.object(studio_pipeline, "kaggle_kernel_id", return_value="owner/private-worker"):
            self.assertIsNone(studio_pipeline.pending_gpu_identity_error(pending))
        self.assertIsNone(
            studio_pipeline.gpu_output_identity_error(gpu_manifest, pending, require_complete=True)
        )

        stale = json.loads(json.dumps(gpu_manifest))
        stale["job_id"] = "older-kaggle-job"
        self.assertIn("job_id mismatch", studio_pipeline.gpu_output_identity_error(stale, pending))

        wrong_renderer = json.loads(json.dumps(gpu_manifest))
        wrong_renderer["generation_mode"] = "wan_video_first_legacy"
        self.assertIn("renderer mismatch", studio_pipeline.gpu_output_identity_error(wrong_renderer, pending))

        missing_scene = json.loads(json.dumps(gpu_manifest))
        missing_scene["scenes"].pop()
        self.assertIn("scene inventory count mismatch", studio_pipeline.gpu_output_identity_error(
            missing_scene, pending, require_complete=True
        ))

        missing_parallax = json.loads(json.dumps(gpu_manifest))
        missing_parallax["parallax_scenes"].pop()
        self.assertIn("depth-parallax inventory", studio_pipeline.gpu_output_identity_error(
            missing_parallax, pending, require_complete=True
        ))

    def test_pending_job_identity_rejects_wrong_kernel_and_embedded_manifest(self):
        pending = {
            "job_id": "expected-job",
            "kaggle_kernel_id": "owner/wrong-worker",
            "manifest": {"job_id": "expected-job", "generation_mode": "still_image_first"},
        }
        with patch.object(studio_pipeline, "kaggle_kernel_id", return_value="owner/private-worker"):
            self.assertIn("kernel identity", studio_pipeline.pending_gpu_identity_error(pending))
            pending["kaggle_kernel_id"] = "owner/private-worker"
            pending["manifest"]["job_id"] = "different-job"
            self.assertIn("embedded worker manifest", studio_pipeline.pending_gpu_identity_error(pending))

    def test_tts_cache_fingerprint_is_bound_to_model_voice_and_performance(self):
        original = producer.GEMINI_TTS_MODEL
        first = producer.tts_cache_fingerprint("नमस्ते", "धीमे स्वर में", "Kore")
        try:
            producer.GEMINI_TTS_MODEL = "different-tts-model"
            self.assertNotEqual(first, producer.tts_cache_fingerprint("नमस्ते", "धीमे स्वर में", "Kore"))
            producer.GEMINI_TTS_MODEL = original
            self.assertNotEqual(first, producer.tts_cache_fingerprint("नमस्ते", "सामान्य स्वर में", "Kore"))
            self.assertNotEqual(first, producer.tts_cache_fingerprint("नमस्ते", "धीमे स्वर में", "Aoede"))
        finally:
            producer.GEMINI_TTS_MODEL = original

    def test_locked_voice_asset_requires_exact_hash_and_duration(self):
        import hashlib
        import wave
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            wav_path = root / "data" / "voice_assets" / "reel-test" / "line.wav"
            wav_path.parent.mkdir(parents=True)
            with wave.open(str(wav_path), "wb") as output:
                output.setnchannels(1)
                output.setsampwidth(2)
                output.setframerate(24000)
                output.writeframes(b"\\x00\\x00" * 24000)
            digest = hashlib.sha256(wav_path.read_bytes()).hexdigest()
            segment = {"segment_id": "line", "voice_asset": {
                "schema_version": 1, "path": "data/voice_assets/reel-test/line.wav",
                "sha256": digest, "duration_seconds": 1.0,
            }}
            with patch.object(producer, "ROOT", root):
                self.assertEqual(producer.validate_locked_voice_asset(segment), wav_path)
                segment["voice_asset"]["sha256"] = "0" * 64
                with self.assertRaisesRegex(RuntimeError, "SHA-256 mismatch"):
                    producer.validate_locked_voice_asset(segment)

    def test_voice_first_finalizer_never_regenerates_missing_locked_audio(self):
        segment = {"segment_id": "line-1", "text": "यह संवाद है।"}
        with self.assertRaisesRegex(RuntimeError, "no immutable voice asset"):
            producer.validate_locked_voice_asset(segment)

if __name__ == "__main__":
    unittest.main(verbosity=2)
