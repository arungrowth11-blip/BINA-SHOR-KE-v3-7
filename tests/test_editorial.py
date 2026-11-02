import unittest

from bsk.editorial.story import validate_critique
from bsk.models import StoryDraft


class StorySchemaTests(unittest.TestCase):
    def valid_story(self):
        return {
            "title": "खाली डिब्बा",
            "logline": "एक पड़ोसी चुपचाप अपनी गलती सुधारता है।",
            "narration_text": "रवि रोज़ सीढ़ियों पर रखा खाली डिब्बा देखकर आगे बढ़ जाता था। एक दिन उसे पता चला कि वह डिब्बा किसी की दवा पहुँचाने के लिए रखा जाता था। उसने बिना बताए डिब्बा सही जगह रख दिया और अगली सुबह दरवाज़े पर एक छोटा धन्यवाद रखा मिला।",
            "story_summary": "रवि की उदासीनता एक जानकारी मिलने पर बदलती है और वह काम सुधारता है।",
            "protagonist": "रवि",
            "protagonist_want": "जल्दी घर पहुँचना",
            "obstacle": "सीढ़ियों पर रखा डिब्बा उसे परेशान करता है",
            "consequential_choice": "वह डिब्बे का कारण जानकर उसे सही जगह रखता है",
            "consequence": "दवा पहुँचाने का रास्ता खुल जाता है",
            "resolution": "अगली सुबह धन्यवाद का छोटा नोट मिलता है",
            "takeaway": "किसी चीज़ का कारण जाने बिना उसे बेकार समझ लेना आसान है।",
            "characters": [{"id": "ravi", "name": "रवि", "role": "पड़ोसी", "visual_identity": "नीली शर्ट, छोटे बाल"}],
            "visual_motifs": ["डिब्बा", "सीढ़ियाँ"],
        }

    def test_story_has_complete_causal_fields(self):
        story = StoryDraft.from_dict(self.valid_story())
        self.assertEqual(story.title, "खाली डिब्बा")
        self.assertGreater(len(story.narration_text), 40)

    def test_story_rejects_missing_resolution(self):
        payload = self.valid_story()
        payload["resolution"] = ""
        with self.assertRaises(ValueError):
            StoryDraft.from_dict(payload)

    def test_story_has_no_fixed_word_or_scene_count(self):
        payload = self.valid_story()
        payload["narration_text"] += " एक और वाक्य।" * 50
        payload["characters"] += [{"id": "x", "name": "दूसरा पात्र", "role": "पड़ोसी", "visual_identity": "सफेद कुर्ता"}]
        story = StoryDraft.from_dict(payload)
        self.assertTrue(story.narration_text.endswith("एक और वाक्य।"))
        self.assertEqual(len(story.characters), 2)


class CritiqueGateTests(unittest.TestCase):
    def valid_review(self):
        return {
            "approved": True,
            "scores": {
                "completeness": 5, "clarity": 5, "causal_logic": 5, "natural_hindi": 4,
                "originality": 4, "human_specificity": 4, "emotional_resonance": 4,
                "ending_payoff": 4, "share_value": 4, "platform_safety": 5,
            },
            "cold_reader_recap": {
                "protagonist": "रवि", "want": "घर पहुँचना", "obstacle": "डिब्बा",
                "choice": "डिब्बा रखना", "consequence": "रास्ता खुलना", "resolution": "धन्यवाद का नोट",
            },
            "confusion_points": [], "missing_causal_links": [], "revision_notes": [],
        }

    def test_approved_review_passes(self):
        approved, average, errors = validate_critique(self.valid_review())
        self.assertTrue(approved)
        self.assertGreaterEqual(average, 4.1)
        self.assertEqual(errors, [])

    def test_critic_missing_causal_link_fails(self):
        review = self.valid_review()
        review["missing_causal_links"] = ["The box movement is unexplained."]
        approved, _, errors = validate_critique(review)
        self.assertFalse(approved)
        self.assertTrue(errors)


if __name__ == "__main__":
    unittest.main()
