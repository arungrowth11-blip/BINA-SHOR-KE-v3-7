from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
import wave
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


    def test_voice_first_plan_generates_measured_audio_before_gpu_timing(self):
        concept = {
            "title": "दो दोस्तों की बात",
            "theme": "एक बातचीत में दो दोस्तों के बीच की गलतफहमी साफ होती है।",
            "characters": [
                {"character_id": "arjun", "display_name": "अर्जुन", "gender_presentation": "male", "age_band": "young_adult"},
                {"character_id": "meera", "display_name": "मीरा", "gender_presentation": "female", "age_band": "older_adult"},
            ],
            "beats": [],
        }
        for index in range(6):
            concept["beats"].append({
                "speech_segments": [{
                    "segment_id": f"beat_{index+1:02d}_line_01",
                    "speaker_id": "arjun" if index % 2 == 0 else "meera",
                    "text": "मैंने सोचा तुम मेरी बात समझोगे।",
                    "emotion": "restrained and conversational",
                }]
            })

        calls = []
        def fake_tts(text, destination, voice_direction=None, voice_name=None):
            calls.append((text, voice_direction, voice_name))
            destination.parent.mkdir(parents=True, exist_ok=True)
            with wave.open(str(destination), "wb") as output:
                output.setnchannels(1)
                output.setsampwidth(2)
                output.setframerate(24000)
                output.writeframes(b"\x00\x00" * (3 * 24000))

        with patch.object(studio_pipeline.character_library, "upsert_character") as registry_write, \\
             patch.object(studio_pipeline.producer, "ensure_tts_wav", side_effect=fake_tts):
            result = studio_pipeline.prepare_voice_first_plan(concept, "reel_01_voice_test")

        self.assertEqual(len(calls), 6)
        self.assertEqual(registry_write.call_count, 2)
        self.assertEqual(result["voice_first_plan"]["status"], "voice_measured_before_video")
        self.assertFalse(result["voice_first_plan"]["dialogue_truncated"])
        self.assertEqual(calls[0][2], "Puck")
        self.assertEqual(calls[1][2], "Gacrux")
        for beat in result["beats"]:
            self.assertEqual(beat["voice_timing"]["timing_source"], "measured_tts_wav_before_gpu")
            self.assertEqual(beat["voice_timing"]["speech_duration_seconds"], 3.0)
            self.assertEqual((beat["target_frames"] - 1) % 4, 0)
            self.assertGreaterEqual(beat["target_frames"] / 24.0, 3.0)


    def test_wan_graph_uses_voice_measured_dynamic_frame_count(self):
        runner = load_runner_module()
        schema = {
            'UnetLoaderGGUF': ['unet_name'],
            'CLIPLoader': ['clip_name', 'type', 'device'],
            'VAELoader': ['vae_name'],
            'ModelSamplingSD3': ['model', 'shift'],
            'CLIPTextEncode': ['text', 'clip'],
            'Wan22ImageToVideoLatent': ['width', 'height', 'length', 'batch_size', 'vae', 'start_image'],
            'KSampler': ['seed', 'steps', 'cfg', 'sampler_name', 'scheduler', 'denoise', 'model', 'positive', 'negative', 'latent_image'],
            'VAEDecode': ['samples', 'vae'],
            'CreateVideo': ['images', 'fps'],
            'SaveVideo': ['video', 'filename_prefix', 'format', 'codec'],
        }
        objects = {}
        for node, keys in schema.items():
            required = [key for key in keys if not (node == 'Wan22ImageToVideoLatent' and key == 'start_image')]
            optional = ['start_image'] if node == 'Wan22ImageToVideoLatent' else []
            objects[node] = {'input': {'required': {key: [] for key in required}, 'optional': {key: [] for key in optional}}}
        beat = {
            'video_prompt': 'Vertical cinematic shot of two friends in a small kitchen, natural acting, warm light, clear camera direction and realistic materials.',
            'target_frames': 109,
            'voice_timing': {'target_frames': 109, 'fps': 24},
        }
        story = {'reel_id': 'reel_voice_test', 'visual_bible': 'Same two characters, consistent wardrobe.', 'beats': [beat] * 6}
        graph = runner.build_api_workflow(objects, beat, story, 1, 'bsk/reel_voice_test/scene_01')
        self.assertEqual(graph['55']['inputs']['length'], 109)
        self.assertEqual(graph['57']['inputs']['fps'], 24)

    def test_wan_graph_rejects_invalid_frame_shape_and_unsupported_duration(self):
        runner = load_runner_module()
        schema = {
            'UnetLoaderGGUF': ['unet_name'],
            'CLIPLoader': ['clip_name', 'type', 'device'], 'VAELoader': ['vae_name'],
            'ModelSamplingSD3': ['model', 'shift'], 'CLIPTextEncode': ['text', 'clip'],
            'Wan22ImageToVideoLatent': ['width', 'height', 'length', 'batch_size', 'vae'],
            'KSampler': ['seed', 'steps', 'cfg', 'sampler_name', 'scheduler', 'denoise', 'model', 'positive', 'negative', 'latent_image'],
            'VAEDecode': ['samples', 'vae'], 'CreateVideo': ['images', 'fps'],
            'SaveVideo': ['video', 'filename_prefix', 'format', 'codec'],
        }
        objects = {node: {'input': {'required': {key: [] for key in keys}, 'optional': {}}} for node, keys in schema.items()}
        story = {'reel_id': 'reel_voice_test', 'visual_bible': 'Same character.', 'beats': [{}] * 6}
        base_prompt = 'Vertical cinematic scene with one clear action, same character and practical lighting.'
        bad_shape = {'video_prompt': base_prompt, 'target_frames': 110, 'voice_timing': {'fps': 24}}
        too_long = {'video_prompt': base_prompt, 'target_frames': 197, 'voice_timing': {'fps': 24}}
        with self.assertRaisesRegex(ValueError, r'4n\+1'):
            runner.build_api_workflow(objects, bad_shape, story, 1, 'bsk/test/scene_01')
        with self.assertRaisesRegex(ValueError, '61..193'):
            runner.build_api_workflow(objects, too_long, story, 1, 'bsk/test/scene_01')

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

    def test_scene5_voiceover_repair_changes_only_voiceover_and_reuses_completed_gpu_scenes(self):
        old_pending = studio_pipeline.PENDING
        with tempfile.TemporaryDirectory() as folder:
            studio_pipeline.PENDING = Path(folder) / 'pending_gpu_job.json'
            original = 'सुमित चुपचाप बालकनी में अपनी भीगी कमीज़ निचोड़ रहा था।'
            replacement = 'सुमित ने चुपचाप अपनी भीगी कमीज़ निचोड़ दी।'
            concept = {
                'title': 'सूखी छतरी',
                'beats': [
                    {'scene_index': i, 'voiceover': f'मूल पंक्ति संख्या {i} सुरक्षित रखी गई है।', 'voice_direction': f'direction {i}', 'video_prompt': f'video {i}'}
                    for i in range(1, 7)
                ],
            }
            concept['beats'][4]['voiceover'] = original
            state = {
                'job_id': '20261031_115742', 'status': 'qa_rejected',
                'kaggle_kernel_id': 'owner/worker',
                'active_finalizing_reel_id': 'reel_01_115742',
                'qa_rejection_reason': 'RuntimeError: AI scene would require excessive speed change (1.67x); it is outside the bounded voice-timing repair window.',
                'rhythm_repair_attempts': 1,
                'rhythm_repair': {'status': 'in_progress', 'scene_index': 1},
                'reels': [{'reel_id': 'reel_01_115742', 'delivery_status': 'planned', 'concept': concept}],
            }
            studio_pipeline.write_json(studio_pipeline.PENDING, state)
            try:
                def fake_finalize():
                    latest = studio_pipeline.load_json(studio_pipeline.PENDING)
                    self.assertEqual(latest['status'], 'gpu_complete')
                    self.assertEqual(latest['reels'][0]['concept']['beats'][4]['voiceover'], replacement)
                    self.assertEqual(latest['reels'][0]['concept']['beats'][4]['video_prompt'], 'video 5')
                    self.assertEqual(latest['reels'][0]['concept']['beats'][4]['voice_direction'], 'direction 5')
                    self.assertEqual(latest['reels'][0]['concept']['beats'][0]['voiceover'], 'मूल पंक्ति संख्या 1 सुरक्षित रखी गई है।')
                    latest['status'] = 'delivered'
                    studio_pipeline.write_json(studio_pipeline.PENDING, latest)
                    return 0
                with patch.dict(studio_pipeline.os.environ, {'KAGGLE_USERNAME': 'owner', 'KAGGLE_KEY': 'test-key'}), \
                     patch.object(studio_pipeline, 'KAGGLE_SLUG', 'worker'), \
                     patch.object(studio_pipeline, 'configure_kaggle_cli'), \
                     patch.object(studio_pipeline, 'kaggle_status', return_value=('COMPLETE', 'KernelWorkerStatus.COMPLETE')), \
                     patch.object(studio_pipeline, 'poll_and_finalize', side_effect=fake_finalize) as finalize:
                    self.assertEqual(studio_pipeline.repair_scene_5_voiceover_finalize(), 0)
                    self.assertEqual(studio_pipeline.os.environ.get('BSK_ALLOW_TINY_VO_TEMPO_FIT'), '1')
                    finalize.assert_called_once()
                updated = studio_pipeline.load_json(studio_pipeline.PENDING)
                self.assertEqual(updated['status'], 'delivered')
                self.assertEqual(updated['scene_voiceover_repair_attempts'], 1)
                self.assertEqual(updated['scene_voiceover_repair']['status'], 'completed')
                self.assertFalse(updated['scene_voiceover_repair']['new_kaggle_gpu_dispatch'])
                self.assertEqual(len(replacement.split()), 8)
            finally:
                studio_pipeline.PENDING = old_pending

    def test_scene5_voiceover_repair_refuses_wrong_scene_or_repeated_attempt(self):
        old_pending = studio_pipeline.PENDING
        with tempfile.TemporaryDirectory() as folder:
            studio_pipeline.PENDING = Path(folder) / 'pending_gpu_job.json'
            base = {
                'job_id': '20261031_115742', 'status': 'qa_rejected',
                'kaggle_kernel_id': 'owner/worker', 'active_finalizing_reel_id': 'reel_01_115742',
                'qa_rejection_reason': 'AI scene 4 would require excessive speed change (1.67x)',
                'rhythm_repair_attempts': 1,
                'reels': [{'reel_id': 'reel_01_115742', 'delivery_status': 'planned', 'concept': {
                    'title': 'सूखी छतरी', 'beats': [{'scene_index': i, 'voiceover': 'x'} for i in range(1, 7)]
                }}],
            }
            try:
                studio_pipeline.write_json(studio_pipeline.PENDING, base)
                with self.assertRaisesRegex(RuntimeError, 'restricted to the recorded Scene 5'):
                    studio_pipeline.repair_scene_5_voiceover_finalize()
                repeated = dict(base)
                repeated['qa_rejection_reason'] = 'AI scene 5 would require excessive speed change (1.67x)'
                repeated['scene_voiceover_repair_attempts'] = 1
                studio_pipeline.write_json(studio_pipeline.PENDING, repeated)
                with self.assertRaisesRegex(RuntimeError, 'already been used'):
                    studio_pipeline.repair_scene_5_voiceover_finalize()
            finally:
                studio_pipeline.PENDING = old_pending

    def test_scene5_voiceover_repair_refuses_ratio_outside_exact_167_window(self):
        old_pending = studio_pipeline.PENDING
        with tempfile.TemporaryDirectory() as folder:
            studio_pipeline.PENDING = Path(folder) / 'pending_gpu_job.json'
            original = 'सुमित चुपचाप बालकनी में अपनी भीगी कमीज़ निचोड़ रहा था।'
            concept = {
                'title': 'सूखी छतरी',
                'beats': [
                    {'scene_index': i, 'voiceover': f'मूल पंक्ति संख्या {i} सुरक्षित रखी गई है.'}
                    for i in range(1, 7)
                ],
            }
            concept['beats'][4]['voiceover'] = original
            state = {
                'job_id': '20261031_115742', 'status': 'qa_rejected',
                'kaggle_kernel_id': 'owner/worker',
                'active_finalizing_reel_id': 'reel_01_115742',
                'qa_rejection_reason': 'RuntimeError: AI scene would require excessive speed change (1.70x)',
                'rhythm_repair_attempts': 1,
                'reels': [{'reel_id': 'reel_01_115742', 'delivery_status': 'planned', 'concept': concept}],
            }
            studio_pipeline.write_json(studio_pipeline.PENDING, state)
            try:
                with patch.dict(studio_pipeline.os.environ, {'KAGGLE_USERNAME': 'owner', 'KAGGLE_KEY': 'test-key'}), \
                     patch.object(studio_pipeline, 'KAGGLE_SLUG', 'worker'):
                    with self.assertRaisesRegex(RuntimeError, 'outside this targeted 1.67x repair case'):
                        studio_pipeline.repair_scene_5_voiceover_finalize()
            finally:
                studio_pipeline.PENDING = old_pending

    def test_scene6_voiceover_followup_changes_only_scene6_and_reuses_completed_gpu_scenes(self):
        old_pending = studio_pipeline.PENDING
        with tempfile.TemporaryDirectory() as folder:
            studio_pipeline.PENDING = Path(folder) / 'pending_gpu_job.json'
            scene5_replacement = 'सुमित ने चुपचाप अपनी भीगी कमीज़ निचोड़ दी।'
            scene6_previous = 'उसने सूखी छतरी टाँगी, मगर कमरा चुप रहा।'
            scene6_replacement = 'उसने छतरी टाँगी, मगर कमरा चुप रहा।'
            concept = {
                'title': 'सूखी छतरी',
                'beats': [
                    {'scene_index': i, 'voiceover': f'मूल पंक्ति संख्या {i} सुरक्षित रखी गई है।', 'voice_direction': f'direction {i}', 'video_prompt': f'video {i}'}
                    for i in range(1, 7)
                ],
            }
            concept['beats'][4]['voiceover'] = scene5_replacement
            concept['beats'][5]['voiceover'] = scene6_previous
            state = {
                'job_id': '20261031_115742', 'status': 'qa_rejected',
                'kaggle_kernel_id': 'owner/worker',
                'active_finalizing_reel_id': 'reel_01_115742',
                'qa_rejection_reason': 'RuntimeError: AI scene would require excessive speed change (1.54x); outside the bounded voice-timing repair window.',
                'rhythm_repair_attempts': 1,
                'scene_voiceover_repair_attempts': 1,
                'scene6_voiceover_repair_attempts': 1,
                'scene6_voiceover_repair': {'status': 'in_progress', 'new_kaggle_gpu_dispatch': False},
                'scene6_voiceover_followup_attempts': 0,
                'reels': [{'reel_id': 'reel_01_115742', 'delivery_status': 'planned', 'concept': concept}],
            }
            studio_pipeline.write_json(studio_pipeline.PENDING, state)
            try:
                def fake_finalize():
                    latest = studio_pipeline.load_json(studio_pipeline.PENDING)
                    self.assertEqual(latest['status'], 'gpu_complete')
                    beats = latest['reels'][0]['concept']['beats']
                    self.assertEqual(beats[5]['voiceover'], scene6_replacement)
                    self.assertEqual(beats[5]['video_prompt'], 'video 6')
                    self.assertEqual(beats[5]['voice_direction'], 'direction 6')
                    self.assertEqual(beats[4]['voiceover'], scene5_replacement)
                    self.assertEqual(beats[0]['voiceover'], 'मूल पंक्ति संख्या 1 सुरक्षित रखी गई है।')
                    latest['status'] = 'delivered'
                    studio_pipeline.write_json(studio_pipeline.PENDING, latest)
                    return 0
                with patch.dict(studio_pipeline.os.environ, {'KAGGLE_USERNAME': 'owner', 'KAGGLE_KEY': 'test-key'}), \
                     patch.object(studio_pipeline, 'KAGGLE_SLUG', 'worker'), \
                     patch.object(studio_pipeline, 'configure_kaggle_cli'), \
                     patch.object(studio_pipeline, 'kaggle_status', return_value=('COMPLETE', 'KernelWorkerStatus.COMPLETE')), \
                     patch.object(studio_pipeline, 'poll_and_finalize', side_effect=fake_finalize) as finalize:
                    self.assertEqual(studio_pipeline.repair_scene_6_voiceover_followup_finalize(), 0)
                    self.assertEqual(studio_pipeline.os.environ.get('BSK_ALLOW_TINY_VO_TEMPO_FIT'), '1')
                    finalize.assert_called_once()
                updated = studio_pipeline.load_json(studio_pipeline.PENDING)
                self.assertEqual(updated['status'], 'delivered')
                self.assertEqual(updated['scene6_voiceover_followup_attempts'], 1)
                self.assertEqual(updated['scene6_voiceover_followup']['status'], 'completed')
                self.assertFalse(updated['scene6_voiceover_followup']['new_kaggle_gpu_dispatch'])
                self.assertEqual(len(scene6_replacement.split()), 7)
            finally:
                studio_pipeline.PENDING = old_pending
                studio_pipeline.os.environ.pop('BSK_ALLOW_TINY_VO_TEMPO_FIT', None)

    def test_scene6_followup_persists_qa_rejection_state_when_finalizer_raises(self):
        old_pending = studio_pipeline.PENDING
        with tempfile.TemporaryDirectory() as folder:
            studio_pipeline.PENDING = Path(folder) / 'pending_gpu_job.json'
            scene5_replacement = 'सुमित ने चुपचाप अपनी भीगी कमीज़ निचोड़ दी।'
            scene6_previous = 'उसने सूखी छतरी टाँगी, मगर कमरा चुप रहा।'
            concept = {
                'title': 'सूखी छतरी',
                'beats': [
                    {'scene_index': i, 'voiceover': f'मूल पंक्ति संख्या {i} सुरक्षित रखी गई है.', 'voice_direction': f'direction {i}', 'video_prompt': f'video {i}'}
                    for i in range(1, 7)
                ],
            }
            concept['beats'][4]['voiceover'] = scene5_replacement
            concept['beats'][5]['voiceover'] = scene6_previous
            state = {
                'job_id': '20261031_115742', 'status': 'qa_rejected',
                'kaggle_kernel_id': 'owner/worker', 'active_finalizing_reel_id': 'reel_01_115742',
                'qa_rejection_reason': 'RuntimeError: AI scene would require excessive speed change (1.54x)',
                'rhythm_repair_attempts': 1, 'scene_voiceover_repair_attempts': 1,
                'scene6_voiceover_repair_attempts': 1,
                'scene6_voiceover_repair': {'status': 'in_progress', 'new_kaggle_gpu_dispatch': False},
                'scene6_voiceover_followup_attempts': 0,
                'reels': [{'reel_id': 'reel_01_115742', 'delivery_status': 'planned', 'concept': concept}],
            }
            studio_pipeline.write_json(studio_pipeline.PENDING, state)
            try:
                def fake_finalize():
                    latest = studio_pipeline.load_json(studio_pipeline.PENDING)
                    self.assertEqual(latest['status'], 'gpu_complete')
                    self.assertEqual(latest['reels'][0]['concept']['beats'][5]['voiceover'], 'उसने छतरी टाँगी, मगर कमरा चुप रहा।')
                    latest['status'] = 'qa_rejected'
                    latest['qa_rejection_reason'] = 'RuntimeError: AI scene would require excessive speed change (1.47x)'
                    studio_pipeline.write_json(studio_pipeline.PENDING, latest)
                    raise RuntimeError('simulated final QA rejection')
                with patch.dict(studio_pipeline.os.environ, {'KAGGLE_USERNAME': 'owner', 'KAGGLE_KEY': 'test-key'}), \
                     patch.object(studio_pipeline, 'KAGGLE_SLUG', 'worker'), \
                     patch.object(studio_pipeline, 'configure_kaggle_cli'), \
                     patch.object(studio_pipeline, 'kaggle_status', return_value=('COMPLETE', 'KernelWorkerStatus.COMPLETE')), \
                     patch.object(studio_pipeline, 'poll_and_finalize', side_effect=fake_finalize):
                    with self.assertRaisesRegex(RuntimeError, 'simulated final QA rejection'):
                        studio_pipeline.repair_scene_6_voiceover_followup_finalize()
                updated = studio_pipeline.load_json(studio_pipeline.PENDING)
                self.assertEqual(updated['status'], 'qa_rejected')
                self.assertEqual(updated['scene6_voiceover_followup_attempts'], 1)
                self.assertEqual(updated['scene6_voiceover_followup']['status'], 'qa_rejected_again')
                self.assertIn('1.47x', updated['scene6_voiceover_followup']['final_qa_rejection_reason'])
                self.assertFalse(updated['scene6_voiceover_followup']['new_kaggle_gpu_dispatch'])
            finally:
                studio_pipeline.PENDING = old_pending

    def test_scene6_voiceover_followup_refuses_wrong_ratio_or_repeated_attempt(self):
        old_pending = studio_pipeline.PENDING
        with tempfile.TemporaryDirectory() as folder:
            studio_pipeline.PENDING = Path(folder) / 'pending_gpu_job.json'
            scene5_replacement = 'सुमित ने चुपचाप अपनी भीगी कमीज़ निचोड़ दी।'
            scene6_previous = 'उसने सूखी छतरी टाँगी, मगर कमरा चुप रहा।'
            concept = {
                'title': 'सूखी छतरी',
                'beats': [{'scene_index': i, 'voiceover': f'line {i}'} for i in range(1, 7)],
            }
            concept['beats'][4]['voiceover'] = scene5_replacement
            concept['beats'][5]['voiceover'] = scene6_previous
            base = {
                'job_id': '20261031_115742', 'status': 'qa_rejected',
                'kaggle_kernel_id': 'owner/worker', 'active_finalizing_reel_id': 'reel_01_115742',
                'qa_rejection_reason': 'AI scene would require excessive speed change (1.54x)',
                'rhythm_repair_attempts': 1, 'scene_voiceover_repair_attempts': 1,
                'scene6_voiceover_repair_attempts': 1,
                'scene6_voiceover_repair': {'status': 'qa_rejected_again'},
                'scene6_voiceover_followup_attempts': 0,
                'reels': [{'reel_id': 'reel_01_115742', 'delivery_status': 'planned', 'concept': concept}],
            }
            try:
                wrong_ratio = dict(base)
                wrong_ratio['qa_rejection_reason'] = 'AI scene would require excessive speed change (1.62x)'
                studio_pipeline.write_json(studio_pipeline.PENDING, wrong_ratio)
                with patch.dict(studio_pipeline.os.environ, {'KAGGLE_USERNAME': 'owner', 'KAGGLE_KEY': 'test-key'}), \
                     patch.object(studio_pipeline, 'KAGGLE_SLUG', 'worker'):
                    with self.assertRaisesRegex(RuntimeError, 'outside this targeted 1.54x follow-up case'):
                        studio_pipeline.repair_scene_6_voiceover_followup_finalize()
                repeated = dict(base)
                repeated['scene6_voiceover_followup_attempts'] = 1
                studio_pipeline.write_json(studio_pipeline.PENDING, repeated)
                with patch.dict(studio_pipeline.os.environ, {'KAGGLE_USERNAME': 'owner', 'KAGGLE_KEY': 'test-key'}), \
                     patch.object(studio_pipeline, 'KAGGLE_SLUG', 'worker'):
                    with self.assertRaisesRegex(RuntimeError, 'already been used'):
                        studio_pipeline.repair_scene_6_voiceover_followup_finalize()
            finally:
                studio_pipeline.PENDING = old_pending

    def test_scene6_voiceover_repair_changes_only_scene6_and_reuses_completed_gpu_scenes(self):
        old_pending = studio_pipeline.PENDING
        with tempfile.TemporaryDirectory() as folder:
            studio_pipeline.PENDING = Path(folder) / 'pending_gpu_job.json'
            scene5_replacement = 'सुमित ने चुपचाप अपनी भीगी कमीज़ निचोड़ दी।'
            scene6_original = 'उसने सूखी छतरी टांग दी, मगर कमरा चुप ही रहा।'
            scene6_replacement = 'उसने सूखी छतरी टाँगी, मगर कमरा चुप रहा।'
            concept = {
                'title': 'सूखी छतरी',
                'beats': [
                    {'scene_index': i, 'voiceover': f'मूल पंक्ति संख्या {i} सुरक्षित रखी गई है।', 'voice_direction': f'direction {i}', 'video_prompt': f'video {i}'}
                    for i in range(1, 7)
                ],
            }
            concept['beats'][4]['voiceover'] = scene5_replacement
            concept['beats'][5]['voiceover'] = scene6_original
            state = {
                'job_id': '20261031_115742', 'status': 'qa_rejected',
                'kaggle_kernel_id': 'owner/worker',
                'active_finalizing_reel_id': 'reel_01_115742',
                'qa_rejection_reason': 'RuntimeError: AI scene would require excessive speed change (1.62x); it is outside the bounded voice-timing repair window.',
                'rhythm_repair_attempts': 1,
                'scene_voiceover_repair_attempts': 1,
                'scene_voiceover_repair': {'status': 'in_progress', 'scene_index': 5},
                'reels': [{'reel_id': 'reel_01_115742', 'delivery_status': 'planned', 'concept': concept}],
            }
            studio_pipeline.write_json(studio_pipeline.PENDING, state)
            try:
                def fake_finalize():
                    latest = studio_pipeline.load_json(studio_pipeline.PENDING)
                    self.assertEqual(latest['status'], 'gpu_complete')
                    beats = latest['reels'][0]['concept']['beats']
                    self.assertEqual(beats[5]['voiceover'], scene6_replacement)
                    self.assertEqual(beats[5]['video_prompt'], 'video 6')
                    self.assertEqual(beats[5]['voice_direction'], 'direction 6')
                    self.assertEqual(beats[4]['voiceover'], scene5_replacement)
                    self.assertEqual(beats[0]['voiceover'], 'मूल पंक्ति संख्या 1 सुरक्षित रखी गई है।')
                    latest['status'] = 'delivered'
                    studio_pipeline.write_json(studio_pipeline.PENDING, latest)
                    return 0
                with patch.dict(studio_pipeline.os.environ, {'KAGGLE_USERNAME': 'owner', 'KAGGLE_KEY': 'test-key'}), \
                     patch.object(studio_pipeline, 'KAGGLE_SLUG', 'worker'), \
                     patch.object(studio_pipeline, 'configure_kaggle_cli'), \
                     patch.object(studio_pipeline, 'kaggle_status', return_value=('COMPLETE', 'KernelWorkerStatus.COMPLETE')), \
                     patch.object(studio_pipeline, 'poll_and_finalize', side_effect=fake_finalize) as finalize:
                    self.assertEqual(studio_pipeline.repair_scene_6_voiceover_finalize(), 0)
                    self.assertEqual(studio_pipeline.os.environ.get('BSK_ALLOW_TINY_VO_TEMPO_FIT'), '1')
                    finalize.assert_called_once()
                updated = studio_pipeline.load_json(studio_pipeline.PENDING)
                self.assertEqual(updated['status'], 'delivered')
                self.assertEqual(updated['scene6_voiceover_repair_attempts'], 1)
                self.assertEqual(updated['scene6_voiceover_repair']['status'], 'completed')
                self.assertFalse(updated['scene6_voiceover_repair']['new_kaggle_gpu_dispatch'])
                self.assertEqual(len(scene6_replacement.split()), 8)
            finally:
                studio_pipeline.PENDING = old_pending
                studio_pipeline.os.environ.pop('BSK_ALLOW_TINY_VO_TEMPO_FIT', None)

    def test_scene6_voiceover_repair_refuses_wrong_ratio_or_repeated_attempt(self):
        old_pending = studio_pipeline.PENDING
        with tempfile.TemporaryDirectory() as folder:
            studio_pipeline.PENDING = Path(folder) / 'pending_gpu_job.json'
            scene5_replacement = 'सुमित ने चुपचाप अपनी भीगी कमीज़ निचोड़ दी।'
            scene6_original = 'उसने सूखी छतरी टांग दी, मगर कमरा चुप ही रहा।'
            concept = {
                'title': 'सूखी छतरी',
                'beats': [{'scene_index': i, 'voiceover': f'line {i}'} for i in range(1, 7)],
            }
            concept['beats'][4]['voiceover'] = scene5_replacement
            concept['beats'][5]['voiceover'] = scene6_original
            base = {
                'job_id': '20261031_115742', 'status': 'qa_rejected',
                'kaggle_kernel_id': 'owner/worker', 'active_finalizing_reel_id': 'reel_01_115742',
                'qa_rejection_reason': 'AI scene 6 would require excessive speed change (1.70x)',
                'rhythm_repair_attempts': 1, 'scene_voiceover_repair_attempts': 1,
                'reels': [{'reel_id': 'reel_01_115742', 'delivery_status': 'planned', 'concept': concept}],
            }
            try:
                studio_pipeline.write_json(studio_pipeline.PENDING, base)
                with patch.dict(studio_pipeline.os.environ, {'KAGGLE_USERNAME': 'owner', 'KAGGLE_KEY': 'test-key'}), \
                     patch.object(studio_pipeline, 'KAGGLE_SLUG', 'worker'):
                    with self.assertRaisesRegex(RuntimeError, 'outside this targeted 1.62x repair case'):
                        studio_pipeline.repair_scene_6_voiceover_finalize()
                repeated = dict(base)
                repeated['qa_rejection_reason'] = 'AI scene would require excessive speed change (1.62x)'
                repeated['scene6_voiceover_repair_attempts'] = 1
                studio_pipeline.write_json(studio_pipeline.PENDING, repeated)
                with self.assertRaisesRegex(RuntimeError, 'already been used'):
                    studio_pipeline.repair_scene_6_voiceover_finalize()
            finally:
                studio_pipeline.PENDING = old_pending

    def test_timing_rebuild_reuses_completed_gpu_output_without_dispatch(self):
        old_pending = studio_pipeline.PENDING
        with tempfile.TemporaryDirectory() as folder:
            studio_pipeline.PENDING = Path(folder) / 'pending_gpu_job.json'
            state = {
                'job_id': '20261031_115742', 'status': 'qa_rejected',
                'kaggle_kernel_id': 'owner/worker',
                'active_finalizing_reel_id': 'reel_01_115742',
                'qa_rejection_reason': 'RuntimeError: AI scene would require excessive speed change (1.52x)',
                'reels': [{
                    'reel_id': 'reel_01_115742', 'delivery_status': 'planned',
                    'concept': {'title': 'सूखी छतरी', 'beats': [{}, {}, {}, {}, {}, {}]},
                }],
            }
            studio_pipeline.write_json(studio_pipeline.PENDING, state)
            try:
                def fake_finalize():
                    latest = studio_pipeline.load_json(studio_pipeline.PENDING)
                    self.assertEqual(latest['status'], 'gpu_complete')
                    self.assertFalse(latest['timing_rebuild']['new_kaggle_gpu_dispatch'])
                    latest['status'] = 'delivered'
                    studio_pipeline.write_json(studio_pipeline.PENDING, latest)
                    return 0

                with patch.dict(studio_pipeline.os.environ, {'KAGGLE_USERNAME': 'owner', 'KAGGLE_KEY': 'test-key'}), \
                     patch.object(studio_pipeline, 'KAGGLE_SLUG', 'worker'), \
                     patch.object(studio_pipeline, 'configure_kaggle_cli'), \
                     patch.object(studio_pipeline, 'kaggle_status', return_value=('COMPLETE', 'KernelWorkerStatus.COMPLETE')), \
                     patch.object(studio_pipeline, 'poll_and_finalize', side_effect=fake_finalize) as finalize:
                    self.assertEqual(studio_pipeline.rebuild_rejected_timing(), 0)
                    finalize.assert_called_once()
                updated = studio_pipeline.load_json(studio_pipeline.PENDING)
                self.assertEqual(updated['status'], 'delivered')
                self.assertEqual(updated['timing_rebuild_attempts'], 1)
                self.assertEqual(updated['timing_rebuild']['status'], 'delivered')
                self.assertFalse(updated['timing_rebuild']['new_kaggle_gpu_dispatch'])
            finally:
                studio_pipeline.PENDING = old_pending

    def test_timing_rebuild_refuses_visual_rejection_and_repeated_attempt(self):
        old_pending = studio_pipeline.PENDING
        with tempfile.TemporaryDirectory() as folder:
            studio_pipeline.PENDING = Path(folder) / 'pending_gpu_job.json'
            base = {
                'job_id': 'job-1', 'status': 'qa_rejected',
                'kaggle_kernel_id': 'owner/worker',
                'active_finalizing_reel_id': 'reel-1',
                'reels': [{'reel_id': 'reel-1', 'delivery_status': 'planned', 'concept': {'beats': []}}],
                'qa_rejection_reason': 'AI scene would require excessive speed change (1.52x)',
            }
            try:
                visual = dict(base)
                visual['qa_rejection_reason'] = 'Critical visual defect: broken hand'
                studio_pipeline.write_json(studio_pipeline.PENDING, visual)
                with self.assertRaisesRegex(RuntimeError, 'only for the recorded narration/video timing'):
                    studio_pipeline.rebuild_rejected_timing()

                repeated = dict(base)
                repeated['timing_rebuild_attempts'] = 1
                studio_pipeline.write_json(studio_pipeline.PENDING, repeated)
                with self.assertRaisesRegex(RuntimeError, 'already been used'):
                    studio_pipeline.rebuild_rejected_timing()
            finally:
                studio_pipeline.PENDING = old_pending

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
