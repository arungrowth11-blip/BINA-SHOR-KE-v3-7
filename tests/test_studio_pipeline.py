from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import studio_pipeline  # noqa: E402


def load_runner_module():
    source = (ROOT / "scripts" / "kaggle_gpu_runner.py").read_text(encoding="utf-8").replace("__MANIFEST_JSON__", "json.loads('{}')")
    with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False, encoding="utf-8") as f:
        f.write(source)
        path = Path(f.name)
    try:
        spec = importlib.util.spec_from_file_location("bsk_test_runner", path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    finally:
        path.unlink(missing_ok=True)


class StudioPipelineTests(unittest.TestCase):
    def test_clone_and_pin_repo_checks_out_locked_sha(self):
        runner = load_runner_module()
        with tempfile.TemporaryDirectory() as folder:
            destination = Path(folder) / "ComfyUI"
            destination.mkdir()
            with patch.object(runner, "run", side_effect=["latest-sha", "", "", "locked-sha"]) as mocked:
                result = runner.clone_and_pin_repo("https://example.invalid/repo.git", destination, "locked-sha")
            self.assertEqual(result, "locked-sha")
            self.assertIn("locked-sha", mocked.call_args_list[1].args[0])
            self.assertIn("checkout", mocked.call_args_list[2].args[0])

    def test_node_schema_rejects_missing_required_inputs(self):
        runner = load_runner_module()
        objects = {"ExampleNode": {"input": {"required": {"required_field": []}, "optional": {"nice_to_have": []}}}}
        with self.assertRaisesRegex(RuntimeError, "missing required inputs"):
            runner.node_prompt(objects, "ExampleNode", {"nice_to_have": "x"})

    def test_node_schema_rejects_inputs_removed_by_upstream_change(self):
        runner = load_runner_module()
        objects = {"ExampleNode": {"input": {"required": {"required_field": []}, "optional": {}}}}
        with self.assertRaisesRegex(RuntimeError, "unsupported inputs"):
            runner.node_prompt(objects, "ExampleNode", {"required_field": "ok", "removed_field": "bad"})

    def test_kaggle_api_sampler_graph_omits_ui_only_control_after_generate(self):
        runner = load_runner_module()
        schema = {
            'seed': [], 'steps': [], 'cfg': [], 'sampler_name': [], 'scheduler': [],
            'denoise': [], 'model': [], 'positive': [], 'negative': [], 'latent_image': [],
        }
        objects = {'KSampler': {'input': {'required': {k: [] for k in schema}, 'optional': {}}}}
        inputs = {
            'seed': 123, 'steps': 20, 'cfg': 5, 'sampler_name': 'uni_pc',
            'scheduler': 'simple', 'denoise': 1, 'model': ['48', 0],
            'positive': ['6', 0], 'negative': ['7', 0], 'latent_image': ['55', 0],
        }
        prompt = runner.node_prompt(objects, 'KSampler', inputs)
        self.assertNotIn('control_after_generate', prompt['inputs'])
        self.assertEqual(prompt['inputs']['seed'], 123)

    def test_kaggle_incomplete_does_not_match_complete(self):
        with patch.object(studio_pipeline, "configure_kaggle_cli"), patch.object(
            studio_pipeline.subprocess, "run", return_value=Mock(returncode=0, stdout="KernelWorkerStatus.INCOMPLETE", stderr="")
        ):
            status, _ = studio_pipeline.kaggle_status("owner/kernel")
        self.assertEqual(status, "UNKNOWN")

    def test_kaggle_complete_token_is_recognized(self):
        with patch.object(studio_pipeline, "configure_kaggle_cli"), patch.object(
            studio_pipeline.subprocess, "run", return_value=Mock(returncode=0, stdout="KernelWorkerStatus.COMPLETE", stderr="")
        ):
            status, _ = studio_pipeline.kaggle_status("owner/kernel")
        self.assertEqual(status, "COMPLETE")

    def test_toolchain_lock_is_created_then_refuses_drift(self):
        with tempfile.TemporaryDirectory() as folder:
            old_path = studio_pipeline.TOOLCHAIN_LOCK
            studio_pipeline.TOOLCHAIN_LOCK = Path(folder) / "toolchain_lock.json"
            observed = {
                "job_id": "test-job",
                "comfyui_commit": "comfy-sha-1",
                "comfyui_gguf_commit": "gguf-sha-1",
                "model_revisions": {"unet": "unet-sha", "clip": "clip-sha", "vae": "vae-sha"},
                "runtime_packages": {"torch": "2.7.0", "numpy": "2.1.0"},
                "status": "complete",
            }
            try:
                locked = studio_pipeline.verify_or_lock_toolchain(observed, "test-job")
                self.assertEqual(locked["status"], "locked")
                self.assertEqual(locked["comfyui_commit"], "comfy-sha-1")
                self.assertEqual(studio_pipeline.verify_or_lock_toolchain(observed, "test-job")["status"], "locked")
                changed = dict(observed)
                changed["comfyui_commit"] = "new-sha"
                with self.assertRaisesRegex(RuntimeError, "Toolchain drift detected"):
                    studio_pipeline.verify_or_lock_toolchain(changed, "test-job")
                changed_runtime = dict(observed)
                changed_runtime['runtime_packages'] = {'torch': '2.8.0', 'numpy': '2.1.0'}
                with self.assertRaisesRegex(RuntimeError, 'GPU runtime dependency drift detected'):
                    studio_pipeline.verify_or_lock_toolchain(changed_runtime, 'test-job')
            finally:
                studio_pipeline.TOOLCHAIN_LOCK = old_path

    def test_dispatch_ambiguity_resolution_requires_owner_marked_pending_state(self):
        old_pending = studio_pipeline.PENDING
        with tempfile.TemporaryDirectory() as folder:
            studio_pipeline.PENDING = Path(folder) / 'pending_gpu_job.json'
            try:
                studio_pipeline.write_json(studio_pipeline.PENDING, {'status': 'dispatch_unknown', 'job_id': 'test', 'created_at_ist': '2026-10-30T12:00:00+05:30'})
                self.assertEqual(studio_pipeline.resolve_dispatch_unknown(confirm_running=True), 0)
                self.assertEqual(studio_pipeline.load_json(studio_pipeline.PENDING)['status'], 'gpu_running')
                studio_pipeline.write_json(studio_pipeline.PENDING, {'status': 'dispatch_unknown', 'job_id': 'test2'})
                self.assertEqual(studio_pipeline.resolve_dispatch_unknown(confirm_running=False), 0)
                self.assertEqual(studio_pipeline.load_json(studio_pipeline.PENDING)['status'], 'dispatch_failed')
                with self.assertRaisesRegex(RuntimeError, 'no ambiguous dispatch'):
                    studio_pipeline.resolve_dispatch_unknown(confirm_running=False)
            finally:
                studio_pipeline.PENDING = old_pending

    def test_retry_gpu_reuses_same_manifest_after_confirmed_kaggle_error(self):
        old_pending = studio_pipeline.PENDING
        with tempfile.TemporaryDirectory() as folder:
            studio_pipeline.PENDING = Path(folder) / 'pending_gpu_job.json'
            manifest = {'job_id': 'job-1', 'reels': [{'reel_id': 'reel-1', 'beats': [{'video_prompt': 'x'}]}]}
            state = {
                'job_id': 'job-1', 'status': 'gpu_failed', 'kaggle_kernel_id': 'owner/worker',
                'manifest': manifest, 'reels': [{'reel_id': 'reel-1', 'delivery_status': 'planned'}],
                'gpu_error': 'KSampler schema changed: unsupported control_after_generate',
            }
            studio_pipeline.write_json(studio_pipeline.PENDING, state)
            try:
                with patch.dict(studio_pipeline.os.environ, {'KAGGLE_USERNAME': 'owner', 'KAGGLE_KEY': 'test-key'}), \
                     patch.object(studio_pipeline, 'KAGGLE_SLUG', 'worker'), \
                     patch.object(studio_pipeline, 'configure_kaggle_cli'), \
                     patch.object(studio_pipeline, 'kaggle_status', return_value=('ERROR', 'KernelWorkerStatus.ERROR')), \
                     patch.object(studio_pipeline, 'build_kaggle_kernel', return_value=Path(folder) / 'kernel'), \
                     patch.object(studio_pipeline.subprocess, 'run', return_value=Mock(returncode=0, stdout='pushed', stderr='')) as push:
                    (Path(folder) / 'kernel').mkdir()
                    self.assertEqual(studio_pipeline.retry_failed_gpu(), 0)
                updated = studio_pipeline.load_json(studio_pipeline.PENDING)
                self.assertEqual(updated['status'], 'gpu_running')
                self.assertEqual(updated['job_id'], 'job-1')
                self.assertEqual(updated['manifest'], manifest)
                self.assertEqual(updated['gpu_retry_attempts'], 1)
                self.assertIn('kernels', push.call_args.args[0])
            finally:
                studio_pipeline.PENDING = old_pending

    def test_retry_gpu_refuses_nonterminal_kaggle_status(self):
        old_pending = studio_pipeline.PENDING
        with tempfile.TemporaryDirectory() as folder:
            studio_pipeline.PENDING = Path(folder) / 'pending_gpu_job.json'
            studio_pipeline.write_json(studio_pipeline.PENDING, {
                'job_id': 'job-1', 'status': 'gpu_failed', 'kaggle_kernel_id': 'owner/worker',
                'manifest': {'job_id': 'job-1', 'reels': [{'reel_id': 'r', 'beats': [{}]}]},
                'reels': [{'reel_id': 'r', 'delivery_status': 'planned'}],
                'gpu_error': 'KSampler schema changed: unsupported control_after_generate',
            })
            try:
                with patch.dict(studio_pipeline.os.environ, {'KAGGLE_USERNAME': 'owner', 'KAGGLE_KEY': 'test-key'}), \
                     patch.object(studio_pipeline, 'KAGGLE_SLUG', 'worker'), \
                     patch.object(studio_pipeline, 'configure_kaggle_cli'), \
                     patch.object(studio_pipeline, 'kaggle_status', return_value=('RUNNING', 'KernelWorkerStatus.RUNNING')), \
                     patch.object(studio_pipeline, 'build_kaggle_kernel') as build:
                    with self.assertRaisesRegex(RuntimeError, 'not confirmed terminal'):
                        studio_pipeline.retry_failed_gpu()
                    build.assert_not_called()
            finally:
                studio_pipeline.PENDING = old_pending

    def test_retry_gpu_refuses_existing_checkpoints(self):
        old_pending = studio_pipeline.PENDING
        with tempfile.TemporaryDirectory() as folder:
            studio_pipeline.PENDING = Path(folder) / 'pending_gpu_job.json'
            studio_pipeline.write_json(studio_pipeline.PENDING, {
                'job_id': 'job-1', 'status': 'gpu_failed', 'kaggle_kernel_id': 'owner/worker',
                'manifest': {'job_id': 'job-1', 'reels': [{'reel_id': 'r', 'beats': [{}]}]},
                'reels': [{'reel_id': 'r', 'delivery_status': 'planned'}],
                'gpu_error': 'KSampler schema changed: unsupported control_after_generate',
                'resume_scene_count': 1, 'resume_dataset_id': 'owner/bsk-resume-job1',
            })
            try:
                with self.assertRaisesRegex(RuntimeError, 'Use resume-checkpoint'):
                    studio_pipeline.retry_failed_gpu()
            finally:
                studio_pipeline.PENDING = old_pending

    def test_rhythm_repair_reuses_completed_kaggle_scenes_without_gpu_dispatch(self):
        old_pending = studio_pipeline.PENDING
        with tempfile.TemporaryDirectory() as folder:
            studio_pipeline.PENDING = Path(folder) / 'pending_gpu_job.json'
            state = {
                'job_id': '20261031_115742', 'status': 'qa_rejected',
                'kaggle_kernel_id': 'owner/worker', 'active_finalizing_reel_id': 'reel-1',
                'qa_rejection_reason': 'RuntimeError: AI scene 1 would require excessive speed change (1.39x); regenerate/adjust voiceover.',
                'reels': [{'reel_id': 'reel-1', 'delivery_status': 'planned', 'concept': {'beats': [{}, {}, {}, {}, {}, {}]}}],
            }
            studio_pipeline.write_json(studio_pipeline.PENDING, state)
            try:
                with patch.dict(studio_pipeline.os.environ, {'KAGGLE_USERNAME': 'owner', 'KAGGLE_KEY': 'test-key'}), \
                     patch.object(studio_pipeline, 'KAGGLE_SLUG', 'worker'), \
                     patch.object(studio_pipeline, 'configure_kaggle_cli'), \
                     patch.object(studio_pipeline, 'kaggle_status', return_value=('COMPLETE', 'KernelWorkerStatus.COMPLETE')), \
                     patch.object(studio_pipeline, 'poll_and_finalize', return_value=0) as finalize:
                    self.assertEqual(studio_pipeline.repair_rhythm_finalize(), 0)
                    self.assertEqual(studio_pipeline.os.environ.get('BSK_ALLOW_TINY_VO_TEMPO_FIT'), '1')
                    finalize.assert_called_once()
                updated = studio_pipeline.load_json(studio_pipeline.PENDING)
                self.assertEqual(updated['status'], 'gpu_complete')
                self.assertEqual(updated['rhythm_repair_attempts'], 1)
                self.assertFalse(updated['rhythm_repair']['new_kaggle_gpu_dispatch'])
            finally:
                studio_pipeline.PENDING = old_pending
                studio_pipeline.os.environ.pop('BSK_ALLOW_TINY_VO_TEMPO_FIT', None)

    def test_rhythm_repair_refuses_visual_qa_rejection(self):
        old_pending = studio_pipeline.PENDING
        with tempfile.TemporaryDirectory() as folder:
            studio_pipeline.PENDING = Path(folder) / 'pending_gpu_job.json'
            studio_pipeline.write_json(studio_pipeline.PENDING, {
                'status': 'qa_rejected', 'qa_rejection_reason': 'Critical visual defect: broken hand',
            })
            try:
                with self.assertRaisesRegex(RuntimeError, 'not a supported'):
                    studio_pipeline.repair_rhythm_finalize()
            finally:
                studio_pipeline.PENDING = old_pending

    def test_rhythm_repair_refuses_ratio_outside_narrow_window(self):
        old_pending = studio_pipeline.PENDING
        with tempfile.TemporaryDirectory() as folder:
            studio_pipeline.PENDING = Path(folder) / 'pending_gpu_job.json'
            studio_pipeline.write_json(studio_pipeline.PENDING, {
                'status': 'qa_rejected', 'qa_rejection_reason': 'AI scene 1 would require excessive speed change (1.48x)',
            })
            try:
                with self.assertRaisesRegex(RuntimeError, 'outside the narrow repair window'):
                    studio_pipeline.repair_rhythm_finalize()
            finally:
                studio_pipeline.PENDING = old_pending

    def test_offline_graph_has_native_t2v_shape(self):
        self.assertEqual(studio_pipeline.self_test(), 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
