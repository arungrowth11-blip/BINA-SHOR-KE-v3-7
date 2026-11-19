from __future__ import annotations

import unittest
import tempfile
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]


def load_gpu_runner_namespace():
    source = (ROOT / "scripts" / "kaggle_gpu_runner.py").read_text(encoding="utf-8")
    source = source.replace("MANIFEST = __MANIFEST_JSON__", 'MANIFEST = {"job_id": "offline-test"}', 1)
    namespace = {"__name__": "bsk_gpu_runner_offline_test"}
    exec(compile(source, "scripts/kaggle_gpu_runner.py", "exec"), namespace)
    return namespace


class CameraCoverageTests(unittest.TestCase):

    def test_hf_cache_revision_extracts_snapshot_sha_not_model_subfolder(self):
        runner = load_gpu_runner_namespace()
        revision = "a" * 40
        with tempfile.TemporaryDirectory() as folder:
            cached = Path(folder) / "models--Comfy-Org--Wan" / "snapshots" / revision / "split_files" / "text_encoders" / "encoder.safetensors"
            self.assertEqual(runner["hf_cache_revision"](cached), revision)

    def test_hf_cache_revision_resolves_comfyui_symlink_to_snapshot_sha(self):
        runner = load_gpu_runner_namespace()
        revision = "b" * 40
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            cached = root / "models--Comfy-Org--Wan" / "snapshots" / revision / "split_files" / "vae" / "wan.safetensors"
            cached.parent.mkdir(parents=True)
            cached.write_bytes(b"model")
            destination = root / "ComfyUI" / "models" / "vae" / "wan.safetensors"
            destination.parent.mkdir(parents=True)
            destination.symlink_to(cached)
            self.assertEqual(runner["hf_cache_revision"](destination), revision)

    def test_hf_cache_revision_rejects_non_snapshot_path(self):
        runner = load_gpu_runner_namespace()
        with tempfile.TemporaryDirectory() as folder:
            with self.assertRaisesRegex(RuntimeError, "Could not determine"):
                runner["hf_cache_revision"](Path(folder) / "text_encoders" / "encoder.safetensors")

    def test_six_scene_coverage_has_distinct_editorial_functions(self):
        runner = load_gpu_runner_namespace()
        roles = [runner["shot_coverage_instruction"](index, 6) for index in range(1, 7)]
        self.assertEqual(len(set(roles)), 6)
        self.assertIn("ESTABLISHING", roles[0])
        self.assertIn("DETAIL INSERT", roles[2])
        self.assertIn("TURNING-POINT", roles[4])
        self.assertIn("PAYOFF", roles[5])

    def test_coverage_rejects_invalid_scene_indexes(self):
        runner = load_gpu_runner_namespace()
        with self.assertRaisesRegex(ValueError, "outside"):
            runner["shot_coverage_instruction"](0, 6)
        with self.assertRaisesRegex(ValueError, "positive integer"):
            runner["shot_coverage_instruction"](1, 0)

    def test_workflow_prompt_repeats_visual_bible_and_adds_scene_specific_coverage(self):
        runner = load_gpu_runner_namespace()
        runner["node_prompt"] = lambda _objects, node_type, inputs: {
            "class_type": node_type, "inputs": inputs
        }
        bible = "Same charcoal wardrobe, same small apartment, same warm window light."
        story = {"reel_id": "offline_reel", "visual_bible": bible, "beats": [{} for _ in range(6)]}
        prompts = []
        for scene_index in range(1, 7):
            graph = runner["build_api_workflow"](
                {}, {"video_prompt": f"Photoreal shot {scene_index}, one simple action."},
                story, scene_index, f"offline/scene_{scene_index:02d}"
            )
            prompt = graph["6"]["inputs"]["text"]
            self.assertIn("CONTINUITY / LOOK BIBLE: " + bible, prompt)
            self.assertIn("SHOT FUNCTION / CAMERA COVERAGE:", prompt)
            self.assertIn(runner["shot_coverage_instruction"](scene_index, 6), prompt)
            self.assertIn(f"SHOT {scene_index}:", prompt)
            self.assertIn("Do not add people, props, dialogue or events", prompt)
            prompts.append(prompt)
        self.assertEqual(len(prompts), 6)




class ComfyPromptDiagnosticsTests(unittest.TestCase):
    def test_prompt_timeout_is_extended_to_ninety_minutes_per_scene(self):
        runner = load_gpu_runner_namespace()
        self.assertEqual(runner["DEFAULT_PROMPT_TIMEOUT_SECONDS"], 5400)

    def test_wait_prompt_reports_queue_state_when_history_is_not_yet_persisted(self):
        runner = load_gpu_runner_namespace()
        calls = []

        class Response:
            def __init__(self, payload):
                self.payload = payload

            def raise_for_status(self):
                return None

            def json(self):
                return self.payload

        def fake_get(url, timeout):
            calls.append(url)
            if "/history/" in url:
                return Response({})
            return Response({
                "queue_running": [[1, "prompt-123", {}, {}, []]],
                "queue_pending": [],
            })

        fake_requests = SimpleNamespace(
            get=fake_get, RequestException=type("RequestException", (Exception,), {})
        )
        with (
            patch.dict(sys.modules, {"requests": fake_requests}),
            patch.object(runner["time"], "monotonic", side_effect=[0, 0, 11]),
            patch.object(runner["time"], "sleep", return_value=None),
        ):
            with self.assertRaisesRegex(TimeoutError, "queue_state.*running"):
                runner["wait_prompt"]("prompt-123", timeout=10)

        self.assertTrue(any("/history/prompt-123" in url for url in calls))
        self.assertTrue(any(url.endswith("/queue") for url in calls))

    def test_failure_file_preserves_current_scene_and_comfy_server_log_tail(self):
        runner = load_gpu_runner_namespace()
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            old_work, old_out, old_manifest = runner["WORK"], runner["OUT"], runner["MANIFEST"]
            work, out = root / "work", root / "out"
            work.mkdir()
            out.mkdir()
            (work / "comfy_server.log").write_text("ComfyUI booted\\nCUDA worker stalled\\n", encoding="utf-8")
            runner["WORK"], runner["OUT"] = work, out
            runner["MANIFEST"] = {"job_id": "offline-test", "reels": []}
            current_scene = {"reel_id": "test-reel", "scene_index": 1, "prompt_id": "prompt-123"}
            try:
                runner["send_failure_file"](TimeoutError("scene timeout"), {"current_scene": current_scene, "scenes": []})
                report = runner["json"].loads((out / "GPU_JOB_ERROR.json").read_text(encoding="utf-8"))
                self.assertEqual(report["current_scene"], current_scene)
                self.assertIn("CUDA worker stalled", report["comfy_server_log_tail"])
                self.assertEqual(report["error_type"], "TimeoutError")
            finally:
                runner["WORK"], runner["OUT"], runner["MANIFEST"] = old_work, old_out, old_manifest

if __name__ == "__main__":
    unittest.main(verbosity=2)
