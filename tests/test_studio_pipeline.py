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

    def test_offline_graph_has_native_t2v_shape(self):
        self.assertEqual(studio_pipeline.self_test(), 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
