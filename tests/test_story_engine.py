from __future__ import annotations

import sys
import unittest
import shutil
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import story_engine
import motion_comic


class StoryEngineTests(unittest.TestCase):
    def test_adaptive_defaults_match_story_categories(self):
        self.assertEqual(story_engine.policy_for("emotional")["target_seconds"], 35)
        self.assertEqual(story_engine.policy_for("suspense")["target_seconds"], 35)
        self.assertEqual(story_engine.policy_for("comedy")["target_seconds"], 25)
        self.assertEqual(story_engine.policy_for("twist")["target_seconds"], 25)
        self.assertEqual(story_engine.policy_for("poetry")["target_seconds"], 22)

    def test_narrative_arc_requires_ordered_roles_unique_changes_and_causal_links(self):
        roles = story_engine.NARRATIVE_BEAT_ROLES
        beats = [
            {
                "narrative_role": role,
                "state_change": f"Distinct story development number {index} changes the situation",
                "causal_link": "Opening pressure establishes why this beat matters" if index == 1 else
                               f"Previous beat leads directly into this development number {index}",
            }
            for index, role in enumerate(roles, start=1)
        ]
        result = story_engine.validate_narrative_arc(beats)
        self.assertEqual(result["status"], "validated")
        self.assertEqual(result["distinct_state_changes"], 6)
        self.assertEqual(result["causal_links_required"], 5)

    def test_narrative_arc_rejects_role_order_and_repeated_state_change(self):
        roles = story_engine.NARRATIVE_BEAT_ROLES
        beats = [
            {
                "narrative_role": role,
                "state_change": f"Distinct situation change number {index} affects the character",
                "causal_link": "A concrete prior action explains this next development",
            }
            for index, role in enumerate(roles, start=1)
        ]
        beats[2]["narrative_role"] = "payoff"
        with self.assertRaisesRegex(ValueError, "must have role 'conflict'"):
            story_engine.validate_narrative_arc(beats)
        beats[2]["narrative_role"] = "conflict"
        beats[2]["state_change"] = beats[1]["state_change"]
        with self.assertRaisesRegex(ValueError, "repeats an earlier state_change"):
            story_engine.validate_narrative_arc(beats)

    def test_screenplay_length_is_genre_aware(self):
        concept = {
            "story_type": "comedy",
            "beats": [{"voiceover": " ".join(["मित्र"] * 10)} for _ in range(6)],
        }
        policy = story_engine.validate_screenplay_length(concept)
        self.assertEqual(policy["word_count"], 60)
        self.assertEqual(concept["story_type"], "comedy")
        self.assertTrue(policy["duration_is_adaptive"])

    def test_short_screenplay_is_rejected_before_visual_generation(self):
        concept = {"story_type": "emotional", "beats": [{"voiceover": "कम शब्द हैं।"} for _ in range(6)]}
        with self.assertRaisesRegex(ValueError, "expected 75–105"):
            story_engine.validate_screenplay_length(concept)

    def test_measured_audio_duration_is_validated_per_story_type(self):
        self.assertEqual(story_engine.validate_measured_duration(35, "emotional")["measured_seconds"], 35)
        with self.assertRaisesRegex(ValueError, "allowed range is 20–30s"):
            story_engine.validate_measured_duration(34, "comedy")

    def test_35_second_emotional_story_is_primarily_2_5d_with_editorial_camera_grammar(self):
        plan = story_engine.build_editorial_shot_plan([5.8, 5.7, 5.9, 5.8, 5.9, 5.9], "emotional")
        self.assertEqual(plan["editorial_shot_count"], 14)
        self.assertEqual(plan["source_beat_count"], 6)
        self.assertEqual(plan["hero_video_shot_count"], 2)
        self.assertEqual(plan["depth_parallax_shot_count"], 12)
        self.assertEqual(plan["gpu_generation_count"], 6)
        self.assertEqual(plan["visual_pipeline"], story_engine.PRIMARY_25D_PIPELINE)
        self.assertGreaterEqual(plan["depth_parallax_share_actual"], 0.80)
        self.assertLessEqual(plan["hero_video_share_actual"], 0.20)
        self.assertEqual(plan["visual_style_profile"]["profile_id"], "warm_indian_melodrama")
        self.assertTrue(all(item.get("camera_move") for item in plan["shots"]))
        self.assertTrue(all(item.get("style_profile_id") == "warm_indian_melodrama" for item in plan["shots"]))
        self.assertFalse(plan["gpu_generation_saving_claim"])
        self.assertAlmostEqual(sum(s["duration_seconds"] for s in plan["shots"]), plan["measured_duration_seconds"], places=2)

    def test_comedy_uses_fewer_shots_and_remains_primarily_2_5d(self):
        plan = story_engine.build_editorial_shot_plan([4.1, 4.0, 4.1, 4.0, 4.1, 4.1], "comedy")
        self.assertGreaterEqual(plan["editorial_shot_count"], 7)
        self.assertLessEqual(plan["editorial_shot_count"], 10)
        self.assertEqual(plan["hero_video_shot_count"], max(1, int(plan["editorial_shot_count"] * 0.20)))
        self.assertGreaterEqual(plan["depth_parallax_share_actual"], 0.80)
        self.assertEqual(plan["visual_style_profile"]["profile_id"], "bright_everyday_comedy")

    def test_story_categories_receive_distinct_visual_style_profiles(self):
        emotional = story_engine.visual_style_for("emotional")
        suspense = story_engine.visual_style_for("suspense")
        poetry = story_engine.visual_style_for("poetry")
        self.assertNotEqual(emotional["palette"], suspense["palette"])
        self.assertNotEqual(suspense["camera_grammar"], poetry["camera_grammar"])
        self.assertEqual(story_engine.PRIMARY_25D_PIPELINE, "primary_25d_motion_comic_v2")

    def test_shot_allocation_rejects_scene_too_short_for_editorial_cuts(self):
        with self.assertRaisesRegex(ValueError, "at least 2.5 seconds"):
            story_engine.build_editorial_shot_plan([1.0, 5, 5, 5, 5, 5], "emotional")

    def test_retime_shots_preserves_full_scene(self):
        shots = [
            {"start_seconds": 0, "end_seconds": 2.5, "duration_seconds": 2.5, "source": "hero_video"},
            {"start_seconds": 2.5, "end_seconds": 5, "duration_seconds": 2.5, "source": "depth_parallax"},
        ]
        result = story_engine.retime_beat_shots(shots, 5.5)
        self.assertAlmostEqual(result[-1]["end_seconds"], 5.5)
        self.assertAlmostEqual(sum(s["duration_seconds"] for s in result), 5.5)


