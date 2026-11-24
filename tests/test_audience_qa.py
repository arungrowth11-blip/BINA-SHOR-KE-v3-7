from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import audience_qa  # noqa: E402


def fixture():
    scores = {key: 4.0 for key in audience_qa.EDITORIAL_DIMENSIONS}
    scores["hook_clarity"] = 2.4
    scores["emotional_resonance"] = 4.7
    concept = {"editorial_review": {"scores": scores}}
    build = {"technical": {
        "technical_checks_passed": True,
        "rendered_frame_visual_qa": {
            "status": "reviewed",
            "scores": {
                "text_legibility": 4, "visual_quality": 4,
                "character_continuity": 3, "story_visual_match": 4,
                "anatomy_integrity": 5, "safe_composition": 4,
            },
            "full_video_motion_diagnostics": {"status": "passed", "full_video_scanned": True},
            "metadata_ocr_qa": {"status": "passed"},
        },
    }}
    quality = {"director_10k_readiness": {"dimensions": dict(scores)}}
    return concept, build, quality


class SyntheticAudienceTests(unittest.TestCase):
    def test_ten_thousand_panel_is_exactly_sized_and_explicitly_synthetic(self):
        concept, build, quality = fixture()
        report = audience_qa.generate_simulated_audience_report(
            "reel_001", concept, build, quality
        )
        self.assertEqual(report["simulated_review_count"], 10_000)
        self.assertEqual(report["simulation_type"], "synthetic_not_human")
        self.assertEqual(report["status"], "completed")
        self.assertEqual(report["evidence"]["evidence_count"], 21)
        self.assertEqual(report["missing_evidence_dimensions"], [])
        self.assertEqual(report["failed_technical_gates"], [])
        self.assertIsNone(report["view_prediction"])
        self.assertEqual(sum(row["simulated_profiles"] for row in report["cohort_results"]), 10_000)
        self.assertIn("hook_clarity", report["weakest_evidence_dimensions"][0]["dimension"])

    def test_simulation_is_reproducible_for_identical_evidence(self):
        concept, build, quality = fixture()
        one = audience_qa.generate_simulated_audience_report(
            "reel_001", concept, build, quality, sample_size=1200
        )
        two = audience_qa.generate_simulated_audience_report(
            "reel_001", concept, build, quality, sample_size=1200
        )
        self.assertEqual(one, two)

    def test_evidence_scores_reject_booleans_and_out_of_range_values(self):
        concept, build, quality = fixture()
        concept["editorial_review"]["scores"]["hook_clarity"] = True
        concept["editorial_review"]["scores"]["payoff"] = 6
        evidence = audience_qa.collect_evidence(concept, build, quality)
        self.assertEqual(evidence["scores"]["hook_clarity"], 2.4)  # valid readiness fallback
        self.assertEqual(evidence["scores"]["payoff"], 4.0)

    def test_missing_visual_dimension_blocks_audience_qa_completion(self):
        concept, build, quality = fixture()
        build["technical"]["rendered_frame_visual_qa"]["scores"].pop("metadata_text_cleanliness")
        report = audience_qa.generate_simulated_audience_report("reel_partial", concept, build, quality)
        self.assertEqual(report["status"], "blocked_incomplete_evidence")
        self.assertIn("frame_metadata_text_cleanliness", report["missing_evidence_dimensions"])
        self.assertEqual(report["simulated_review_count"], 10_000)

    def test_failed_objective_gate_blocks_audience_qa_completion(self):
        concept, build, quality = fixture()
        build["technical"]["rendered_frame_visual_qa"]["metadata_ocr_qa"]["status"] = "not_completed"
        report = audience_qa.generate_simulated_audience_report("reel_ocr", concept, build, quality)
        self.assertEqual(report["status"], "blocked_incomplete_evidence")
        self.assertIn("metadata_ocr_passed", report["failed_technical_gates"])

    def test_no_evidence_does_not_fabricate_audience_reactions(self):
        report = audience_qa.generate_simulated_audience_report(
            "empty", {}, {}, {}, sample_size=100
        )
        self.assertEqual(report["status"], "insufficient_evidence")
        self.assertEqual(report["simulated_review_count"], 0)
        self.assertEqual(report["real_human_reviews"]["count"], 0)

    def test_sample_size_validation(self):
        for value in (0, -1, 100_001, True, 2.5):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    audience_qa.generate_simulated_audience_report(
                        "reel", *fixture(), sample_size=value
                    )


class RealHumanReviewTests(unittest.TestCase):
    def ratings(self, score=4):
        return {key: score for key in audience_qa.HUMAN_DIMENSIONS}

    def test_real_reviews_are_separate_deduplicated_and_summarized(self):
        store = {"reviews": []}
        first = audience_qa.record_human_review(
            store, "reel_001", "10001", self.ratings(4), "pass",
            notes="Strong ending", update_id=10, hash_salt="test",
        )
        duplicate = audience_qa.record_human_review(
            store, "reel_001", "10001", self.ratings(2), "reject",
            update_id=11, hash_salt="test",
        )
        second = audience_qa.record_human_review(
            store, "reel_001", "10002", self.ratings(2), "revise",
            hash_salt="test",
        )
        self.assertTrue(first["saved"])
        self.assertTrue(duplicate["duplicate"])
        self.assertTrue(second["saved"])
        self.assertNotIn("10001", str(store))
        summary = audience_qa.summarize_human_reviews(store, "reel_001", 2)
        self.assertEqual(summary["count"], 2)
        self.assertEqual(summary["status"], "sufficient")
        self.assertEqual(summary["dimension_averages_1_to_5"]["hook"], 3.0)
        self.assertEqual(summary["verdict_counts"]["pass"], 1)

    def test_human_review_rejects_missing_or_invalid_ratings(self):
        store = {"reviews": []}
        with self.assertRaises(ValueError):
            audience_qa.record_human_review(
                store, "reel", "123", {"hook": 5}, "pass"
            )
        bad = self.ratings()
        bad["audio"] = 0
        with self.assertRaises(ValueError):
            audience_qa.record_human_review(store, "reel", "123", bad, "pass")

    def test_real_human_threshold_is_not_met_by_synthetic_panel(self):
        store = {"reviews": []}
        summary = audience_qa.summarize_human_reviews(store, "reel", 3)
        self.assertEqual(summary["count"], 0)
        self.assertEqual(summary["status"], "pending")


if __name__ == "__main__":
    unittest.main()
