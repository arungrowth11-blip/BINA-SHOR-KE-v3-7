from __future__ import annotations
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import model_lab  # noqa: E402
import studio_pipeline  # noqa: E402


def load_runner():
    import importlib.util
    source = (ROOT / 'scripts' / 'kaggle_gpu_runner.py').read_text(encoding='utf-8').replace('__MANIFEST_JSON__', "json.loads('{}')")
    with tempfile.NamedTemporaryFile('w', suffix='.py', delete=False, encoding='utf-8') as f:
        f.write(source); path = Path(f.name)
    try:
        spec = importlib.util.spec_from_file_location('bsk_checkpoint_runner_test', path)
        module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
        return module
    finally:
        path.unlink(missing_ok=True)


class RecoveryTests(unittest.TestCase):
    def test_collect_checkpoint_clips_only_keeps_valid_expected_scenes(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder); reel = root / 'reel_01_123456'; reel.mkdir()
            clip = reel / 'scene_01.mp4'; clip.write_bytes(b'x' * 150_000)
            pending = {'reels': [{'reel_id': reel.name, 'beats': [{}, {}]}]}
            with patch.object(studio_pipeline.producer, 'probe_duration', return_value=3.375):
                items = studio_pipeline.collect_checkpoint_clips(root, pending)
            self.assertEqual(len(items), 1)
            self.assertEqual(items[0]['scene_index'], 1)
            self.assertEqual(items[0]['bytes'], 150_000)
            self.assertEqual(len(items[0]['sha256']), 64)

    def test_resume_time_estimate_uses_recorded_median_with_safety_buffer(self):
        pending = {'reels': [{'reel_id': 'r', 'beats': [{}, {}]}]}
        scenes = [{'reel_id': 'r', 'scene_index': 1, 'generation_elapsed_seconds': 100}]
        self.assertEqual(studio_pipeline.estimate_resume_hours(pending, scenes), 1.06)

    def test_resume_time_fails_closed_without_benchmark(self):
        pending = {'reels': [{'reel_id': 'r', 'beats': [{}, {}]}]}
        with patch.object(studio_pipeline, 'load_json', return_value={}):
            self.assertEqual(studio_pipeline.estimate_resume_hours(pending, []), 999.0)

    def test_checkpoint_upload_uses_private_default_and_manifest_hash(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder); clip = root / 'clip.mp4'; clip.write_bytes(b'v' * 140_000)
            pending = {'job_id': 'test_20261030_123456', 'reels': [{'reel_id': 'r1', 'beats': [{}, {}]}]}
            scene = {'reel_id': 'r1', 'scene_index': 1, 'file': 'r1__scene_01.mp4', 'source_path': str(clip), 'bytes': clip.stat().st_size, 'sha256': studio_pipeline._sha256(clip), 'duration_seconds': 3.375, 'generation_elapsed_seconds': 50, 'prompt_id': 'p1'}
            inspected = {}
            def fake_run(command, **kwargs):
                inspected['command'] = command
                stage = Path(command[command.index('-p') + 1])
                inspected['metadata'] = json.loads((stage / 'dataset-metadata.json').read_text(encoding='utf-8'))
                inspected['manifest'] = json.loads((stage / 'checkpoint_manifest.json').read_text(encoding='utf-8'))
                return Mock(returncode=0, stdout='created', stderr='')
            with patch.dict(os.environ, {'KAGGLE_USERNAME': 'owner'}), patch.object(studio_pipeline, 'collect_checkpoint_clips', return_value=[scene]), patch.object(studio_pipeline.subprocess, 'run', side_effect=fake_run), patch.object(studio_pipeline, 'estimate_resume_hours', return_value=1.2):
                result = studio_pipeline.persist_private_resume_dataset(root, pending)
            self.assertIsNotNone(result)
            self.assertIn('datasets', inspected['command'])
            self.assertNotIn('--public', inspected['command'])
            self.assertNotIn('-u', inspected['command'])
            self.assertEqual(inspected['metadata']['id'], 'owner/bsk-resume-test20261030123456')
            self.assertEqual(inspected['manifest']['completed_scenes'], 1)

    def test_kaggle_kernel_metadata_mounts_only_requested_resume_dataset(self):
        with tempfile.TemporaryDirectory() as folder:
            fake_root = Path(folder); (fake_root / 'scripts').mkdir()
            (fake_root / 'scripts' / 'kaggle_gpu_runner.py').write_text('MANIFEST = __MANIFEST_JSON__\n', encoding='utf-8')
            old_root = studio_pipeline.ROOT
            try:
                studio_pipeline.ROOT = fake_root
                with patch.dict(os.environ, {'KAGGLE_USERNAME': 'owner'}):
                    kernel_dir = studio_pipeline.build_kaggle_kernel({'job_id': 'j1', 'resume_dataset_id': 'owner/bsk-resume-test'})
                meta = json.loads((kernel_dir / 'kernel-metadata.json').read_text(encoding='utf-8'))
                self.assertEqual(meta['dataset_sources'], ['owner/bsk-resume-test'])
                self.assertTrue(meta['is_private'])
            finally:
                studio_pipeline.ROOT = old_root

    def test_worker_restores_only_hash_validated_scenes_for_the_same_job(self):
        runner = load_runner()
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder); dataset = root / 'input' / 'bsk-resume-test'; dataset.mkdir(parents=True)
            reel_id = 'reel_01_123456'; clip = dataset / f'{reel_id}__scene_01.mp4'; clip.write_bytes(b'k' * 170_000)
            runner.write_json(dataset / 'checkpoint_manifest.json', {
                'job_id': 'job-restore', 'scenes': [{
                    'reel_id': reel_id, 'scene_index': 1, 'file': clip.name,
                    'bytes': clip.stat().st_size, 'sha256': runner.sha256_file(clip),
                    'generation_elapsed_seconds': 44, 'prompt_id': 'p1'
                }]
            })
            old_input, old_out, old_manifest, old_work = runner.KAGGLE_INPUT_ROOT, runner.OUT, runner.MANIFEST, runner.WORK
            runner.KAGGLE_INPUT_ROOT = root / 'input'; runner.OUT = root / 'output'; runner.WORK = root
            runner.MANIFEST = {'job_id': 'job-restore', 'resume_dataset_id': 'owner/bsk-resume-test', 'reels': [{'reel_id': reel_id, 'beats': [{}]}]}
            result = {'scenes': []}
            try:
                with patch.object(runner, 'valid_scene_file', return_value=(True, 3.375)):
                    restored = runner.restore_checkpoint_dataset(result)
                self.assertIsNone(restored)
                self.assertEqual(len(result['scenes']), 1)
                self.assertTrue((root / 'output' / reel_id / 'scene_01.mp4').exists())
            finally:
                runner.KAGGLE_INPUT_ROOT, runner.OUT, runner.MANIFEST, runner.WORK = old_input, old_out, old_manifest, old_work

    def test_worker_rejects_checkpoint_from_a_different_job(self):
        runner = load_runner()
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder); dataset = root / 'input' / 'bsk-resume-test'; dataset.mkdir(parents=True)
            runner.write_json(dataset / 'checkpoint_manifest.json', {'job_id': 'someone-elses-job', 'scenes': []})
            old_input, old_out, old_manifest, old_work = runner.KAGGLE_INPUT_ROOT, runner.OUT, runner.MANIFEST, runner.WORK
            runner.KAGGLE_INPUT_ROOT = root / 'input'; runner.OUT = root / 'output'; runner.WORK = root
            runner.MANIFEST = {'job_id': 'our-job', 'resume_dataset_id': 'owner/bsk-resume-test', 'reels': []}
            try:
                with self.assertRaisesRegex(RuntimeError, 'different production job'):
                    runner.restore_checkpoint_dataset({'scenes': []})
            finally:
                runner.KAGGLE_INPUT_ROOT, runner.OUT, runner.MANIFEST, runner.WORK = old_input, old_out, old_manifest, old_work

    def test_worker_writes_hash_verified_scene_checkpoint_manifest(self):
        runner = load_runner()
        with tempfile.TemporaryDirectory() as folder:
            out = Path(folder); reel_id = 'reel_01_123456'; d = out / reel_id; d.mkdir()
            (d / 'scene_01.mp4').write_bytes(b'v' * 160_000)
            old_out, old_manifest = runner.OUT, runner.MANIFEST
            runner.OUT = out; runner.MANIFEST = {'job_id': 'job1', 'reels': [{'reel_id': reel_id, 'beats': [{}]}]}
            try:
                with patch.object(runner, 'valid_scene_file', return_value=(True, 3.375)):
                    entries = runner.write_checkpoint_manifest({'scenes': []}, 'running')
                data = json.loads((out / 'gpu_checkpoint_manifest.json').read_text(encoding='utf-8'))
                self.assertEqual(len(entries), 1)
                self.assertEqual(data['completed_scenes'], 1)
                self.assertEqual(len(data['scenes'][0]['sha256']), 64)
            finally:
                runner.OUT, runner.MANIFEST = old_out, old_manifest


    def test_ambiguous_resume_push_is_locked_even_if_kaggle_reports_old_complete_status(self):
        pending = {'status': 'gpu_checkpoint_saved', 'job_id': 'j1', 'resume_dataset_id': 'owner/bsk-resume-test', 'resume_estimated_hours': 1.0, 'resume_attempts': 0, 'manifest': {}, 'kaggle_kernel_id': 'owner/kernel'}
        with patch.object(studio_pipeline, 'build_kaggle_kernel', return_value=Path('/tmp/fake-kernel')), patch.object(studio_pipeline.subprocess, 'run', return_value=Mock(returncode=1, stdout='', stderr='connection closed')), patch.object(studio_pipeline, 'kaggle_status', return_value=('COMPLETE', 'possibly stale previous kernel version')), patch.object(studio_pipeline, 'alert_failure'), patch.object(studio_pipeline, 'write_json') as writer:
            result = studio_pipeline.dispatch_checkpoint_resume(pending, automatic=True)
        self.assertEqual(result, 1)
        self.assertEqual(pending['status'], 'dispatch_unknown')
        self.assertTrue(pending['resume_dispatch_attempt_pending'])
        self.assertEqual(pending['resume_attempts'], 0)
        writer.assert_called_once()

    def test_resume_push_timeout_is_ambiguous_and_never_auto_retried(self):
        pending = {'status': 'gpu_checkpoint_saved', 'job_id': 'j-timeout', 'resume_dataset_id': 'owner/bsk-resume-test', 'resume_estimated_hours': 1.0, 'resume_attempts': 0, 'manifest': {}, 'kaggle_kernel_id': 'owner/kernel'}
        timeout = studio_pipeline.subprocess.TimeoutExpired(cmd='kaggle kernels push', timeout=900)
        with patch.object(studio_pipeline, 'build_kaggle_kernel', return_value=Path('/tmp/fake-kernel')), patch.object(studio_pipeline.subprocess, 'run', side_effect=timeout), patch.object(studio_pipeline, 'kaggle_status', return_value=('COMPLETE', 'stale prior result')), patch.object(studio_pipeline, 'alert_failure'), patch.object(studio_pipeline, 'write_json') as writer:
            result = studio_pipeline.dispatch_checkpoint_resume(pending, automatic=True)
        self.assertEqual(result, 1)
        self.assertEqual(pending['status'], 'dispatch_unknown')
        self.assertTrue(pending['resume_dispatch_attempt_pending'])
        writer.assert_called_once()

    def test_owner_resolution_counts_resume_only_after_confirmation(self):
        old_pending = studio_pipeline.PENDING
        with tempfile.TemporaryDirectory() as folder:
            studio_pipeline.PENDING = Path(folder) / 'pending.json'
            try:
                studio_pipeline.write_json(studio_pipeline.PENDING, {'status': 'dispatch_unknown', 'job_id': 'j1', 'resume_dispatch_attempt_pending': True, 'resume_attempts': 0})
                studio_pipeline.resolve_dispatch_unknown(confirm_running=True)
                state = studio_pipeline.load_json(studio_pipeline.PENDING)
                self.assertEqual(state['status'], 'gpu_running')
                self.assertEqual(state['resume_attempts'], 1)
                self.assertNotIn('resume_dispatch_attempt_pending', state)
                studio_pipeline.write_json(studio_pipeline.PENDING, {'status': 'dispatch_unknown', 'job_id': 'j2', 'resume_dispatch_attempt_pending': True, 'resume_attempts': 1})
                studio_pipeline.resolve_dispatch_unknown(confirm_running=False)
                state = studio_pipeline.load_json(studio_pipeline.PENDING)
                self.assertEqual(state['status'], 'gpu_checkpoint_saved')
                self.assertEqual(state['resume_attempts'], 1)
            finally:
                studio_pipeline.PENDING = old_pending


