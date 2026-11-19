from __future__ import annotations

import unittest
import tempfile
from pathlib import Path


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


if __name__ == "__main__":
    unittest.main(verbosity=2)
