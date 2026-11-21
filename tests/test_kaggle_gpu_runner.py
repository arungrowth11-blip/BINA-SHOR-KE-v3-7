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
                {}, {"video_prompt": f"Photoreal shot {scene_index}, one simple action.", "narrative_role": ("hook", "context", "conflict", "escalation", "turn", "payoff")[scene_index-1], "state_change": f"Distinct beat {scene_index} changes the scene meaning", "causal_link": f"Previous beat leads into development {scene_index}"},
                story, scene_index, f"offline/scene_{scene_index:02d}"
            )
            prompt = graph["6"]["inputs"]["text"]
            self.assertIn("CONTINUITY / LOOK BIBLE: " + bible, prompt)
            self.assertIn("SHOT FUNCTION / CAMERA COVERAGE:", prompt)
            self.assertIn("NARRATIVE ROLE: " + ("hook", "context", "conflict", "escalation", "turn", "payoff")[scene_index-1], prompt)
            self.assertIn("STATE CHANGE THIS SHOT MUST COMMUNICATE:", prompt)
            self.assertIn("CAUSAL LINK TO THE STORY:", prompt)
            self.assertIn(runner["shot_coverage_instruction"](scene_index, 6), prompt)
            self.assertIn(f"SHOT {scene_index}:", prompt)
            self.assertIn("Do not add people, props, dialogue or events", prompt)
            prompts.append(prompt)
        self.assertEqual(len(prompts), 6)




class FluxImageFirstWorkflowTests(unittest.TestCase):
    def test_flux_workflow_uses_four_step_still_graph_and_no_wan_video_nodes(self):
        runner = load_gpu_runner_namespace()
        runner["node_prompt"] = lambda _objects, node_type, inputs: {
            "class_type": node_type, "inputs": inputs
        }
        story = {
            "reel_id": "flux_offline_reel",
            "visual_bible": "Same adult cast, same wardrobe, same Indian apartment.",
            "visual_style_profile": {
                "surface_language": "painterly graphic novel",
                "palette": "monsoon teal and warm tungsten",
                "lighting": "motivated window light",
            },
            "characters": [
                {
                    "character_id": "arjun", "display_name": "अर्जुन",
                    "visual_age_description": "adult Indian man in his thirties",
                    "appearance": "olive shirt, short hair, silver watch",
                }
            ],
        }
        beat = {
            "narrative_role": "hook",
            "state_change": "He discovers the unopened letter under the old steel box.",
            "causal_link": "A missed phone call made him search the locked drawer.",
            "video_prompt": "Close-up of an adult man's hand pulling a folded letter from a steel box.",
        }
        graph = runner["build_flux_image_workflow"](
            {}, beat, story, 1, "offline/flux_scene_01"
        )
        classes = {node["class_type"] for node in graph.values()}
        self.assertIn("UnetLoaderGGUF", classes)
        self.assertIn("DualCLIPLoader", classes)
        self.assertIn("CLIPTextEncodeFlux", classes)
        self.assertIn("EmptySD3LatentImage", classes)
        self.assertIn("SaveImage", classes)
        self.assertNotIn("Wan22ImageToVideoLatent", classes)
        self.assertNotIn("CreateVideo", classes)
        sampler = next(node["inputs"] for node in graph.values() if node["class_type"] == "KSampler")
        self.assertEqual(sampler["steps"], 4)
        self.assertEqual(sampler["cfg"], 1.0)
        latent = next(node["inputs"] for node in graph.values() if node["class_type"] == "EmptySD3LatentImage")
        self.assertEqual((latent["width"], latent["height"]), (704, 1280))
        prompt = next(node["inputs"]["clip_l"] for node in graph.values() if node["class_type"] == "CLIPTextEncodeFlux")
        self.assertIn("Same adult cast", prompt)
        self.assertIn("olive shirt", prompt)
        self.assertIn("monsoon teal", prompt)
        self.assertIn("STATE CHANGE", prompt)
        self.assertIn("CAUSAL LINK", prompt)

    def test_scene_still_is_validated_and_center_cropped_to_vertical_canvas(self):
        from PIL import Image
        runner = load_gpu_runner_namespace()
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source = root / "wide.png"
            destination = root / "scene_01.png"
            Image.effect_noise((1600, 900), 80).convert("RGB").save(source)
            result = runner["prepare_scene_still"](source, destination)
            with Image.open(destination) as image:
                self.assertEqual(image.size, (704, 1280))
            self.assertEqual(result["width"], 704)
            self.assertEqual(result["height"], 1280)
            self.assertEqual(result["sha256"], runner["sha256_file"](destination))
            self.assertGreater(result["bytes"], 100_000)

    def test_image_first_comfy_preflight_requires_flux_nodes_only(self):
        runner = load_gpu_runner_namespace()
        required = {
            "UnetLoaderGGUF", "DualCLIPLoader", "VAELoader", "CLIPTextEncodeFlux",
            "ConditioningZeroOut", "EmptySD3LatentImage", "KSampler", "VAEDecode", "SaveImage",
        }
        class Response:
            status = 200
            def read(self):
                return json.dumps({name: {} for name in required}).encode("utf-8")
        with patch.object(runner["urllib"].request, "urlopen", return_value=Response()):
            objects = runner["wait_for_comfy"](primary_image_first=True)
        self.assertEqual(set(objects), required)