class ModelLabTests(unittest.TestCase):
    def test_candidate_templates_have_ten_paired_samples(self):
        for candidate in model_lab.CANDIDATES:
            with self.subTest(candidate=candidate):
                card = model_lab.template(candidate)
                self.assertEqual(len(card['samples']), 10)
                self.assertEqual(set(card['samples'][0]['scores_1_to_5']), set(card['samples'][0]['baseline_scores_1_to_5']))

    def test_model_lab_requires_rights_and_baseline_for_promotion(self):
        card = model_lab.template('flux.1-schnell')
        for sample in card['samples']:
            sample['scores_1_to_5'] = {k: 4.8 for k in sample['scores_1_to_5']}
            sample['baseline_scores_1_to_5'] = {k: 4.0 for k in sample['baseline_scores_1_to_5']}
            sample['runtime_seconds'] = 60
            sample['baseline_runtime_seconds'] = 60
        card['human_review']['all_samples_reviewed'] = True
        # Missing licence evidence must keep a high scoring candidate out of production.
        scored = model_lab.score_submission(card)
        self.assertEqual(scored['decision']['status'], 'not_qualified')
        self.assertEqual(scored['decision']['uplift_vs_baseline'], 0.8)

    def test_model_lab_rejects_missing_sample_scores(self):
        card = model_lab.template('indic-speak')
        with self.assertRaisesRegex(ValueError, 'missing or invalid'):
            model_lab.score_submission(card)

    def test_model_lab_high_score_requires_minimum_quality_uplift_and_rights(self):
        card = model_lab.template('hunyuanvideo-1.5')
        for sample in card['samples']:
            sample['scores_1_to_5'] = {k: 4.5 for k in sample['scores_1_to_5']}
            sample['baseline_scores_1_to_5'] = {k: 4.0 for k in sample['baseline_scores_1_to_5']}
            sample['runtime_seconds'] = 100
            sample['baseline_runtime_seconds'] = 100
        card['rights'] = {k: True for k in card['rights']}
        card['human_review']['all_samples_reviewed'] = True
        result = model_lab.score_submission(card)
        self.assertEqual(result['decision']['status'], 'eligible_for_production_trial')
        self.assertEqual(result['decision']['uplift_vs_baseline'], 0.5)


if __name__ == '__main__':
    unittest.main(verbosity=2)
