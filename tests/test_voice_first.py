from __future__ import annotations

import json
import sys
import tempfile
import unittest
import wave
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import character_library
import voice_first


class VoiceFirstTests(unittest.TestCase):
    def write_wav(self, path: Path, duration: float, sample_rate: int = 24000):
        path.parent.mkdir(parents=True, exist_ok=True)
        with wave.open(str(path), "wb") as output:
            output.setnchannels(1)
            output.setsampwidth(2)
            output.setframerate(sample_rate)
            output.writeframes(b"\x00\x00" * round(duration * sample_rate))

    def test_legacy_concept_upgrades_to_narrator_without_rewriting_line(self):
        source = "बाहर बादल देखकर उसने बिना पूछे सुमित की छतरी उठा ली।"
        concept = {"beats": [{"voiceover": source} for _ in range(6)]}
        result = voice_first.normalise_screenplay(concept)
        self.assertEqual(result["screenplay_schema_version"], 2)
        self.assertTrue(result["characters"][0]["character_id"].endswith("_narrator"))
        self.assertEqual(
            result["beats"][0]["speech_segments"][0]["speaker_id"],
            result["characters"][0]["character_id"],
        )
        self.assertEqual(result["beats"][0]["speech_segments"][0]["text"], source)
        self.assertEqual(result["beats"][0]["voiceover"], source)
        self.assertEqual(result["beats"][0]["speech_segments"][0]["gemini_voice"], "Kore")
        # Normalisation is safe to run again before dispatch/finalization.
        again = voice_first.normalise_screenplay(result)
        self.assertEqual(again["characters"][0]["character_id"], result["characters"][0]["character_id"])

    def test_two_character_script_assigns_distinct_gender_age_voice_presets(self):
        concept = {
            "characters": [
                {"character_id": "arjun", "display_name": "अर्जुन", "gender_presentation": "male", "age_band": "young_adult"},
                {
                    "character_id": "meera", "display_name": "मीरा",
                    "gender_presentation": "female", "age_band": "adult",
                    "voice_direction": "Make her sound like a much older woman.",
                },
            ],
            "beats": [{
                "speech_segments": [
                    {"speaker_id": "arjun", "text": "तुमने मेरी बात सुनी ही नहीं।", "emotion": "restrained hurt"},
                    {"speaker_id": "meera", "text": "मैं जवाब देने से पहले सोच रही थी।", "emotion": "calm"},
                ]
            } for _ in range(6)],
        }
        result = voice_first.normalise_screenplay(concept)
        lines = result["beats"][0]["speech_segments"]
        self.assertEqual(lines[0]["gemini_voice"], "Puck")
        self.assertEqual(lines[1]["gemini_voice"], "Aoede")
        self.assertEqual(
            result["characters"][1]["voice_direction"],
            voice_first.resolve_voice_profile("hi_female_adult_aoede")["direction"],
        )
        self.assertEqual(result["characters"][1]["visual_age_description"], voice_first.visual_age_description("adult"))
        self.assertTrue(lines[0]["speaker_id"].endswith("_arjun"))
        self.assertTrue(lines[1]["speaker_id"].endswith("_meera"))
        self.assertEqual(result["beats"][0]["voiceover"], "तुमने मेरी बात सुनी ही नहीं। मैं जवाब देने से पहले सोच रही थी।")


    def test_matching_gemini_display_voice_alias_normalizes_to_canonical_profile_id(self):
        concept = {
            "characters": [{
                "character_id": "arjun", "display_name": "अर्जुन",
                "gender_presentation": "male", "age_band": "young_adult",
                "voice_profile_id": "Puck",
            }],
            "beats": [{"speech_segments": []} for _ in range(6)],
        }
        result = voice_first.normalise_screenplay(concept)
        character = result["characters"][0]
        self.assertEqual(character["voice_profile_id"], "hi_male_young_puck")
        self.assertEqual(character["gemini_voice"], "Puck")

    def test_wrong_gemini_display_voice_alias_is_overridden_by_age_gender(self):
        concept = {
            "characters": [{
                "character_id": "arjun", "display_name": "अर्जुन",
                "gender_presentation": "male", "age_band": "young_adult",
                "voice_profile_id": "Charon",
            }],
            "beats": [{"speech_segments": []} for _ in range(6)],
        }
        result = voice_first.normalise_screenplay(concept)
        character = result["characters"][0]
        self.assertEqual(character["voice_profile_id"], "hi_male_young_puck")
        self.assertEqual(character["gemini_voice"], "Puck")
        self.assertEqual(character["voice_profile_override_ignored"], "Charon")

    def test_ignored_voice_display_alias_preserves_original_case(self):
        concept = {
            "characters": [{
                "character_id": "arjun", "display_name": "अर्जुन",
                "gender_presentation": "male", "age_band": "young_adult",
                "voice_profile_id": "cHaRoN",
            }],
            "beats": [{"speech_segments": []} for _ in range(6)],
        }
        result = voice_first.normalise_screenplay(concept)
        character = result["characters"][0]
        self.assertEqual(character["voice_profile_id"], "hi_male_young_puck")
        self.assertEqual(character["gemini_voice"], "Puck")
        self.assertEqual(character["voice_profile_override_ignored"], "cHaRoN")

    def test_conflicting_explicit_voice_profile_is_overridden_against_visual_age(self):
        concept = {
            "characters": [{
                "character_id": "meera", "display_name": "मीरा",
                "gender_presentation": "female", "age_band": "adult",
                "voice_profile_id": "hi_female_older_gacrux",
            }],
            "beats": [{"speech_segments": []} for _ in range(6)],
        }
        result = voice_first.normalise_screenplay(concept)
        character = result["characters"][0]
        self.assertEqual(character["voice_profile_id"], "hi_female_adult_aoede")
        self.assertEqual(character["gemini_voice"], "Aoede")
        self.assertEqual(character["voice_profile_override_ignored"], "hi_female_older_gacrux")

    def test_silent_child_keeps_child_visual_age_without_an_adult_voice(self):
        concept = {
            "characters": [{
                "character_id": "child1", "display_name": "बच्चा",
                "gender_presentation": "male", "age_band": "child",
                "appearance": "A school-age child in a blue sweater.",
            }],
            "beats": [{"speech_segments": []} for _ in range(6)],
        }
        result = voice_first.normalise_screenplay(concept)
        character = result["characters"][0]
        self.assertEqual(character["age_band"], "child")
        self.assertEqual(character["voice_profile_id"], "")
        self.assertIn("child", character["visual_age_description"])

    def test_child_speaker_fails_closed_without_a_qualified_child_voice(self):
        concept = {
            "characters": [{
                "character_id": "child1", "display_name": "बच्चा",
                "gender_presentation": "male", "age_band": "child",
            }],
            "beats": [{"speech_segments": [
                {"speaker_id": "child1", "text": "मैं भी साथ चलूँगा।"}
            ]} for _ in range(6)],
        }
        with self.assertRaisesRegex(ValueError, "no age-appropriate Hindi TTS profile is qualified"):
            voice_first.normalise_screenplay(concept)

    def test_teen_is_not_silently_cast_with_a_young_adult_voice(self):
        with self.assertRaisesRegex(ValueError, "No age-appropriate Hindi TTS profile is qualified"):
            voice_first.infer_voice_profile("female", "teen")

    def test_unknown_speaker_fails_closed(self):
        concept = {
            "characters": [{"character_id": "a1", "display_name": "A"}],
            "beats": [{"speech_segments": [{"speaker_id": "missing", "text": "यह संवाद गलत cast से जुड़ा है।"}]} for _ in range(6)],
        }
        with self.assertRaisesRegex(ValueError, "unknown speaker_id"):
            voice_first.normalise_screenplay(concept)

    def test_voice_profile_is_validated(self):
        with self.assertRaisesRegex(ValueError, "Unknown voice_profile_id"):
            voice_first.resolve_voice_profile("not-a-real-voice")

    def test_duration_plan_uses_measured_audio_and_never_shortens(self):
        segments = [
            {"segment_id": "one", "speaker_id": "a"},
            {"segment_id": "two", "speaker_id": "b"},
        ]
        result = voice_first.build_scene_timing_plan(segments, {"one": 2.31, "two": 3.27})
        self.assertAlmostEqual(result["speech_duration_seconds"], 5.58)
        self.assertFalse(result["dialogue_truncated"])
        self.assertGreaterEqual(result["target_duration_seconds"], 5.58 + 0.18 + 0.08 + 0.18)
        self.assertEqual((result["target_frames"] - 1) % 4, 0)
        self.assertEqual(result["timing_source"], "measured_tts_wav_before_gpu")

    def test_frame_count_rounds_up_to_wan_temporal_shape(self):
        self.assertEqual(voice_first.frames_for_duration(2.0), 61)
        frames = voice_first.frames_for_duration(7.3)
        self.assertGreaterEqual(frames / 24.0, 7.3)
        self.assertEqual((frames - 1) % 4, 0)

    def test_assemble_dialogue_preserves_each_line_and_gap(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            first, second, combined = root / "one.wav", root / "two.wav", root / "combined.wav"
            self.write_wav(first, 1.25)
            self.write_wav(second, 2.0)
            duration = voice_first.assemble_dialogue_wav(
                [first, second], combined, gap_seconds=0.2,
                leading_silence_seconds=0.08,
            )
            self.assertAlmostEqual(duration, 3.53, places=2)
            self.assertAlmostEqual(voice_first.wav_duration(combined), 3.53, places=2)

    def test_silent_visual_beat_can_have_a_valid_audio_timeline(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "silence.wav"
            voice_first.write_silence_wav(path, 2.6)
            self.assertAlmostEqual(voice_first.wav_duration(path), 2.6, places=2)


    def test_duplicate_segment_ids_are_rejected(self):
        concept = {
            "characters": [{"character_id": "a1", "display_name": "A"}],
            "beats": [],
        }
        for _ in range(6):
            concept["beats"].append({
                "speech_segments": [{
                    "segment_id": "same_line",
                    "speaker_id": "a1",
                    "text": "यह संवाद पूरी तरह से स्वाभाविक है।",
                }]
            })
        with self.assertRaisesRegex(ValueError, "Duplicate speech segment id"):
            voice_first.normalise_screenplay(concept)

    def test_new_reel_identity_does_not_reuse_previous_story_cast(self):
        first = {
            "title": "एक कहानी", "theme": "एक ही विषय",
            "story_instance_id": "reel_0001",
            "characters": [{"character_id": "protagonist", "display_name": "A"}],
            "beats": [],
        }
        second = {
            "title": "एक कहानी", "theme": "एक ही विषय",
            "story_instance_id": "reel_0002",
            "characters": [{"character_id": "protagonist", "display_name": "A"}],
            "beats": [],
        }
        for concept in (first, second):
            concept["beats"] = [{
                "speech_segments": [{
                    "speaker_id": "protagonist", "text": "यह एक सामान्य संवाद है।"
                }]
            } for _ in range(6)]
            voice_first.normalise_screenplay(concept)
        self.assertNotEqual(first["characters"][0]["character_id"], second["characters"][0]["character_id"])

    def test_wav_format_gate_rejects_wrong_sample_rate(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "wrong.wav"
            self.write_wav(path, 1.0, sample_rate=16000)
            with self.assertRaisesRegex(ValueError, "24 kHz"):
                voice_first.wav_duration(path)


class CharacterLibraryTests(unittest.TestCase):
    def test_register_reuses_character_id_and_writes_atomic_registry(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "registry.json"
            one = {"character_id": "arjun", "display_name": "Arjun", "gender_presentation": "male", "age_band": "young"}
            character_library.upsert_character(one, path)
            updated = dict(one, display_name="Arjun v2")
            character_library.upsert_character(updated, path)
            registry = character_library.load_registry(path)
            self.assertEqual(len(registry["characters"]), 1)
            self.assertEqual(registry["characters"][0]["display_name"], "Arjun v2")
            self.assertEqual(registry["characters"][0]["asset_status"], "metadata_only_pending_3d_pilot")

    def test_invalid_character_id_is_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            with self.assertRaisesRegex(ValueError, "Invalid character_id"):
                character_library.upsert_character({"character_id": "../escape"}, Path(folder) / "registry.json")


if __name__ == "__main__":
    unittest.main()
