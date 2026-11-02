import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from bsk.pipeline import service
from bsk.pipeline.state import JobStore


STORY = {
    "title": "आख़िरी कुर्सी",
    "logline": "एक व्यक्ति बिना शोर किए अपना फैसला बदलता है।",
    "narration_text": "रमेश हर शाम दुकान के बाहर कुर्सी रखता था। एक दिन उसने देखा कि पड़ोस की बुज़ुर्ग महिला देर तक खड़ी रहती है। उसने अपनी कुर्सी भीतर रख दी और अगली शाम दरवाज़े के पास दूसरी कुर्सी रख दी।",
    "story_summary": "रमेश एक जरूरत देखकर अपनी आदत बदलता है।",
    "protagonist": "रमेश", "protagonist_want": "शाम को आराम करना", "obstacle": "कुर्सी पर उसकी आदत",
    "consequential_choice": "दूसरी कुर्सी रखना", "consequence": "पड़ोसी को बैठने की जगह मिलती है",
    "resolution": "वह बिना श्रेय लिए मदद करता है", "takeaway": "ध्यान देना भी देखभाल का रूप है",
    "characters": [{"id": "ramesh", "name": "रमेश", "role": "दुकानदार", "visual_identity": "भूरी कमीज़"}],
    "visual_motifs": ["लकड़ी की कुर्सी"],
}

ALIGNMENT = {
    "audio_duration_seconds": 3.1,
    "segments": [
        {"segment_id": 1, "start_seconds": 0.0, "end_seconds": 0.9, "text": "रमेश हर शाम दुकान के बाहर कुर्सी रखता था।"},
        {"segment_id": 2, "start_seconds": 0.95, "end_seconds": 2.0, "text": "एक दिन उसने पड़ोस की महिला को खड़े देखा।"},
        {"segment_id": 3, "start_seconds": 2.05, "end_seconds": 3.1, "text": "उसने अगली शाम दूसरी कुर्सी रख दी।"},
    ],
}


class FakeRouter:
    def generate_json(self, system, prompt, temperature=0.35, exclude=None):
        return "groq", {
            "visual_bible": {
                "style_candidate": "not locked",
                "characters": [{"character_id": "ramesh", "visual_identity": "भूरी कमीज़, छोटे बाल"}],
                "continuity_rules": ["same shirt and face"],
                "locations": [{"location_id": "shop", "description": "small neighbourhood shop"}],
            },
            "scenes": [
                {"segment_start_id": 1, "segment_end_id": 2, "visual_action": "Ramesh places the chair, then notices the waiting neighbour.",
                 "motion_event": "He lowers the chair and turns his head toward her.", "character_ids": ["ramesh"],
                 "camera_direction": "medium shot, gentle lateral move", "emotional_subtext": "first unnoticed, then attentive", "transition": "cut on his turn"},
                {"segment_start_id": 3, "segment_end_id": 3, "visual_action": "Ramesh places a second chair beside the doorway.",
                 "motion_event": "He carries and sets down the chair with a small adjustment.", "character_ids": ["ramesh"],
                 "camera_direction": "wide doorway shot", "emotional_subtext": "quiet practical care", "transition": "hold on empty chair"},
            ],
        }


class StoryboardTests(unittest.TestCase):
    def test_variable_scene_timing_comes_from_approved_audio(self):
        with tempfile.TemporaryDirectory() as temp:
            local_store = JobStore(Path(temp) / "jobs")
            local_store.create("storyboard_job", {"topic": "test"})
            job = local_store.job_dir("storyboard_job")
            (job / "story.json").write_text(__import__("json").dumps(STORY, ensure_ascii=False), encoding="utf-8")
            (job / "alignment.json").write_text(__import__("json").dumps(ALIGNMENT, ensure_ascii=False), encoding="utf-8")
            local_store.add_artifact("storyboard_job", "story", job / "story.json")
            local_store.add_artifact("storyboard_job", "audio_alignment", job / "alignment.json")
            local_store.transition("storyboard_job", "created", "story_drafted")
            local_store.transition("storyboard_job", "story_drafted", "story_approved")
            local_store.transition("storyboard_job", "story_approved", "voice_generated")
            local_store.transition("storyboard_job", "voice_generated", "voice_approved")
            local_store.transition("storyboard_job", "voice_approved", "audio_aligned")
            local_store.transition("storyboard_job", "audio_aligned", "alignment_approved")
            with patch.object(service, "store", local_store), patch.object(service, "ProviderRouter", return_value=FakeRouter()):
                result = service.create_storyboard("storyboard_job")
            self.assertEqual(result["scenes"], 2)
            data = __import__("json").loads((job / "storyboard.json").read_text(encoding="utf-8"))
            self.assertEqual(data["scenes"][0]["start_seconds"], 0.0)
            self.assertEqual(data["scenes"][0]["end_seconds"], 2.0)
            self.assertEqual(data["scenes"][1]["start_seconds"], 2.05)
            self.assertEqual(local_store.read("storyboard_job")["stage"], "storyboard_created")


if __name__ == "__main__":
    unittest.main()