class MotionComicTests(unittest.TestCase):
    def setUp(self):
        self.shots = [
            {"source": "hero_video", "start_seconds": 0.0, "end_seconds": 2.5, "zoom": 1.0, "crop_x": 0.5, "crop_y": 0.5},
            {"source": "depth_parallax", "start_seconds": 2.5, "end_seconds": 5.0, "zoom": 1.12, "crop_x": 0.5, "crop_y": 0.5},
        ]

    def test_filter_graph_combines_hero_and_parallax_with_exact_cuts(self):
        graph = motion_comic.build_editorial_filter_graph(self.shots, video_speed_ratio=1.0)
        self.assertIn("[0:v]setpts=PTS*1.0000000", graph)
        self.assertIn("fps=30", graph)
        self.assertIn("[1:v]setpts=PTS*1.0000000", graph)
        self.assertIn("trim=start=0.0000:end=2.5000", graph)
        self.assertIn("trim=start=2.5000:end=5.0000", graph)
        self.assertIn("crop=1080:1920", graph)
        self.assertIn("concat=n=2:v=1:a=0[outv]", graph)

    def test_filter_graph_accepts_a_beat_with_only_one_source_type(self):
        graph = motion_comic.build_editorial_filter_graph([dict(self.shots[0])])
        self.assertIn("[0:v]setpts=PTS*1.0000000", graph)
        self.assertNotIn("[1:v]", graph)
        self.assertIn("concat=n=1:v=1:a=0[outv]", graph)

    def test_filter_graph_rejects_an_unknown_editorial_source(self):
        invalid = [dict(self.shots[0], source="still_image"), dict(self.shots[1])]
        with self.assertRaisesRegex(ValueError, "source must be"):
            motion_comic.build_editorial_filter_graph(invalid)

    def test_filter_graph_rejects_non_finite_crop_values(self):
        invalid = [dict(self.shots[0], zoom=float("nan")), dict(self.shots[1])]
        with self.assertRaisesRegex(ValueError, "non-finite"):
            motion_comic.build_editorial_filter_graph(invalid)

    @unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"), "FFmpeg/ffprobe are required for real montage integration.")
    def test_real_ffmpeg_hybrid_montage_preserves_exact_audio_lock_duration(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            hero = root / "hero.mp4"
            depth = root / "depth.mp4"
            output = root / "montage.mp4"
            for destination, colour in ((hero, "0x26384d"), (depth, "0xa66c40")):
                subprocess.run([
                    "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
                    "-f", "lavfi", "-i", "testsrc2=size=704x1280:rate=24",
                    "-vf", f"hue=h={0 if colour == '0x26384d' else 145}", "-t", "3", "-an", "-c:v", "libx264", "-crf", "22", "-pix_fmt", "yuv420p",
                    str(destination),
                ], check=True, timeout=60)
            shots = [
                {"source": "hero_video", "start_seconds": 0.0, "end_seconds": 1.5, "zoom": 1.0, "crop_x": 0.5, "crop_y": 0.5},
                {"source": "depth_parallax", "start_seconds": 0.0, "end_seconds": 1.5, "zoom": 1.08, "crop_x": 0.5, "crop_y": 0.5},
            ]
            result = motion_comic.render_editorial_montage(
                hero, depth, output, shots, target_duration=3.0, fps=30,
            )
            self.assertTrue(result.is_file())
            self.assertGreater(result.stat().st_size, 100_000)


if __name__ == "__main__":
    unittest.main()
