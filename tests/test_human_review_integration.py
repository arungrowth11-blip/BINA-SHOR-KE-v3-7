from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import audience_qa  # noqa: E402
import producer  # noqa: E402


def full_ratings(value: int = 4) -> dict[str, int]:
    return {key: value for key in audience_qa.HUMAN_DIMENSIONS}


class HumanReviewIntegrationTests(unittest.TestCase):
    def test_allowlisted_human_command_is_parsed_and_duplicate_vote_is_rejected(self):
        history = {"topics": [{
            "reel_id": "reel_001", "title": "एक कहानी", "qa_passed": True,
        }]}
        store = {"reviews": []}
        command = (
            "/bskreview reel_id=reel_001; hook=4; story=4; emotion=5; visual=4; "
            "audio=4; ending=5; clarity=4; share_value=4; verdict=pass; notes=Strong twist"
        )
        with patch.dict(os.environ, {
            "BSK_HUMAN_REVIEW_MIN_RESPONSES": "3",
            "BSK_REVIEWER_HASH_SALT": "test-salt-0123456789-abcdefghijklmnopqrstuvwxyz",
        }):
            first = producer._parse_human_review_message(command, history, store, "10001", 20)
            duplicate = producer._parse_human_review_message(command, history, store, "10001", 21)
        self.assertTrue(first["saved"])
        self.assertTrue(duplicate["duplicate"])
        self.assertEqual(first["summary"]["count"], 1)
        self.assertEqual(len(store["reviews"]), 1)
        self.assertEqual(store["reviews"][0]["notes"], "Strong twist")
        self.assertNotIn("10001", str(store))

    def test_human_review_command_requires_real_qa_pass_and_all_ratings(self):
        history = {"topics": [{"reel_id": "reel_001", "qa_passed": False}]}
        with self.assertRaisesRegex(ValueError, "has not passed"):
            producer._parse_human_review_message(
                "/bskreview reel_id=reel_001", history, {"reviews": []}, "10001", 1
            )
        history["topics"][0]["qa_passed"] = True
        with self.assertRaisesRegex(ValueError, "Missing ratings"):
            producer._parse_human_review_message(
                "/bskreview reel_id=reel_001; verdict=pass",
                history, {"reviews": []}, "10001", 1,
            )

    def test_owner_approval_waits_for_configured_independent_panel(self):
        history = {"topics": [{
            "title": "एक कहानी", "reel_id": "reel_001",
            "status": "ready_for_manual_publish_not_confirmed_published",
            "qa_passed": True, "visual_qa_status": "reviewed",
            "motion_diagnostics_status": "passed", "metadata_ocr_status": "passed",
            "telegram_delivered": True,
        }]}
        with patch.object(producer, "human_reviewer_chat_ids", return_value=["10001", "10002", "10003"]),              patch.object(producer, "telegram_chat_id", return_value="99999"),              patch.dict(os.environ, {"BSK_HUMAN_REVIEW_MIN_RESPONSES": "3"}):
            with self.assertRaisesRegex(ValueError, "Independent human panel is not qualified"):
                producer._parse_review_message("/approve title=एक कहानी", history, approved=True)

            store = {"reviews": []}
            for index, reviewer_id in enumerate(("10001", "10002", "10003"), start=1):
                audience_qa.record_human_review(
                    store, "reel_001", reviewer_id, full_ratings(4), "pass",
                    hash_salt="test",
                )
            history["topics"][0]["human_review_summary"] = audience_qa.summarize_human_reviews(store, "reel_001", 3)
            approved = producer._parse_review_message("/approve title=एक कहानी", history, approved=True)
        self.assertTrue(approved["weekly_qualification_created"])
        self.assertTrue(history["one_reel_qualification"]["owner_approved"])

    def test_panel_reject_or_revise_votes_block_owner_approval(self):
        history = {"topics": [{
            "title": "एक कहानी", "reel_id": "reel_001",
            "status": "ready_for_manual_publish_not_confirmed_published",
            "qa_passed": True, "visual_qa_status": "reviewed",
            "motion_diagnostics_status": "passed", "metadata_ocr_status": "passed",
            "telegram_delivered": True,
        }]}
        store = {"reviews": []}
        for reviewer_id, verdict in (("10001", "pass"), ("10002", "revise"), ("10003", "pass")):
            audience_qa.record_human_review(
                store, "reel_001", reviewer_id, full_ratings(4), verdict, hash_salt="test"
            )
        history["topics"][0]["human_review_summary"] = audience_qa.summarize_human_reviews(store, "reel_001", 3)
        with patch.object(producer, "human_reviewer_chat_ids", return_value=["10001", "10002", "10003"]),              patch.object(producer, "telegram_chat_id", return_value="99999"):
            with self.assertRaisesRegex(ValueError, "All reviewers must return verdict=pass"):
                producer._parse_review_message("/approve title=एक कहानी", history, approved=True)

    def test_panel_sends_only_to_allowlisted_private_ids_and_resumes_without_duplicates(self):
        with tempfile.TemporaryDirectory() as folder:
            video = Path(folder) / "reel.mp4"
            video.write_bytes(b"sample-video")
            sent_chats = []
            def fake_post(method, data=None, files=None, timeout=180):
                sent_chats.append(data["chat_id"])
                return {"ok": True}
            with patch.dict(os.environ, {
                "BSK_HUMAN_REVIEWER_CHAT_IDS": "12345,67890,24680,99999,not-an-id,12345",
                "BSK_REVIEWER_HASH_SALT": "test-salt-0123456789-abcdefghijklmnopqrstuvwxyz",
            }), patch.object(producer, "telegram_chat_id", return_value="99999"), patch.object(producer, "telegram_post", side_effect=fake_post):
                first = producer.dispatch_human_review_panel("reel_001", "शीर्षक", video)
                second = producer.dispatch_human_review_panel(
                    "reel_001", "शीर्षक", video,
                    already_sent_hashes=first["sent_reviewer_hashes"],
                )
        self.assertEqual(sent_chats, ["12345", "67890", "24680"])
        self.assertEqual(first["configured_count"], 3)
        self.assertEqual(first["sent_count"], 3)
        self.assertEqual(second["sent_count"], 3)
        self.assertEqual(second["pending_count"], 0)

    def test_owner_cannot_be_counted_as_independent_reviewer(self):
        with patch.dict(os.environ, {
            "BSK_HUMAN_REVIEWER_CHAT_IDS": "99999,12345,67890",
            "BSK_HUMAN_REVIEW_MIN_RESPONSES": "2",
            "BSK_REVIEWER_HASH_SALT": "test-salt-0123456789-abcdefghijklmnopqrstuvwxyz",
        }), patch.object(producer, "telegram_chat_id", return_value="99999"):
            with tempfile.TemporaryDirectory() as folder:
                video = Path(folder) / "reel.mp4"
                video.write_bytes(b"video")
                sent = []
                with patch.object(producer, "telegram_post", side_effect=lambda method, data=None, files=None, timeout=180: sent.append(data["chat_id"]) or {"ok": True}):
                    result = producer.dispatch_human_review_panel("reel_001", "शीर्षक", video)
        self.assertEqual(sent, ["12345", "67890"])
        self.assertEqual(result["configured_count"], 2)
        self.assertEqual(result["sent_count"], 2)

    def test_reviewer_hash_salt_must_be_stable_and_at_least_32_characters(self):
        with patch.dict(os.environ, {"BSK_REVIEWER_HASH_SALT": "short"}):
            with self.assertRaisesRegex(RuntimeError, "at least 32 characters"):
                producer.human_reviewer_hash_salt()
        valid = "production-salt-0123456789-abcdefghijklmnopqrstuvwxyz"
        with patch.dict(os.environ, {"BSK_REVIEWER_HASH_SALT": valid}):
            self.assertEqual(producer.human_reviewer_hash_salt(), valid)

    def test_panel_fails_closed_when_allowlist_is_smaller_than_minimum(self):
        with patch.dict(os.environ, {
            "BSK_HUMAN_REVIEWER_CHAT_IDS": "12345,67890",
            "BSK_HUMAN_REVIEW_MIN_RESPONSES": "3",
            "BSK_REVIEWER_HASH_SALT": "test-salt-0123456789-abcdefghijklmnopqrstuvwxyz",
        }):
            with tempfile.TemporaryDirectory() as folder:
                video = Path(folder) / "reel.mp4"
                video.write_bytes(b"video")
                with self.assertRaisesRegex(RuntimeError, "independent responses are required"):
                    producer.dispatch_human_review_panel("reel_001", "शीर्षक", video)

    def test_reviewer_allowlist_is_deduplicated_and_validated(self):
        with patch.dict(os.environ, {"BSK_HUMAN_REVIEWER_CHAT_IDS": "10001, 10002;10001;bad;-10003"}):
            self.assertEqual(producer.human_reviewer_chat_ids(), ["10001", "10002"])


if __name__ == "__main__":
    unittest.main()