class CharacterReferenceTests(unittest.TestCase):
    def test_first_scene_reference_is_extracted_validated_and_hashed(self):
        from PIL import Image
        runner = load_gpu_runner_namespace()
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source = root / "scene_01.mp4"
            destination = root / "input" / "reel_identity_anchor.png"
            source.write_bytes(b"source")
            commands = []
            def fake_run(command, cwd=None, timeout=1800):
                commands.append(command)
                Path(command[-1]).parent.mkdir(parents=True, exist_ok=True)
                Image.effect_noise((704, 1280), 100).convert("RGB").save(command[-1])
                return ""
            with patch.dict(runner, {"run": fake_run}):
                result = runner["create_character_reference_image"](source, destination, 4.0)
            self.assertEqual(result["filename"], "reel_identity_anchor.png")
            self.assertEqual((result["width"], result["height"]), (704, 1280))
            self.assertEqual(result["sha256"], runner["sha256_file"](destination))
            self.assertTrue(destination.is_file())
            self.assertEqual(len(commands), 1)
            self.assertIn("1.800", commands[0])

    def test_character_reference_persistence_records_source_hash_and_resume_targets(self):
        runner = load_gpu_runner_namespace()
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            old_comfy, old_out = runner["COMFY"], runner["OUT"]
            runner["COMFY"], runner["OUT"] = root / "ComfyUI", root / "bsk_output"
            scene = root / "scene_01.mp4"
            scene.write_bytes(b"verified source clip")
            reel = {"reel_id": "reel_reference_test", "beats": [{}, {}, {}, {}, {}, {}]}
            manifest = {}
            metadata = {
                "filename": "reel_reference_test_identity_anchor.png", "width": 704, "height": 1280,
                "timestamp_seconds": 1.8, "bytes": 12345, "sha256": "a" * 64,
                "conditioning": "ComfyUI LoadImage -> Wan22ImageToVideoLatent.start_image for later scenes",
            }
            try:
                with patch.dict(runner, {
                    "valid_scene_file": lambda _path: (True, 4.0),
                    "create_character_reference_image": lambda _source, _destination, _duration: metadata,
                    "write_json": lambda _path, _payload: None,
                }):
                    result = runner["persist_character_reference"](reel, "reel_reference_test", scene, manifest)
                self.assertEqual(reel["character_reference_image"], metadata["filename"])
                self.assertEqual(result["sha256"], "a" * 64)
                self.assertEqual(result["source_scene_index"], 1)
                self.assertEqual(result["used_for_scenes"], [2, 3, 4, 5, 6])
                self.assertEqual(manifest["character_references"], [result])
            finally:
                runner["COMFY"], runner["OUT"] = old_comfy, old_out

    def test_first_scene_reference_rejects_non_finite_or_too_short_duration(self):
        runner = load_gpu_runner_namespace()
        with tempfile.TemporaryDirectory() as folder:
            destination = Path(folder) / "identity.png"
            with self.assertRaisesRegex(ValueError, "finite source scene"):
                runner["create_character_reference_image"](Path("scene.mp4"), destination, float("nan"))


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
