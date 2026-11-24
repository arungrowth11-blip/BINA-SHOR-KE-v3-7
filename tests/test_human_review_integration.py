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
import studio_pipeline  # noqa: E402


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

    def test_incomplete_ai_review_can_pass_only_after_real_human_fallback(self):
        history = {"topics": [{
            "title": "AI fallback story", "reel_id": "reel_fallback",
            "status": "ready_for_manual_publish_not_confirmed_published",
            "qa_passed": False, "eligible_for_human_review": True,
            "human_review_fallback_required": True, "human_review_qa_passed": False,
            "technical_checks_passed": True, "visual_qa_status": "local_pass_human_review",
            "motion_diagnostics_status": "passed", "metadata_ocr_status": "passed",
            "telegram_delivered": True,
        }]}
        store = {"reviews": []}
        command = (
            "/bskreview reel_id=reel_fallback; hook=4; story=4; emotion=4; visual=4; "
            "audio=4; ending=4; clarity=4; share_value=4; verdict=pass"
        )
        with patch.dict(os.environ, {
            "BSK_HUMAN_REVIEW_MIN_RESPONSES": "3",
            "BSK_REVIEWER_HASH_SALT": "test-salt-0123456789-abcdefghijklmnopqrstuvwxyz",
        }):
            for index, reviewer_id in enumerate(("10001", "10002", "10003"), start=1):
                record = producer._parse_human_review_message(
                    command, history, store, reviewer_id, index
                )
                self.assertTrue(record["saved"])
                history["topics"][0]["human_review_summary"] = record["summary"]
                if index < 3:
                    self.assertFalse(history["topics"][0]["qa_passed"])
            self.assertTrue(history["topics"][0]["qa_passed"])
            self.assertTrue(history["topics"][0]["human_review_qa_passed"])

        with patch.object(producer, "human_reviewer_chat_ids", return_value=["10001", "10002", "10003"]), \
             patch.object(producer, "telegram_chat_id", return_value="99999"):
            approved = producer._parse_review_message(
                "/approve title=AI fallback story", history, approved=True
            )
        self.assertTrue(approved["weekly_qualification_created"])
        qualification = history["one_reel_qualification"]
        self.assertEqual(qualification["visual_qa_status"], "local_pass_human_review")
        self.assertTrue(qualification["human_review_fallback_required"])
        self.assertTrue(qualification["human_review_qa_passed"])

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
            progress_events = []
            def fake_post(method, data=None, files=None, timeout=180):
                sent_chats.append(data["chat_id"])
                return {"ok": True}
            with patch.dict(os.environ, {
                "BSK_HUMAN_REVIEWER_CHAT_IDS": "12345,67890,24680,99999,not-an-id,12345",
                "BSK_REVIEWER_HASH_SALT": "test-salt-0123456789-abcdefghijklmnopqrstuvwxyz",
            }), patch.object(producer, "telegram_chat_id", return_value="99999"), patch.object(producer, "telegram_post", side_effect=fake_post):
                first = producer.dispatch_human_review_panel(
                    "reel_001", "शीर्षक", video,
                    on_progress=lambda state: progress_events.append(state),
                )
                second = producer.dispatch_human_review_panel(
                    "reel_001", "शीर्षक", video,
                    already_sent_hashes=first["sent_reviewer_hashes"],
                )
        self.assertEqual(sent_chats, ["12345", "67890", "24680"])
        self.assertEqual(first["configured_count"], 3)
        self.assertEqual(first["sent_count"], 3)
        self.assertEqual([event["sent_count"] for event in progress_events], [1, 2, 3])
        self.assertEqual([event["pending_count"] for event in progress_events], [2, 1, 0])
        self.assertEqual(second["sent_count"], 3)
        self.assertEqual(second["pending_count"], 0)

    def test_local_visual_fallback_does_not_require_telegram_reviewer_ids_but_keeps_all_local_gates(self):
        build = {"technical": {
            "technical_checks_passed": True,
            "rendered_frame_visual_qa": {
                "status": "local_pass_human_review",
                "review_mode": "deterministic_local_fallback",
                "human_review_required": True,
                "local_visual_diagnostics": {
                    "engine": "bsk_local_frame_qa_v1", "status": "passed",
                    "frames_scanned": 8, "hard_failures": [],
                },
                "full_video_motion_diagnostics": {"status": "passed", "full_video_scanned": True},
                "metadata_ocr_qa": {"status": "passed"},
            },
        }}
        with patch.object(
            studio_pipeline.producer,
            "external_human_reviewer_chat_ids",
            side_effect=AssertionError("manual review must not query Telegram reviewer IDs"),
        ):
            self.assertEqual(studio_pipeline.ensure_reel_qa_passed(build), "human_review_fallback")
        build["technical"]["rendered_frame_visual_qa"]["metadata_ocr_qa"]["status"] = "not_completed"
        with patch.object(
            studio_pipeline.producer,
            "external_human_reviewer_chat_ids",
            side_effect=AssertionError("manual review must not query Telegram reviewer IDs"),
        ):
            with self.assertRaisesRegex(RuntimeError, "OCR must complete"):
                studio_pipeline.ensure_reel_qa_passed(build)

    def test_owner_approval_attests_three_manual_external_passes_without_reviewer_ids(self):
        history = {"topics": [{
            "title": "Manual fallback Reel", "reel_id": "reel_manual_fallback",
            "status": "ready_for_manual_publish_not_confirmed_published",
            "qa_passed": False, "eligible_for_human_review": True,
            "human_review_fallback_required": True, "human_review_qa_passed": False,
            "technical_checks_passed": True, "visual_qa_status": "local_pass_human_review",
            "motion_diagnostics_status": "passed", "metadata_ocr_status": "passed",
            "telegram_delivered": True,
        }]}
        with patch.object(producer, "external_human_reviewer_chat_ids", return_value=[]):
            approved = producer._parse_review_message(
                "/approve title=Manual fallback Reel", history, approved=True
            )
        self.assertTrue(approved["weekly_qualification_created"])
        topic = history["topics"][0]
        self.assertTrue(topic["qa_passed"])
        self.assertTrue(topic["human_review_qa_passed"])
        self.assertEqual(topic["human_review_qa_source"], "owner_attested_manual_external_review")
        attestation = topic["manual_external_review_attestation"]
        self.assertEqual(attestation["reported_independent_reviewers"], 3)
        self.assertTrue(attestation["attested_by_owner"])
        self.assertEqual(attestation["verification"], "owner_attested_not_bot_verified")
        qualification = history["one_reel_qualification"]
        self.assertTrue(qualification["human_review_qa_passed"])
        self.assertEqual(qualification["human_review_qa_source"], "owner_attested_manual_external_review")
        self.assertEqual(
            qualification["manual_external_review_attestation"]["verification"],
            "owner_attested_not_bot_verified",
        )

    def test_weekly_qualification_rejects_local_fallback_without_human_pass(self):
        history = {"one_reel_qualification": {
            "status": "qualified", "qa_passed": True, "visual_qa_status": "local_pass_human_review",
            "human_review_fallback_required": True, "human_review_qa_passed": False,
            "telegram_delivered": True, "owner_approved": True,
            "reel_id": "reel_fallback", "approved_at_ist": "2026-11-24T10:00:00+05:30",
        }}
        lock = {"gpu_benchmark": {"qualified": True, "estimated_3_reel_hours": 5.0}}
        with self.assertRaisesRegex(RuntimeError, "Weekly 3-Reel production is locked"):
            studio_pipeline.require_weekly_qualification(history, lock)

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
            with patch.object(producer, "telegram_chat_id", return_value="99999"), tempfile.TemporaryDirectory() as folder:
                video = Path(folder) / "reel.mp4"
                video.write_bytes(b"video")
                with self.assertRaisesRegex(RuntimeError, "independent responses are required"):
                    producer.dispatch_human_review_panel("reel_001", "शीर्षक", video)

    def test_human_review_store_is_authenticated_encrypted_at_rest(self):
        from cryptography.fernet import Fernet
        key = Fernet.generate_key().decode("ascii")
        private_note = "sensitive reviewer feedback should not be plaintext"
        store = {"schema_version": 1, "reviews": [{
            "reel_id": "reel_001", "reviewer_hash": "opaque-hash",
            "notes": private_note, "verdict": "pass",
        }]}
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "human_reviews.enc"
            with patch.object(producer, "HUMAN_REVIEW_PATH", path), patch.dict(
                os.environ, {"BSK_HUMAN_REVIEW_ENCRYPTION_KEY": key}
            ):
                producer.save_human_review_store(store)
                ciphertext = path.read_bytes()
                self.assertNotIn(private_note.encode("utf-8"), ciphertext)
                self.assertNotIn(b"opaque-hash", ciphertext)
                self.assertEqual(producer.load_human_review_store(), store)

    def test_tampered_or_wrong_key_human_review_store_fails_closed(self):
        from cryptography.fernet import Fernet
        right_key = Fernet.generate_key().decode("ascii")
        wrong_key = Fernet.generate_key().decode("ascii")
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "human_reviews.enc"
            with patch.object(producer, "HUMAN_REVIEW_PATH", path), patch.dict(
                os.environ, {"BSK_HUMAN_REVIEW_ENCRYPTION_KEY": right_key}
            ):
                producer.save_human_review_store({"reviews": []})
                path.write_bytes(path.read_bytes()[:-2] + b"xx")
                with self.assertRaisesRegex(RuntimeError, "could not be authenticated/decrypted"):
                    producer.load_human_review_store()
            with patch.object(producer, "HUMAN_REVIEW_PATH", path), patch.dict(
                os.environ, {"BSK_HUMAN_REVIEW_ENCRYPTION_KEY": wrong_key}
            ):
                with self.assertRaisesRegex(RuntimeError, "could not be authenticated/decrypted"):
                    producer.load_human_review_store()

    def test_reviewer_allowlist_is_deduplicated_and_validated(self):
        with patch.dict(os.environ, {"BSK_HUMAN_REVIEWER_CHAT_IDS": "10001, 10002;10001;bad;-10003"}):
            self.assertEqual(producer.human_reviewer_chat_ids(), ["10001", "10002"])


if __name__ == "__main__":
    unittest.main()
