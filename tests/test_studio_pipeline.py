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
            "story_type": "poetry",
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

        with (
            patch.object(studio_pipeline.character_library, "upsert_character") as registry_write,
            patch.object(studio_pipeline.producer, "ensure_tts_wav", side_effect=fake_tts),
        ):
            result = studio_pipeline.prepare_voice_first_plan(concept, "reel_01_voice_test")

        self.assertEqual(len(calls), 6)
        # Do not save a cast until the voice-aware storyboard has passed.
        self.assertEqual(registry_write.call_count, 0)
        self.assertEqual(result["voice_first_plan"]["status"], "voice_measured_before_video")
        self.assertFalse(result["voice_first_plan"]["dialogue_truncated"])
        self.assertEqual(calls[0][2], "Puck")
        self.assertEqual(calls[1][2], "Gacrux")
        for beat in result["beats"]:
            self.assertEqual(beat["voice_timing"]["timing_source"], "measured_tts_wav_before_gpu")
            self.assertEqual(beat["voice_timing"]["speech_duration_seconds"], 3.0)
            self.assertEqual((beat["target_frames"] - 1) % 4, 0)
            self.assertGreaterEqual(beat["target_frames"] / 24.0, 3.0)



    def test_character_cast_is_persisted_only_after_storyboard_acceptance(self):
        concept = {
            "characters": [
                {"character_id": "story_abc12345_arjun", "display_name": "अर्जुन"},
                {"character_id": "story_abc12345_meera", "display_name": "मीरा"},
            ]
        }
        with patch.object(studio_pipeline.character_library, "upsert_character") as upsert:
            count = studio_pipeline.persist_character_cast(concept)
        self.assertEqual(count, 2)
        self.assertEqual(upsert.call_count, 2)

    def test_wan_graph_uses_voice_measured_dynamic_frame_count(self):
        runner = load_runner_module()
        schema = {
            'UnetLoaderGGUF': ['unet_name'],
            'CLIPLoader': ['clip_name', 'type', 'device'],
            'VAELoader': ['vae_name'],
            'ModelSamplingSD3': ['model', 'shift'],
            'CLIPTextEncode': ['text', 'clip'],
            'Wan22ImageToVideoLatent': ['width', 'height', 'length', 'batch_size', 'vae', 'start_image'],
            'LoadImage': ['image'],
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

    def test_later_wan_scenes_are_conditioned_on_the_verified_first_scene_anchor(self):
        runner = load_runner_module()
        schema = {
            'UnetLoaderGGUF': ['unet_name'], 'CLIPLoader': ['clip_name', 'type', 'device'],
            'VAELoader': ['vae_name'], 'ModelSamplingSD3': ['model', 'shift'],
            'CLIPTextEncode': ['text', 'clip'], 'LoadImage': ['image'],
            'Wan22ImageToVideoLatent': ['width', 'height', 'length', 'batch_size', 'vae', 'start_image'],
            'KSampler': ['seed', 'steps', 'cfg', 'sampler_name', 'scheduler', 'denoise', 'model', 'positive', 'negative', 'latent_image'],
            'VAEDecode': ['samples', 'vae'], 'CreateVideo': ['images', 'fps'],
            'SaveVideo': ['video', 'filename_prefix', 'format', 'codec'],
        }
        objects = {
            node: {'input': {'required': {key: [] for key in keys if not (node == 'Wan22ImageToVideoLatent' and key == 'start_image')},
                             'optional': {'start_image': []} if node == 'Wan22ImageToVideoLatent' else {}}}
            for node, keys in schema.items()
        }
        beat = {'video_prompt': 'Illustrated character takes one new action in the same room.', 'target_frames': 109,
                'voice_timing': {'target_frames': 109, 'fps': 24}, 'narrative_role': 'context',
                'state_change': 'The protagonist discovers a new consequence', 'causal_link': 'The hook creates this next discovery'}
        story = {'reel_id': 'reel_anchor_test', 'visual_bible': 'Same two characters, consistent wardrobe.',
                 'visual_pipeline': 'hybrid_25d_motion_comic_v1', 'character_reference_image': 'reel_anchor_test_identity_anchor.png',
                 'beats': [beat] * 6}
        graph = runner.build_api_workflow(objects, beat, story, 2, 'bsk/reel_anchor_test/scene_02')
        self.assertEqual(graph['59']['class_type'], 'LoadImage')
        self.assertEqual(graph['59']['inputs']['image'], 'reel_anchor_test_identity_anchor.png')
        self.assertEqual(graph['55']['inputs']['start_image'], ['59', 0])
        self.assertIn('VISUAL IDENTITY ANCHOR', graph['6']['inputs']['text'])

    def test_hybrid_later_scene_fails_closed_when_reference_anchor_is_missing(self):
        runner = load_runner_module()
        story = {'reel_id': 'reel_anchor_test', 'visual_pipeline': 'hybrid_25d_motion_comic_v1', 'beats': [{}] * 6}
        beat = {'video_prompt': 'A clear illustrated action.', 'target_frames': 109, 'voice_timing': {'fps': 24},
                'narrative_role': 'context', 'state_change': 'The character notices a new detail', 'causal_link': 'The hook creates this discovery'}
        with patch.object(runner, 'node_prompt', side_effect=lambda _objects, node_type, inputs: {'class_type': node_type, 'inputs': inputs}):
            with self.assertRaisesRegex(RuntimeError, 'missing its safe first-scene character anchor'):
                runner.build_api_workflow({}, beat, story, 2, 'bsk/test/scene_02')

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

    def test_kaggle_cli_uses_active_python_interpreter(self):
        command = studio_pipeline.kaggle_cli_command("kernels", "status", "owner/kernel")
        self.assertEqual(command[0], studio_pipeline.sys.executable)
        self.assertEqual(command[1], "-c")
        self.assertIn("from kaggle.cli import main", command[2])
        self.assertEqual(command[3:], ["kernels", "status", "owner/kernel"])

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
                extended = dict(observed)
                extended["model_revisions"] = {**observed["model_revisions"], "depth": "d" * 40}
                extended["runtime_packages"] = {
                    **observed["runtime_packages"],
                    "opencv-python": "not-installed",
                    "opencv-python-headless": "4.10.0.84",
                }
                migrated = studio_pipeline.verify_or_lock_toolchain(extended, "test-job")
                self.assertEqual(migrated["model_revisions"]["depth"], "d" * 40)
                self.assertEqual(migrated["runtime_packages"]["torch"], "2.7.0")
                self.assertEqual(migrated["runtime_packages"]["opencv-python-headless"], "4.10.0.84")
                self.assertIn("runtime_packages_extended_at_ist", migrated)
                self.assertEqual(
                    studio_pipeline.verify_or_lock_toolchain(extended, "test-job")["runtime_packages"],
                    migrated["runtime_packages"],
                )
                changed = dict(extended)
                changed["comfyui_commit"] = "new-sha"
                with self.assertRaisesRegex(RuntimeError, "Toolchain drift detected"):
                    studio_pipeline.verify_or_lock_toolchain(changed, "test-job")
                changed_runtime = dict(extended)
                changed_runtime['runtime_packages'] = {
                    **extended['runtime_packages'], 'torch': '2.8.0'
                }
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
                self.assertEqual(updated['manifest']['reels'], manifest['reels'])
                self.assertEqual(
                    updated['manifest']['toolchain_lock']['model_revisions']['clip'],
                    'c4f60d30c55a624e35427060fdd217579a6c1d77',
                )
                self.assertEqual(updated['gpu_retry_attempts'], 1)
                self.assertIn('kernels', push.call_args.args[0])
            finally:
                studio_pipeline.PENDING = old_pending


    def test_retry_gpu_repairs_exact_hf_folder_revision_error_and_keeps_same_reel(self):
        old_pending = studio_pipeline.PENDING
        old_lock = studio_pipeline.TOOLCHAIN_LOCK
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            studio_pipeline.PENDING = root / 'pending_gpu_job.json'
            studio_pipeline.TOOLCHAIN_LOCK = root / 'toolchain_lock.json'
            comfy_sha = '1' * 40
            gguf_sha = '2' * 40
            fixed_sha = 'c4f60d30c55a624e35427060fdd217579a6c1d77'
            saved_lock = {
                'status': 'locked',
                'comfyui_commit': comfy_sha,
                'comfyui_gguf_commit': gguf_sha,
                'model_revisions': {
                    'unet': 'e1701a0fc7a708f6459531776ee6e08111417d49',
                    'clip': fixed_sha,
                    'vae': fixed_sha,
                },
            }
            studio_pipeline.write_json(studio_pipeline.TOOLCHAIN_LOCK, saved_lock)
            manifest = {
                'job_id': 'job-hf-1',
                'toolchain_lock': {
                    'comfyui_commit': comfy_sha,
                    'comfyui_gguf_commit': gguf_sha,
                    'model_revisions': {'unet': 'e1701a0fc7a708f6459531776ee6e08111417d49',
                                        'clip': 'text_encoders', 'vae': 'vae'},
                },
                'reels': [{'reel_id': 'reel-hf', 'beats': [{'video_prompt': 'same story'}]}],
            }
            state = {
                'job_id': 'job-hf-1', 'status': 'gpu_failed', 'kaggle_kernel_id': 'owner/worker',
                'manifest': manifest, 'reels': [{'reel_id': 'reel-hf', 'delivery_status': 'planned'}],
                'gpu_error': {
                    'error_type': 'RevisionNotFoundError',
                    'error': 'Invalid rev id: text_encoders',
                },
            }
            studio_pipeline.write_json(studio_pipeline.PENDING, state)
            try:
                with patch.dict(studio_pipeline.os.environ, {'KAGGLE_USERNAME': 'owner', 'KAGGLE_KEY': 'test-key'}), \
                     patch.object(studio_pipeline, 'KAGGLE_SLUG', 'worker'), \
                     patch.object(studio_pipeline, 'configure_kaggle_cli'), \
                     patch.object(studio_pipeline, 'kaggle_status', return_value=('ERROR', 'KernelWorkerStatus.ERROR')), \
                     patch.object(studio_pipeline, 'build_kaggle_kernel', return_value=root / 'kernel'), \
                     patch.object(studio_pipeline.subprocess, 'run', return_value=Mock(returncode=0, stdout='pushed', stderr='')) as push:
                    (root / 'kernel').mkdir()
                    self.assertEqual(studio_pipeline.retry_failed_gpu(), 0)
                updated = studio_pipeline.load_json(studio_pipeline.PENDING)
                self.assertEqual(updated['status'], 'gpu_running')
                self.assertEqual(updated['manifest']['job_id'], manifest['job_id'])
                self.assertEqual(updated['manifest']['reels'], manifest['reels'])
                self.assertEqual(updated['manifest']['toolchain_lock']['model_revisions']['clip'], fixed_sha)
                self.assertEqual(updated['manifest']['toolchain_lock']['model_revisions']['vae'], fixed_sha)
                self.assertEqual(updated['gpu_retry_attempts'], 1)
                self.assertIn('Hugging Face snapshot SHA pins', updated['gpu_retry_reason'])
                push.assert_called_once()
            finally:
                studio_pipeline.PENDING = old_pending
                studio_pipeline.TOOLCHAIN_LOCK = old_lock

    def test_retry_gpu_allows_one_guarded_timeout_retry_after_queue_aware_fix(self):
        old_pending = studio_pipeline.PENDING
        old_lock = studio_pipeline.TOOLCHAIN_LOCK
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            studio_pipeline.PENDING = root / 'pending_gpu_job.json'
            studio_pipeline.TOOLCHAIN_LOCK = root / 'toolchain_lock.json'
            comfy_sha = '1' * 40
            gguf_sha = '2' * 40
            saved_lock = {
                'status': 'locked',
                'comfyui_commit': comfy_sha,
                'comfyui_gguf_commit': gguf_sha,
                'model_revisions': {
                    'unet': 'e1701a0fc7a708f6459531776ee6e08111417d49',
                    'clip': 'c4f60d30c55a624e35427060fdd217579a6c1d77',
                    'vae': 'c4f60d30c55a624e35427060fdd217579a6c1d77',
                },
            }
            studio_pipeline.write_json(studio_pipeline.TOOLCHAIN_LOCK, saved_lock)
            manifest = {
                'job_id': 'job-timeout-1',
                'toolchain_lock': {
                    'comfyui_commit': comfy_sha,
                    'comfyui_gguf_commit': gguf_sha,
                    'model_revisions': dict(saved_lock['model_revisions']),
                },
                'reels': [{'reel_id': 'reel-timeout', 'beats': [{'video_prompt': 'same Reel'}]}],
            }
            timeout_error = {
                'status': 'failed',
                'error_type': 'TimeoutError',
                'error': 'ComfyUI scene generation timed out after 2700s. Last status=None',
                'stage': 'kaggle_gpu_render',
                'manifest_id': 'job-timeout-1',
            }
            original_reels = [{'reel_id': 'reel-timeout', 'delivery_status': 'planned'}]
            studio_pipeline.write_json(studio_pipeline.PENDING, {
                'job_id': 'job-timeout-1',
                'status': 'gpu_failed',
                'kaggle_kernel_id': 'owner/worker',
                'manifest': manifest,
                'reels': original_reels,
                'gpu_retry_attempts': 1,
                'gpu_error': json.dumps(timeout_error),
            })
            try:
                with (
                    patch.dict(studio_pipeline.os.environ, {'KAGGLE_USERNAME': 'owner', 'KAGGLE_KEY': 'test-key'}),
                    patch.object(studio_pipeline, 'KAGGLE_SLUG', 'worker'),
                    patch.object(studio_pipeline, 'configure_kaggle_cli'),
                    patch.object(studio_pipeline, 'kaggle_status', return_value=('ERROR', 'KernelWorkerStatus.ERROR')),
                    patch.object(studio_pipeline, 'build_kaggle_kernel', return_value=root / 'kernel'),
                    patch.object(studio_pipeline.subprocess, 'run', return_value=Mock(returncode=0, stdout='pushed', stderr='')) as push,
                ):
                    (root / 'kernel').mkdir()
                    self.assertEqual(studio_pipeline.retry_failed_gpu(), 0)
                updated = studio_pipeline.load_json(studio_pipeline.PENDING)
                self.assertEqual(updated['status'], 'gpu_running')
                self.assertEqual(updated['job_id'], 'job-timeout-1')
                self.assertEqual(updated['gpu_retry_attempts'], 2)
                self.assertEqual(updated['manifest']['reels'], manifest['reels'])
                self.assertEqual(updated['reels'], original_reels)
                self.assertIn('Queue-aware ComfyUI prompt tracking', updated['gpu_retry_reason'])
                push.assert_called_once()
            finally:
                studio_pipeline.PENDING = old_pending
                studio_pipeline.TOOLCHAIN_LOCK = old_lock

    def test_retry_gpu_rejects_unclassified_hf_revision_error(self):
        old_pending = studio_pipeline.PENDING
        with tempfile.TemporaryDirectory() as folder:
            studio_pipeline.PENDING = Path(folder) / 'pending_gpu_job.json'
            studio_pipeline.write_json(studio_pipeline.PENDING, {
                'job_id': 'job-2', 'status': 'gpu_failed', 'kaggle_kernel_id': 'owner/worker',
                'manifest': {'job_id': 'job-2', 'reels': [{'reel_id': 'r', 'beats': [{}]}]},
                'gpu_error': {'error_type': 'RevisionNotFoundError', 'error': 'Invalid rev id: branch_name'},
            })
            try:
                with self.assertRaisesRegex(RuntimeError, 'restricted to the first classified'):
                    studio_pipeline.retry_failed_gpu()
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

    def test_terminal_end_hold_qa_failure_is_archived_after_kaggle_complete(self):
        old_pending = studio_pipeline.PENDING
        old_data = studio_pipeline.DATA
        with tempfile.TemporaryDirectory() as folder:
            data_dir = Path(folder) / "data"
            studio_pipeline.DATA = data_dir
            studio_pipeline.PENDING = data_dir / "pending_gpu_job.json"
            pending = {
                "job_id": "job-qa-1",
                "status": "finalize_failed",
                "kaggle_kernel_id": "owner/worker",
                "finalize_error": (
                    "RuntimeError: AI scene needs a 1.34s end hold, "
                    "above the 1.20s quality limit; regenerate a longer scene or shorten the narration."
                ),
                "manifest": {
                    "job_id": "job-qa-1",
                    "reels": [{"reel_id": "reel-1", "beats": [{}, {}, {}, {}, {}, {}]}],
                },
                "reels": [{"reel_id": "reel-1", "delivery_status": "planned"}],
            }
            studio_pipeline.write_json(studio_pipeline.PENDING, pending)
            try:
                with patch.object(
                    studio_pipeline, "kaggle_status",
                    return_value=("COMPLETE", "KernelWorkerStatus.COMPLETE"),
                ) as status:
                    resolved = studio_pipeline.archive_completed_qa_rejection(
                        pending,
                        studio_pipeline.terminal_finalization_qa_reason(pending),
                    )
                status.assert_called_once_with("owner/worker")
                self.assertEqual(resolved["status"], "qa_rejected")
                self.assertEqual(resolved["finalization_resolution"]["verified_kaggle_status"], "COMPLETE")
                archive = data_dir / "job_archive" / "job-qa-1.json"
                archived = studio_pipeline.load_json(archive)
                self.assertEqual(archived["status"], "finalize_failed")
                self.assertIn("1.34s end hold", archived["finalize_error"])
                self.assertEqual(archived["archive_metadata"]["verified_kaggle_status"], "COMPLETE")
            finally:
                studio_pipeline.PENDING = old_pending
                studio_pipeline.DATA = old_data

    def test_terminal_qa_failure_is_not_archived_when_kaggle_is_not_complete(self):
        old_pending = studio_pipeline.PENDING
        old_data = studio_pipeline.DATA
        with tempfile.TemporaryDirectory() as folder:
            data_dir = Path(folder) / "data"
            studio_pipeline.DATA = data_dir
            studio_pipeline.PENDING = data_dir / "pending_gpu_job.json"
            pending = {
                "job_id": "job-qa-2",
                "status": "finalize_failed",
                "kaggle_kernel_id": "owner/worker",
                "finalize_error": (
                    "RuntimeError: AI scene needs a 1.34s end hold, above the 1.20s quality limit."
                ),
                "manifest": {
                    "reels": [{"reel_id": "reel-2", "beats": [{}, {}, {}, {}, {}, {}]}],
                },
            }
            studio_pipeline.write_json(studio_pipeline.PENDING, pending)
            try:
                with patch.object(
                    studio_pipeline, "kaggle_status",
                    return_value=("RUNNING", "KernelWorkerStatus.RUNNING"),
                ):
                    with self.assertRaisesRegex(RuntimeError, "keeping the pending lock"):
                        studio_pipeline.archive_completed_qa_rejection(
                            pending,
                            studio_pipeline.terminal_finalization_qa_reason(pending),
                        )
                current = studio_pipeline.load_json(studio_pipeline.PENDING)
                self.assertEqual(current["status"], "finalize_failed")
                self.assertFalse((data_dir / "job_archive" / "job-qa-2.json").exists())
            finally:
                studio_pipeline.PENDING = old_pending
                studio_pipeline.DATA = old_data

    def test_unknown_finalization_failure_is_not_classified_as_terminal_qa_rejection(self):
        pending = {
            "status": "finalize_failed",
            "finalize_error": "RuntimeError: Telegram API timeout while sending delivery message.",
        }
        self.assertEqual(studio_pipeline.terminal_finalization_qa_reason(pending), "")

    def test_offline_graph_has_native_t2v_shape(self):
        self.assertEqual(studio_pipeline.self_test(), 0)


    def test_image_first_checkpoint_collector_keeps_hash_verified_png_stills(self):
        from PIL import Image
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            reel_id = "reel_image_checkpoint"
            scene_dir = root / reel_id
            scene_dir.mkdir(parents=True)
            still = scene_dir / "scene_01.png"
            Image.effect_noise((704, 1280), 80).convert("RGB").save(still, format="PNG")
            pending = {
                "job_id": "image-checkpoint-job",
                "reels": [{
                    "reel_id": reel_id,
                    "beats": [{}],
                    "concept": {"visual_pipeline": producer.story_engine.PRIMARY_25D_PIPELINE},
                }],
            }
            rows = studio_pipeline.collect_checkpoint_clips(root, pending)
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["media_type"], "image/png")
            self.assertEqual(rows[0]["file"], f"{reel_id}__scene_01.png")
            self.assertEqual((rows[0]["width"], rows[0]["height"]), (704, 1280))
            self.assertEqual(rows[0]["sha256"], studio_pipeline._sha256(still))

    def test_hybrid_motion_comic_worker_pins_depth_model_and_finalizer_verifies_assets(self):
        runner_source = (ROOT / "scripts" / "kaggle_gpu_runner.py").read_text(encoding="utf-8")
        producer_source = (ROOT / "scripts" / "producer.py").read_text(encoding="utf-8")
        pipeline_source = (ROOT / "scripts" / "studio_pipeline.py").read_text(encoding="utf-8")
        self.assertIn("model_info('depth-anything/Depth-Anything-V2-Small-hf'", runner_source)
        self.assertIn("model_revisions['depth'] = depth_revision", runner_source)
        self.assertIn("build_flux_image_workflow", runner_source)
        self.assertIn("flux1-schnell-Q4_K_S.gguf", runner_source)
        self.assertIn("generation_mode", runner_source)
        self.assertIn("scene_{scene_index:02d}_25d.mp4", runner_source)
        self.assertIn("'sha256': sha256_file(parallax)", runner_source)
        self.assertIn("motion_comic.render_editorial_montage", producer_source)
        self.assertIn("primary_image_first", producer_source)
        self.assertIn("depth_rows", pipeline_source)
        self.assertIn("_sha256(depth_source)", pipeline_source)
        self.assertIn("verify_or_lock_image_toolchain", pipeline_source)
        self.assertIn("IMAGE_TOOLCHAIN_LOCK", pipeline_source)


if __name__ == "__main__":
    unittest.main(verbosity=2)
